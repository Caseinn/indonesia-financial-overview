"""Cross-source reconciliation that runs after all Sources, non-blocking.

JISDOR publishes a daily reference rate while SEKI V.40 publishes a monthly
middle rate; the two should agree, so comparing them catches a silently shifted
source. The check never blocks a publish: a divergence is a finding to look at,
not a reason to discard good data.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from pipeline.models import Observation

PRIMARY_CODE = "USDIRR_JISDOR"
REFERENCE_CODE = "USDIRR_SEKI"
THRESHOLD = 0.02
MIN_PRIMARY_DAYS = 15


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    """One month where the primary and reference USD/IDR rates disagree."""

    period_start: date
    primary: float
    reference: float
    relative_diff: float


def monthly_averages(
    observations: Iterable[Observation], indicator_code: str, *, min_days: int = 1
) -> dict[tuple[int, int], float]:
    """Average an Indicator's values per month, skipping months with too few days."""
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for observation in observations:
        if observation.indicator_code == indicator_code:
            buckets[(observation.period_start.year, observation.period_start.month)].append(
                observation.normalized_value
            )
    return {
        period: sum(values) / len(values)
        for period, values in buckets.items()
        if len(values) >= min_days
    }


def reconcile_usd_idr(
    primary: Iterable[Observation],
    reference: Iterable[Observation],
    *,
    threshold: float = THRESHOLD,
) -> tuple[ReconciliationFinding, ...]:
    """Compare JISDOR's monthly average against SEKI V.40 for overlapping months."""
    daily = monthly_averages(primary, PRIMARY_CODE, min_days=MIN_PRIMARY_DAYS)
    monthly = {
        (
            observation.period_start.year,
            observation.period_start.month,
        ): observation.normalized_value
        for observation in reference
        if observation.indicator_code == REFERENCE_CODE
    }

    findings: list[ReconciliationFinding] = []
    for period, value in sorted(monthly.items()):
        if period not in daily or value == 0:
            continue
        relative_diff = abs(daily[period] - value) / value
        if relative_diff > threshold:
            findings.append(
                ReconciliationFinding(
                    period_start=date(period[0], period[1], 1),
                    primary=daily[period],
                    reference=value,
                    relative_diff=relative_diff,
                )
            )
    return tuple(findings)
