"""Write a built Gold snapshot to static JSON for the public frontend.

The React app reads pre-built snapshots from a public R2 prefix instead of
querying a database, preserving the "no live public database access" boundary
and the free-tier budget. Each Run rewrites a small cacheable snapshot plus a
manifest recording the Run and per-file checksums, so the frontend can show data
freshness and detect a partial upload. The Gold Parquet tables are rewritten too
unless the command targets a local directory.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from pipeline.parsing import sha256_hex
from pipeline.redaction import redact
from pipeline.storage.gold import store_from_env as gold_from_env
from pipeline.storage.s3 import ObjectStore, S3Error, client_from_env

_logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/json; charset=utf-8"
SCHEMA_VERSION = 1
DEFAULT_PREFIX = "web/data"
MANIFEST_NAME = "manifest.json"

Snapshot = Mapping[str, list[dict[str, object]]]


def _json_default(value: object) -> object:
    """Turn decimal and temporal values into JSON-safe primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def dumps(payload: object) -> bytes:
    """Serialize a snapshot deterministically so checksums are stable."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=_json_default,
    ).encode("utf-8")


def normalize_prefix(prefix: str) -> str:
    """Trim surrounding slashes so keys are composed predictably."""
    return prefix.strip("/") or DEFAULT_PREFIX


def build_files(
    snapshot: Snapshot,
    *,
    run_id: str,
    generated_at: datetime,
) -> dict[str, bytes]:
    """Render the snapshot and manifest as flat filename-to-bytes entries."""
    files: dict[str, bytes] = {}
    manifest_views: dict[str, dict[str, object]] = {}
    for name, rows in snapshot.items():
        body = dumps(rows)
        files[f"{name}.json"] = body
        manifest_views[name] = {"rows": len(rows), "sha256": sha256_hex(body)}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at.isoformat(),
        "views": manifest_views,
    }
    files[MANIFEST_NAME] = dumps(manifest)
    return files


def build_objects(
    snapshot: Snapshot,
    *,
    prefix: str = DEFAULT_PREFIX,
    run_id: str,
    generated_at: datetime,
) -> dict[str, bytes]:
    """Render the snapshot and its manifest into object-store keyed bytes."""
    base = normalize_prefix(prefix)
    files = build_files(snapshot, run_id=run_id, generated_at=generated_at)
    return {f"{base}/{name}": body for name, body in files.items()}


def export_to_directory(
    snapshot: Snapshot,
    directory: Path,
    *,
    run_id: str,
    generated_at: datetime | None = None,
) -> list[Path]:
    """Write the snapshot as local JSON files, for dev without a public bucket."""
    moment = generated_at or datetime.now(UTC)
    files = build_files(snapshot, run_id=run_id, generated_at=moment)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, body in files.items():
        path = directory / name
        path.write_bytes(body)
        written.append(path)
    _logger.info("web export: wrote %d files to %s", len(written), directory)
    return written


def export_snapshot(
    snapshot: Snapshot,
    store: ObjectStore,
    bucket: str,
    *,
    run_id: str,
    prefix: str = DEFAULT_PREFIX,
    generated_at: datetime | None = None,
) -> list[str]:
    """Upload the snapshot plus manifest, returning the keys written."""
    moment = generated_at or datetime.now(UTC)
    objects = build_objects(snapshot, prefix=prefix, run_id=run_id, generated_at=moment)
    for key, body in objects.items():
        store.put_object(Bucket=bucket, Key=key, Body=body, ContentType=CONTENT_TYPE)
    _logger.info("web export: wrote %d objects under %s/", len(objects), normalize_prefix(prefix))
    return list(objects)


def export_from_env(snapshot: Snapshot, *, run_id: str) -> list[str]:
    """Export to the public bucket, never falling back to the private data bucket."""
    bucket = os.environ.get("R2_PUBLIC_BUCKET")
    if not bucket:
        raise S3Error(
            "R2_PUBLIC_BUCKET is not set; refusing to publish web data in the private bucket"
        )
    store, _ = client_from_env()
    prefix = os.environ.get("R2_PUBLIC_PREFIX") or DEFAULT_PREFIX
    return export_snapshot(snapshot, store, bucket, run_id=run_id, prefix=prefix)


def _write_gold(tables: Mapping[str, pd.DataFrame], run_id: str) -> None:
    """Rewrite the Gold Parquet tables, never failing the web export."""
    try:
        gold_from_env().write(tables, run_id=run_id)
    except Exception as exc:
        _logger.warning("gold write failed for %s: %s", run_id, redact(str(exc)))


def main(argv: list[str] | None = None) -> int:
    """Rebuild Gold from Silver, then export it without re-running the sources."""
    from pipeline.gold import build_bundle_from_env

    parser = argparse.ArgumentParser(description="Export Gold views to the public web bucket.")
    parser.add_argument(
        "--run-id",
        default=datetime.now(UTC).strftime("export-%Y%m%dT%H%M%SZ"),
        help="identifier recorded in the manifest (default: current UTC timestamp)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write JSON files to this directory instead of uploading to R2",
    )
    args = parser.parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    bundle = build_bundle_from_env()
    if not args.out:
        _write_gold(bundle.tables, args.run_id)
    if args.out:
        export_to_directory(bundle.snapshot, args.out, run_id=args.run_id)
    else:
        export_from_env(bundle.snapshot, run_id=args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
