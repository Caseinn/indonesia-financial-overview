"""Compose one pipeline Run: ingest, Bronze, Silver, quality gates, Gold.

The entrypoint stays thin: it wires the stages and records the outcome, while
every adapter fetch, Silver merge, gate, and Gold projection stays in its own
module. Sources run independently, so one failure never erases another's work
(ADR-0003); a Circuit Breaker quarantines its Source but the batch still lands
in Bronze and Silver (ADR-0006). Gold is rebuilt once from Silver after every
Source has had its turn. The broad catches here are deliberate boundaries, not
blind error handling: they isolate a Source or a bookkeeping call and record it.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from dotenv import load_dotenv

from pipeline import export_web, gold, notify, quality, reconciliation
from pipeline.config import IndicatorsConfig, load_config
from pipeline.models import SourceRunResult
from pipeline.ops import OpsStore, PipelineRunRecord, SourceRunRecord
from pipeline.ops import store_from_env as ops_from_env
from pipeline.redaction import redact, redact_traceback
from pipeline.sources import bi_jisdor, bi_seki, bps, ojk_sjk, ojk_spi_editions
from pipeline.storage.bronze import BronzeStore
from pipeline.storage.bronze import store_from_env as bronze_from_env
from pipeline.storage.gold import GoldStore
from pipeline.storage.gold import store_from_env as gold_from_env
from pipeline.storage.silver import SilverStore
from pipeline.storage.silver import store_from_env as silver_from_env

_logger = logging.getLogger("pipeline.run_monthly")

DEFAULT_LOOKBACK_DAYS = 40
Runner = Callable[[IndicatorsConfig, str, date, date], SourceRunResult]


def _run_jisdor(config: IndicatorsConfig, run_id: str, start: date, end: date) -> SourceRunResult:
    return bi_jisdor.run(start, end, ingestion_run_id=run_id)


def _run_seki(config: IndicatorsConfig, run_id: str, start: date, end: date) -> SourceRunResult:
    return bi_seki.run(ingestion_run_id=run_id, config=config)


def _run_bps(config: IndicatorsConfig, run_id: str, start: date, end: date) -> SourceRunResult:
    return bps.run(start, end, ingestion_run_id=run_id, config=config)


def _run_ojk(config: IndicatorsConfig, run_id: str, start: date, end: date) -> SourceRunResult:
    return ojk_sjk.run(ingestion_run_id=run_id, config=config)


def _run_ojk_editions(
    config: IndicatorsConfig, run_id: str, start: date, end: date
) -> SourceRunResult:
    return ojk_spi_editions.run(ingestion_run_id=run_id, config=config)


SOURCES: dict[str, tuple[str, Runner]] = {
    "BI_JISDOR": ("BI_JISDOR", _run_jisdor),
    "BI_SEKI": ("BI_SEKI", _run_seki),
    "BPS": ("BPS", _run_bps),
    "OJK_SPI": ("OJK_SPI", _run_ojk),
    "OJK_SPI_EDITION": ("OJK_SPI", _run_ojk_editions),
}
DEFAULT_SOURCES = ("BI_JISDOR", "BI_SEKI", "BPS", "OJK_SPI")


def main(argv: list[str] | None = None) -> int:
    """Run every Source once and record the Run, returning a process exit code."""
    args = _parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_config(args.config)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    start, end = _period(args)
    selected = args.sources or list(DEFAULT_SOURCES)
    started_at = datetime.now(UTC)

    bronze = bronze_from_env()
    silver = silver_from_env()
    ops = ops_from_env()
    gold_store = gold_from_env()
    _write_run(ops, PipelineRunRecord(run_id, "running", args.trigger, started_at))

    status_by_source: dict[str, str] = {}
    results: dict[str, SourceRunResult] = {}
    overall = "failed"
    try:
        for key in selected:
            source_id, runner = SOURCES[key]
            status, result = _run_source(
                source_id, runner, config, run_id, start, end, bronze, silver, ops
            )
            status_by_source[key] = status
            if result is not None:
                results[source_id] = result
        overall = _overall(list(status_by_source.values()))
        latest = ops.latest_source_runs(config.sources)
        quarantined = ops.quarantined_checksums(config.sources)
        gates = _reconcile(results) + quality.evaluate_freshness(config, latest).findings
        _notify_gates(run_id, gates)
        bundle = gold.build_bundle(
            config=config,
            frame=silver.read_all(),
            latest=latest,
            quarantined=quarantined,
        )
        _write_gold(gold_store, bundle.tables, run_id)
        _export_web(bundle.snapshot, run_id)
    except Exception:
        overall = "failed"
        raise
    finally:
        _finish_run(ops, run_id, overall, status_by_source, started_at, args.trigger)

    _logger.info("run %s finished: %s", run_id, overall)
    return 0 if overall == "ok" else 1


def _notify(payload: dict[str, object]) -> None:
    """Send an alert when a webhook is configured, never failing the Run."""
    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    if webhook:
        notify.send(webhook, payload)


def _export_web(snapshot: dict[str, list[dict[str, object]]], run_id: str) -> None:
    """Publish the frontend snapshot, never failing the Run when R2 is unavailable."""
    try:
        export_web.export_from_env(snapshot, run_id=run_id)
    except Exception as exc:
        _logger.error("web export failed for %s: %s", run_id, redact_traceback(exc))
        _notify(
            {
                "run_id": run_id,
                "check": "web_export",
                "status": "failed",
                "error": redact(str(exc))[:500],
            }
        )


def _write_gold(
    store: GoldStore,
    tables: Mapping[str, pd.DataFrame],
    run_id: str,
) -> None:
    """Persist the Gold tables, never failing the Run when R2 is unavailable."""
    try:
        store.write(tables, run_id=run_id)
    except Exception as exc:
        _logger.error("gold write failed for %s: %s", run_id, redact_traceback(exc))
        _notify(
            {
                "run_id": run_id,
                "check": "gold_write",
                "status": "failed",
                "error": redact(str(exc))[:500],
            }
        )


def _write_run(ops: OpsStore, record: PipelineRunRecord) -> None:
    """Record the Run, never letting a bookkeeping failure escape."""
    try:
        ops.write_run(record)
    except Exception as exc:
        _logger.error("recording run %s failed: %s", record.run_id, redact_traceback(exc))


def _finish_run(
    ops: OpsStore,
    run_id: str,
    status: str,
    status_by_source: dict[str, str],
    started_at: datetime,
    trigger: str | None,
) -> None:
    """Close the Run record with the per-source outcomes."""
    message = ", ".join(f"{source}={value}" for source, value in status_by_source.items())
    _write_run(
        ops,
        PipelineRunRecord(
            run_id,
            status,
            trigger,
            started_at,
            finished_at=datetime.now(UTC),
            message=message,
        ),
    )


def _run_source(
    source_id: str,
    runner: Runner,
    config: IndicatorsConfig,
    run_id: str,
    start: date,
    end: date,
    bronze: BronzeStore,
    silver: SilverStore,
    ops: OpsStore,
) -> tuple[str, SourceRunResult | None]:
    """Ingest one Source and record it, failing or quarantining alone.

    ``source_id`` is the Source's logical id, so both OJK adapters record under
    ``OJK_SPI``. Everything after the fetch is guarded as well, so a storage or
    gate failure blocks this Source without aborting the rest of the batch
    (ADR-0003).
    """
    _logger.info("%s: ingesting %s..%s", source_id, start, end)
    status = "failed"
    result: SourceRunResult | None = None
    checksums: tuple[str, ...] = ()
    rows = 0
    revisions = 0
    message: str | None = None
    try:
        result = runner(config, run_id, start, end)
        checksums = tuple(sorted({item.source_file_sha256 for item in result.observations}))
        rows = len(result.observations)
        bronze.write(result.envelope, result.artifacts)
        quarantined = ops.quarantined_checksums((source_id,)).get(source_id, ())
        previous = silver.current_values(result.observations, excluded_checksums=quarantined)
        write = silver.upsert(result.observations)
        revisions = len(write.revisions)
        report = quality.evaluate(result.observations, config, previous)

        if report.findings:
            _notify(_alert_payload(source_id, run_id, report))
        if report.has_breaker:
            message = f"quarantined: {_breaker_summary(source_id, report)}"[:500]
            _record_quarantine(ops, source_id, checksums)
            _logger.warning("%s: %s", source_id, message)
        else:
            status = "ok"
            _logger.info("%s: ingested %d rows (%d revisions)", source_id, rows, revisions)
    except Exception as exc:
        message = redact(str(exc))[:500]
        _logger.error("%s: ingestion or publish failed: %s", source_id, redact_traceback(exc))
        _notify(
            {
                "run_id": run_id,
                "check": "source_run",
                "source_id": source_id,
                "status": "failed",
                "error": message,
            }
        )
    finally:
        _record_source(
            ops,
            SourceRunRecord(
                run_id=run_id,
                source_id=source_id,
                status=status,
                finished_at=datetime.now(UTC),
                rows_published=rows if status == "ok" else 0,
                revisions=revisions if status == "ok" else 0,
                publication_checksums=checksums,
                message=message,
            ),
        )
    return status, result


def _record_source(ops: OpsStore, record: SourceRunRecord) -> None:
    """Record a Source Run, never letting the recording itself raise."""
    try:
        ops.write_source(record)
    except Exception as exc:
        _logger.error(
            "%s: recording the Source Run failed: %s",
            record.source_id,
            redact_traceback(exc),
        )


def _record_quarantine(ops: OpsStore, source_id: str, checksums: tuple[str, ...]) -> None:
    """Persist rejected publications, never letting the bookkeeping fail the Run."""
    if not checksums:
        return
    try:
        ops.record_quarantine(source_id, checksums)
    except Exception as exc:
        _logger.error(
            "%s: recording the quarantine failed: %s",
            source_id,
            redact_traceback(exc),
        )


def _alert_payload(source_id: str, run_id: str, report: quality.QualityReport) -> dict[str, object]:
    return {
        "run_id": run_id,
        "source_id": source_id,
        "breakers": len(report.breakers),
        "warns": len(report.warns),
        "findings": [
            {"severity": str(finding.severity), "code": finding.code, "message": finding.message}
            for finding in report.findings
        ],
    }


def _breaker_summary(source_id: str, report: quality.QualityReport) -> str:
    return "; ".join(f"{finding.code}: {finding.message}" for finding in report.breakers)


def _reconcile(results: dict[str, SourceRunResult]) -> tuple[quality.Finding, ...]:
    """Compare JISDOR against SEKI and turn divergences into advisory findings."""
    primary = results.get("BI_JISDOR")
    reference = results.get("BI_SEKI")
    if primary is None or reference is None:
        return ()
    findings = reconciliation.reconcile_usd_idr(primary.observations, reference.observations)
    for finding in findings:
        _logger.warning(
            "reconciliation: %s JISDOR %.2f vs SEKI %.2f (%.2f%%)",
            finding.period_start,
            finding.primary,
            finding.reference,
            finding.relative_diff * 100,
        )
    return tuple(
        quality.Finding(
            severity=quality.Severity.WARN,
            code="usd_idr_reconciliation",
            message=(
                f"{finding.period_start}: JISDOR {finding.primary:.2f} vs "
                f"SEKI {finding.reference:.2f} ({finding.relative_diff * 100:.2f}%)"
            ),
            period_start=finding.period_start,
        )
        for finding in findings
    )


def _notify_gates(run_id: str, findings: tuple[quality.Finding, ...]) -> None:
    """Send the Run-level advisory findings in one webhook, never failing the Run."""
    if not findings:
        return
    _notify(
        {
            "run_id": run_id,
            "check": "run_gates",
            "findings": [
                {
                    "severity": str(finding.severity),
                    "code": finding.code,
                    "message": finding.message,
                }
                for finding in findings
            ],
        }
    )


def _overall(statuses: list[str]) -> str:
    unique = set(statuses)
    if unique == {"ok"}:
        return "ok"
    if unique == {"failed"}:
        return "failed"
    return "partial"


def _period(args: argparse.Namespace) -> tuple[date, date]:
    end = args.end or date.today()
    start = args.start or end - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    if start > end:
        raise SystemExit(f"--start {start} is after --end {end}")
    return start, end


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Indonesia financial pipeline once.")
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        help="inclusive period start (default: today - lookback)",
    )
    parser.add_argument(
        "--end", type=date.fromisoformat, help="inclusive period end (default: today)"
    )
    parser.add_argument("--run-id", help="Run id (default: current UTC timestamp)")
    parser.add_argument("--trigger", default="schedule", help="what started this Run")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=sorted(SOURCES),
        help="subset of Sources to run (default: all)",
    )
    parser.add_argument("--config", default=None, help="path to indicators.yml")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
