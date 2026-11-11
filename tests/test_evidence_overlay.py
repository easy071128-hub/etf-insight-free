"""Research overlay never turns unidentified composition weights into NAV."""
import pytest
from etf_engine import parse_bundle
from evidence_overlay import annotate_component_business
from research_registry import reviewed_company_evidence


def _table(as_of=False, codes=None):
    header = ("ETF코드,ETF상품명,기준일," if as_of else "") + "종목코드,구성종목명,시가총액 구성비중\n"
    records = codes or [
        ("042700", "한미반도체", 60),
        ("247540", "에코프로비엠", 40),
    ]
    raw = header
    for code, name, weight in records:
        pre = "091230,연구용 참고ETF,2026-10-13," if as_of else ""
        raw += f"{pre}{code},{name},{weight}\n"
    catalog = {"091230":{"code":"091230","name":"연구용 참고ETF"}}
    _,snapshots,_,reports=parse_bundle([("unlinked.csv",raw.encode("utf-8-sig"))],catalog)
    assert not snapshots
    return reports[0]


def test_undated_composition_shows_business_names_but_never_sector_exposures():
    report = _table()
    out = annotate_component_business(
        report["_standalone_frame"],report["weight_basis"],reviewed_company_evidence())
    assert out["available"] and out["matched_count"] == 2
    assert out["matched_table_pct"] == pytest.approx(100)
    assert out["sector_distribution"] == {}
    assert all("소급 불가" in r["원본 기준일과 비교"] for r in out["matches"])


def test_dated_composition_only_weights_evidence_preceding_holdings():
    report = _table(as_of=True)
    out = annotate_component_business(
        report["_standalone_frame"],report["weight_basis"],
        reviewed_company_evidence(),as_of_date=report["identity"]["as_of_date"])
    assert out["matched_count"] == 2
    assert out["dated_count"] == 1
    assert out["sector_distribution"] == {"반도체":pytest.approx(60)}
    assert any("근거일이 더 늦음" in r["원본 기준일과 비교"] for r in out["matches"])


def test_id_name_mismatch_rejected_as_company_business_match():
    report = _table(codes=[
        ("042700", "동명이인", 60), ("247540", "에코프로비엠", 40)])
    out = annotate_component_business(
        report["_standalone_frame"],report["weight_basis"],reviewed_company_evidence())
    assert out["matched_count"] == 1
    assert out["matched_table_pct"] == pytest.approx(40)


def test_nav_table_cannot_use_market_cap_business_overlay():
    report = _table()
    out = annotate_component_business(
        report["_standalone_frame"],"ETF NAV 편입비중(원본 명시, 독립 검증 전)",
        reviewed_company_evidence())
    assert not out["available"]
    assert not out["matches"]


def test_explicit_bank_deposit_row_is_not_stock_concentration():
    from etf_engine import krx_component_concentration
    import pandas as pd
    frame = pd.DataFrame({
        "security_id": ["042700","247540","KRD010010001"],
        "security_name": ["한미반도체","에코프로비엠","원화예금"],
        "weight_pct": [55.0, 35.0, 10.0],
        "asset_type": ["미확인","미확인","미확인"],
    })
    stats=krx_component_concentration(frame)
    assert stats["available"]
    assert stats["cash_rows"] == 1
    assert stats["instrument_rows"] == 2
    assert stats["top3_pct"] == pytest.approx(90)
    assert stats["hhi"] == pytest.approx(55**2+35**2+10**2)
