"""Tests for pipeline.config loading and validation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pipeline.config import DEFAULT_CONFIG_PATH, ConfigError, load_config


def test_loads_committed_config() -> None:
    config = load_config()
    assert DEFAULT_CONFIG_PATH.exists()

    policy = config.indicator("POLICY_RATE")
    assert policy.source == "BI_SEKI"
    assert policy.unit == "percent_per_annum"
    assert policy.drift is not None
    assert policy.drift.warn.value == 25
    assert policy.drift.circuit_breaker.value == 500
    assert len(policy.regimes) == 2
    assert policy.regimes[0].valid_from == date(2010, 1, 1)
    assert policy.regimes[1].valid_to is None

    seki = config.source("BI_SEKI")
    assert seki.cadence.probe_start_day == 15
    assert seki.cadence.probe_end_day == 28


def test_indicator_lookup_has_business_fields() -> None:
    config = load_config()
    jisdor = config.indicator("USDIRR_JISDOR")
    assert jisdor.frequency == "daily"
    assert jisdor.role is None
    assert config.indicator("USDIRR_SEKI").role == "reconciliation"


def test_geography_projection() -> None:
    config = load_config()

    assert config.geographies["IDN"].is_national is True
    assert config.geographies["MYS"].name == "Malaysia"
    assert config.indicator("MYS_GDP_GROWTH").geography == "MYS"
    assert config.indicator("POLICY_RATE").geography == "IDN"


def test_unknown_geography_reference_raises(tmp_path: Path) -> None:
    bad = tmp_path / "indicators.yml"
    bad.write_text(
        "sources:\n"
        "  BI_SEKI:\n"
        "    name: Bank Indonesia SEKI\n"
        "indicators:\n"
        "  POLICY_RATE:\n"
        "    name: Policy Rate\n"
        "    unit: percent_per_annum\n"
        "    frequency: monthly\n"
        "    source: BI_SEKI\n"
        "    geography: XYZ\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown geography"):
        load_config(bad)


def test_unknown_indicator_raises() -> None:
    config = load_config()
    with pytest.raises(ConfigError, match="unknown indicator code"):
        config.indicator("NOPE")


def test_unknown_source_reference_raises(tmp_path: Path) -> None:
    bad = tmp_path / "indicators.yml"
    bad.write_text(
        "sources:\n"
        "  BI_SEKI:\n"
        "    name: Bank Indonesia SEKI\n"
        "indicators:\n"
        "  POLICY_RATE:\n"
        "    name: Policy Rate\n"
        "    unit: percent_per_annum\n"
        "    frequency: monthly\n"
        "    source: BI_MISSING\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown source"):
        load_config(bad)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    bad = tmp_path / "indicators.yml"
    bad.write_text(
        "sources:\n"
        "  BI_SEKI:\n"
        "    name: Bank Indonesia SEKI\n"
        "indicators:\n"
        "  POLICY_RATE:\n"
        "    name: Policy Rate\n"
        "    frequency: monthly\n"
        "    source: BI_SEKI\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="missing required field 'unit'"):
        load_config(bad)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "absent.yml")


def test_bi_seki_indicator_without_table_raises(tmp_path: Path) -> None:
    bad = tmp_path / "indicators.yml"
    bad.write_text(
        "sources:\n"
        "  BI_SEKI:\n"
        "    name: Bank Indonesia SEKI\n"
        "indicators:\n"
        "  POLICY_RATE:\n"
        "    name: Policy Rate\n"
        "    unit: percent_per_annum\n"
        "    frequency: monthly\n"
        "    source: BI_SEKI\n"
        "    source_sheets:\n"
        "      - 1.25A_1\n"
        "    source_row: Policy Rate\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="lacks binding fields"):
        load_config(bad)


def test_ojk_indicator_without_binding_raises(tmp_path: Path) -> None:
    bad = tmp_path / "indicators.yml"
    bad.write_text(
        "sources:\n"
        "  OJK_SPI:\n"
        "    name: OJK\n"
        "indicators:\n"
        "  CAR:\n"
        "    name: Capital Adequacy Ratio\n"
        "    unit: percent\n"
        "    frequency: monthly\n"
        "    source: OJK_SPI\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="lacks binding fields"):
        load_config(bad)


def test_committed_config_separates_annual_ratio_series() -> None:
    config = load_config()

    assert config.indicator("CAR").frequency == "monthly"
    assert config.indicator("CAR").source_sheet is None
    assert config.indicator("CAR_ANNUAL").frequency == "annual"
    assert config.indicator("CAR_ANNUAL").source_sheet == "Kinerja_KBMI 1.16.-1.20."
