"""Regression of explicitly reviewed company evidence and issuer research examples.

All portfolio inputs here are synthetic and no official NAV inventory is bundled.
"""
from datetime import date

import pandas as pd
import pytest

from research_registry import (
    REVIEWED_ON, reviewed_company_evidence, issuer_research_cases,
    combine_company_evidence, verify_registry,
)
from research_analysis import analyze_labeled_portfolio
from structure_similarity import score_pair
from streamlit.testing.v1 import AppTest
from pathlib import Path


def test_registry_dates_sources_and_composite_protection():
    n, cases = verify_registry()
    assert n == 15 and cases == 2
    metadata = reviewed_company_evidence()
    assert all(r["source_url"].startswith("https://") for r in metadata.values())
    assert all(r["as_of_date"] <= REVIEWED_ON for r in metadata.values())
    assert "복합사업" in metadata["005930"]["subsector"]
    assert "복합사업" in metadata["003670"]["subsector"]
    assert metadata["247540"]["as_of_date"] == REVIEWED_ON
    assert metadata["000660"]["as_of_date"] < REVIEWED_ON


def test_issuer_aggregate_is_not_fabricated_nav_holdings():
    cases = issuer_research_cases()
    case = next(x for x in cases if x["etf_code"] == "091160")
    # Recompute directly from the 21 published *non-cash* component percentages,
    # not from an invented 2026-11-12 NAV portfolio.
    disclosed = [
        17.03,15.86,10.73,8.11,4.43,4.40,4.13,4.08,3.99,3.98,
        2.86,2.84,2.52,2.39,2.29,2.00,1.95,1.76,1.67,1.50,1.48,
    ]
    assert sum(disclosed) == pytest.approx(case["sum_disclosed_pct"])
    assert sum(disclosed[:3]) == pytest.approx(case["top3_pct"])
    assert sum(disclosed[:5]) == pytest.approx(case["top5_pct"])
    assert sum(x*x for x in disclosed) == pytest.approx(case["hhi_disclosed"])
    assert not case["full_nav_verified"]
    assert "현금성 제외" in case["weight_basis"]
    partial = next(x for x in cases if x["etf_code"] == "461950")
    assert partial["hhi_disclosed"] is None
    assert partial["sum_disclosed_pct"] < 100.0
    assert not partial["full_nav_verified"]


def test_user_data_cannot_silently_override_reviewed_business():
    original = reviewed_company_evidence()
    uploaded = {
        "005930": dict(original["005930"], subsector="DRAM"),
        "123456": {
            "security_name": "별도 기업", "sector": "기타",
            "subsector": "", "country": "", "group": "",
            "as_of_date": "2026-10-01", "source_url": "https://example.org/source",
        },
    }
    merged, conflicts = combine_company_evidence(original, uploaded)
    assert conflicts == ["005930"]
    assert merged["005930"]["subsector"] == original["005930"]["subsector"]
    assert "123456" in merged
    assert original["005930"]["subsector"] != "DRAM"


def _snapshot(day,weights=(60,40)):
    return {
        "frame": pd.DataFrame({
            "security_id": ["042700","247540"],
            "security_name": ["한미반도체","에코프로비엠"],
            "asset_type": ["주식","주식"], "weight_pct": list(weights),
        }),
        "meta": {
            "as_of_date": day, "nav_basis_claimed": True,
            "pcf_context_detected": False,
        },
    }


def test_reviewed_business_does_not_backfill_company_website_into_past():
    metadata = reviewed_company_evidence()
    older = analyze_labeled_portfolio(_snapshot("2026-10-13"),metadata)
    assert older["available"]
    assert "247540" in older["future_relative_to_holdings"]
    assert older["coverage_pct"]["subsector"] == pytest.approx(60.0)
    assert older["complete"]["subsector"] is False
    newer = analyze_labeled_portfolio(_snapshot("2026-11-12"),metadata)
    assert newer["complete"]["subsector"] is True
    assert newer["breakdowns"]["subsector"]["양극재"] == pytest.approx(40.0)
    # Group evidence is incomplete, so the five-factor full score must not
    # appear even if both files are synthetically complete NAV-labelled files.
    pair = score_pair(_snapshot("2026-11-12"),_snapshot("2026-11-12"),metadata)
    assert pair["overall_score"] is None
    assert "기업집단 구성" in " ".join(pair["missing"])


def test_streamlit_displays_issuer_research_without_uploads():
    script = Path(__file__).resolve().parents[1]/"app.py"
    app = AppTest.from_file(script,default_timeout=30).run()
    assert not app.exception
    assert any("운용사 공시 확인 사례" in s.value for s in app.subheader)
    assert any("공식 기업자료" in s.value for s in app.subheader)
