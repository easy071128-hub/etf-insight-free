"""Regression: archived user KRX results remain useful without reupload.

Original user files could not be reopened in this build context. These tests
validate faithfully carrying forward the earlier audit, not re-analysing bytes.
"""
import pytest
from historical_krx_cases import (
    archived_user_results, archived_pair_observation, audit_historical_results,
)
from research_registry import issuer_research_cases


def test_all_previously_provided_krx_cases_visible_as_historical_records():
    assert audit_historical_results() == 4
    records = {r["file"]:r for r in archived_user_results()}
    assert set(records) == {
        "data_2325_20261112.xlsx", "data_2340_20261112.xlsx",
        "data_2308_20261112.xlsx", "data_5705_20261111.xlsx",
    }
    a=records["data_2325_20261112.xlsx"]
    b=records["data_2340_20261112.xlsx"]
    assert (a["top1_pct"],a["top3_pct"],a["top5_pct"],a["hhi"],a["grade"]) == (
        22.23,59.60,88.53,1642.09,"고집중")
    assert (b["top1_pct"],b["top3_pct"],b["top5_pct"],b["hhi"],b["grade"]) == (
        24.92,52.34,70.65,1312.94,"고집중")


def test_missing_weight_stays_unavailable_not_zero():
    case=next(r for r in archived_user_results()
              if r["file"] == "data_2308_20261112.xlsx")
    assert case["observed_component_count"] == 505
    assert case["hhi"] is None
    assert case["top1_pct"] is None
    assert case["top3_pct"] is None
    assert case["top5_pct"] is None
    assert case["grade"] == "자료부족"


def test_previous_crosscheck_still_does_not_certify_etf_nav():
    case=next(r for r in archived_user_results()
              if r["file"] == "data_5705_20261111.xlsx")
    assert case["top5_pct"] == pytest.approx(59.79)
    assert len(case["original_sha256"])==64
    assert "NAV" in case["limitation"]
    assert "시가총액" in case["weight_basis"]
    pair=archived_pair_observation()
    assert pair["observed_common_non_cash_security_count"] == 0
    assert "NAV" in pair["limitation"]
    assert not any(c["file"] in [x["etf_code"] for x in issuer_research_cases()]
                   for c in archived_user_results())


def test_app_displays_historical_results_without_upload():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),
                          default_timeout=30).run()
    assert not app.exception
    assert any("기존에 제출한 KRX 자료 검증 기록" in s.value
               for s in app.subheader)
