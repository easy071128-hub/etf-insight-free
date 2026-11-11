"""KRX market-cap tables can be compared directly without claiming ETF NAV data."""
from io import BytesIO

import pytest
from openpyxl import load_workbook

from etf_engine import (
    compare_krx_component_tables,excel_report_krx_comparison,parse_bundle
)


def _csv(rows):
    return ("종목코드,구성종목명,시가총액 구성비중\n"+
        "".join(f"{code},{name},{weight}\n" for code,name,weight in rows)).encode("utf-8-sig")


def _reports():
    a=_csv([("005930","삼성전자",60),("000660","SK하이닉스",40)])
    b=_csv([("005930","삼성전자",50),("042700","한미반도체",50)])
    _,snapshots,_,out=parse_bundle([("A.csv",a),("B.csv",b)])
    assert not snapshots
    assert [r["status"] for r in out]==["성공","성공"]
    return out


def test_two_standalone_krx_tables_have_correct_overlap():
    a,b=_reports()
    diff=compare_krx_component_tables(a,b)
    assert diff["available"]
    assert diff["file_a"]=="A.csv"
    assert diff["file_b"]=="B.csv"
    assert diff["overlap_non_cash_pct"]==pytest.approx(50)
    assert diff["common_count"]==1
    assert diff["top3_gap_pct"]==pytest.approx(0)
    assert diff["hhi_a"]==pytest.approx(5200)
    assert diff["hhi_b"]==pytest.approx(5000)
    assert diff["grade_a"]=="고집중"
    assert diff["grade_b"]=="고집중"
    assert "순자산 편입비중" in diff["reason"]
    by_code={r["종목코드"]:r for r in diff["rows"]}
    assert by_code["005930"]["차이(%p)"]==pytest.approx(10)


def test_same_source_file_is_not_compared_to_itself():
    a,b=_reports()
    assert compare_krx_component_tables(a,a)["available"] is False
    assert compare_krx_component_tables(a,b)["available"]


def test_explicit_cash_is_excluded_from_overlap():
    a=_csv([("005930","삼성전자",60),("000660","SK하이닉스",30),
            ("KRWCASH","원화현금",10)])
    b=_csv([("005930","삼성전자",30),("000660","SK하이닉스",60),
            ("KRWCASH","원화현금",10)])
    _,snapshots,_,reports=parse_bundle([("A.csv",a),("B.csv",b)])
    assert not snapshots
    diff=compare_krx_component_tables(*reports)
    assert diff["available"]
    assert diff["common_count"]==2
    assert diff["overlap_non_cash_pct"]==pytest.approx(60)
    assert all(r["종목코드"]!="KRWCASH" for r in diff["rows"])


def test_uncertain_or_invalid_composition_not_compared():
    good,bad=_reports()
    invalid=dict(bad)
    invalid["weight_basis"]="ETF 편입비중(원본 표기)"
    assert not compare_krx_component_tables(good,invalid)["available"]
    invalid=dict(bad)
    invalid["_standalone_frame"]=None
    assert not compare_krx_component_tables(good,invalid)["available"]


def test_comparison_excel_contains_basis_and_no_formulas():
    a,b=_reports()
    diff=compare_krx_component_tables(a,b)
    output=excel_report_krx_comparison(diff)
    book=load_workbook(BytesIO(output),data_only=False)
    assert book.sheetnames==["비교요약","종목별차이"]
    summary={r[0]:r[1] for r in book["비교요약"].values if r[0]}
    assert "시가총액" in summary["자료 유형"]
    assert summary["공통 비현금 종목 수"]==1
    assert all(cell.data_type!="f" for sheet in book for row in sheet for cell in row)
