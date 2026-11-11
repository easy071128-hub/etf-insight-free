"""Synthetic regression tests; no claim that these are actual ETF filings."""
from io import BytesIO

from openpyxl import load_workbook

from data_quality import build_readiness_audit, excel_readiness_audit, review_etf
from etf_engine import parse_bundle
from research_analysis import parse_company_evidence


def csv(*lines):
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


def portfolio(weight_header="NAV 편입비중(%)"):
    holdings = csv(
        f"종목코드,종목명,{weight_header},자산유형,ETF코드,ETF상품명,기준일",
        "005930,가상회사A,60,주식,487230,가상 연구 ETF,2026-11-10",
        "000660,가상회사B,40,주식,487230,가상 연구 ETF,2026-11-10",
    )
    catalog, snapshots, _, reports = parse_bundle([("portfolio.csv", holdings)])
    assert reports[0]["status"] == "성공", reports
    return catalog, snapshots


def company_metadata(one_missing=False):
    rows = [
        "종목코드,종목명,섹터,세부산업,국가,기업집단,근거URL,기준일",
        "005930,가상회사A,반도체,DRAM,한국,독립기업,https://example.org/a,2026-11-10",
    ]
    if not one_missing:
        rows.append("000660,가상회사B,반도체,검사장비,한국,독립기업,https://example.org/b,2026-11-10")
    data, _ = parse_company_evidence(csv(*rows), "business.csv")
    return data


def test_basic_catalog_is_never_counted_as_actual_portfolios():
    cat = {f"{i:06d}": {"name": f"기본정보 ETF {i}"} for i in range(1190)}
    audit = build_readiness_audit(cat)
    assert audit["counts"]["기본 ETF 수"] == 1190
    assert audit["counts"]["실제 구성종목 등록 ETF 수(사용자 세션)"] == 0
    assert audit["counts"]["공식 NAV 원출처 독립 검증 완료 ETF 수"] == 0
    assert set(row["level"] for row in audit["rows"]) == {"기본정보만 확인"}


def test_generic_weight_must_not_claim_nav_analysis():
    cat, snapshots = portfolio("비중(%)")
    row = review_etf("487230", cat["487230"], snapshots["487230"], company_metadata())
    assert row["level"] == "일부 분석 가능"
    assert row["concentration_calculable"]
    assert not row["nav_label_present"]
    assert row["sector_coverage_pct"] is None
    assert any("NAV 편입비중" in note for note in row["notes"])


def test_complete_user_labels_enable_research_not_independent_verification():
    cat, snapshots = portfolio()
    row = review_etf("487230", cat["487230"], snapshots["487230"], company_metadata())
    assert row["level"] == "분석 가능(제출 근거 기준)"
    assert row["full_subsector_classification"]
    assert row["sector_coverage_pct"] == 100
    assert not row["nav_source_independently_verified"]
    assert not row["company_source_independently_verified"]
    assert not row["quantitative_pair_ready"]


def test_incomplete_company_labels_are_never_filled_in():
    cat, snapshots = portfolio()
    row = review_etf("487230", cat["487230"], snapshots["487230"], company_metadata(True))
    assert row["level"] == "일부 분석 가능"
    assert row["sector_coverage_pct"] == 60
    assert not row["full_subsector_classification"]
    assert any("누락" in note for note in row["notes"])


def test_audit_counts_only_present_sessions_and_records_source_limit():
    cat, snapshots = portfolio()
    cat["123456"] = {"name": "다른 ETF 기본정보만"}
    audit = build_readiness_audit(cat, snapshots, company_metadata(), {
        "source_url": "https://data.krx.co.kr/",
        "as_of_date": "2026-11-11",
        "rights_status": "허가 확인되지 않음",
    })
    assert audit["counts"]["기본 ETF 수"] == 2
    assert audit["counts"]["실제 구성종목 등록 ETF 수(사용자 세션)"] == 1
    assert audit["counts"]["제출 근거 기준 구조 분석 가능 ETF 수"] == 1
    assert audit["counts"]["공식 기업 분류 원출처 독립 검증 완료 ETF 수"] == 0
    assert audit["catalog_rights"] == "허가 확인되지 않음"


def test_audit_excel_is_human_readable_and_escapes_formulas():
    cat, snapshots = portfolio()
    cat["123456"] = {"name": "=HYPERLINK(\"http://evil.test\")"}
    audit = build_readiness_audit(cat, snapshots, {})
    binary = excel_readiness_audit(audit)
    wb = load_workbook(BytesIO(binary), read_only=True)
    assert "연구검증현황" in wb.sheetnames
    assert "ETF별자료상태" in wb.sheetnames
    table = list(wb["ETF별자료상태"].values)
    assert table[0][0] == "ETF 코드"
    assert any(r[1] == "'=HYPERLINK(\"http://evil.test\")" for r in table[1:])
    assert all(cell.data_type != "f" for sheet in wb for row in sheet for cell in row)


def test_empty_catalog_still_exports_audit():
    audit = build_readiness_audit({})
    assert audit["rows"] == []
    wb = load_workbook(BytesIO(excel_readiness_audit(audit)), read_only=True)
    assert wb["ETF별자료상태"]["A1"].value == "ETF 코드"
