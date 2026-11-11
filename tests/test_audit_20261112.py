"""Independent regressions for the 2026-11-12 financial integrity audit."""
from datetime import date, timedelta
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

from etf_engine import (
    concentration, date_value, excel_report, krx_component_concentration,
    parse_bundle, parse_holdings_auto,
)


def _data(headers, rows):
    return ("\n".join([headers, *rows]) + "\n").encode("utf-8-sig")


def _holding_rows(header="종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일"):
    return _data(header,[
        "005930,삼성전자,60,주식,487230,합성 연구 ETF 487230,2026-11-10",
        "000660,SK하이닉스,40,주식,487230,합성 연구 ETF 487230,2026-11-10",
    ])


def _catalog():
    return {"487230":{"code":"487230","name":"합성 연구 ETF 487230","short_name":"합성 연구 ETF 487230"}}


def test_filename_is_never_sufficient_to_attribute_etf_holdings():
    data=_data("종목코드,종목명,비중(%),자산유형,ETF상품명,기준일",[
        "005930,삼성전자,60,주식,합성 연구 ETF 487230,2026-11-10",
        "000660,SK하이닉스,40,주식,합성 연구 ETF 487230,2026-11-10",
    ])
    catalog, snapshots, _, messages=parse_bundle(
        [("ETF_487230.csv",data)],catalog=_catalog())
    assert not snapshots
    assert "파일명" in messages[0]["message"]
    assert catalog["487230"]["name"]=="합성 연구 ETF 487230"


def test_multiple_weight_columns_cannot_silently_choose_first():
    data=_data(
        "종목코드,종목명,비중(%),시가총액 구성비중,자산유형,ETF코드,ETF상품명,기준일",
        ["005930,삼성전자,60,75,주식,487230,합성 연구 ETF 487230,2026-11-10",
         "000660,SK하이닉스,40,25,주식,487230,합성 연구 ETF 487230,2026-11-10"],
    )
    with pytest.raises(ValueError,match="비중 열이 여러"):
        parse_holdings_auto(data,"two-weights.csv")
    _,snapshots,_,out=parse_bundle([("two-weights.csv",data)])
    assert not snapshots
    assert out[0]["status"]!="성공"


@pytest.mark.parametrize("key,wrong",[
    ("name","다른 ETF"),
    ("date","2026-11-09"),
])
def test_conflicting_labeled_preamble_cannot_override_row_identity(key,wrong):
    pre=[
        "ETF코드,487230,,,,,",
        "ETF상품명,"+("다른 ETF" if key=="name" else "합성 연구 ETF 487230")+",,,,,",
        "기준일,"+("2026-11-09" if key=="date" else "2026-11-10")+",,,,,",
    ]
    header="종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일"
    content=("\n".join([*pre,header,
        "005930,삼성전자,60,주식,487230,합성 연구 ETF 487230,2026-11-10",
        "000660,SK하이닉스,40,주식,487230,합성 연구 ETF 487230,2026-11-10",""])).encode("utf-8-sig")
    with pytest.raises(ValueError,match="충돌"):
        parse_holdings_auto(content,"preamble.csv")
    _,snapshots,_,_=parse_bundle([("preamble.csv",content)])
    assert not snapshots


def test_equivalent_date_formats_in_body_are_accepted():
    data=_data("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        "005930,삼성전자,60,주식,487230,합성 연구 ETF 487230,2026/11/10",
        "000660,SK하이닉스,40,주식,487230,합성 연구 ETF 487230,2026/11/10",
    ])
    frame, meta=parse_holdings_auto(data,"normalized-date.csv")
    assert meta["as_of_date"]=="2026-11-10"
    assert len(frame)==2


def test_future_reference_date_must_not_be_accepted():
    tomorrow=(date.today()+timedelta(days=1)).isoformat()
    assert date_value(tomorrow) is None


def test_alphanumeric_code_in_preamble_is_preserved():
    text="\n".join([
        "ETF코드,0193M0,,,,",
        "ETF상품명,혼합코드 연구 ETF,,,,",
        "기준일,2026-11-10,,,,",
        "종목코드,종목명,비중(%),자산유형,,",
        "005930,삼성전자,60,주식,,",
        "000660,SK하이닉스,40,주식,,",
    ])+"\n"
    df,meta=parse_holdings_auto(text.encode("utf-8-sig"),"alpha.csv")
    assert meta["etf_code"]=="0193M0"
    assert len(df)==2


def test_same_code_conflicting_names_rejected_in_nav_holdings():
    source=_data("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        "005930,삼성전자,50,주식,487230,합성 연구 ETF 487230,2026-11-10",
        "005930,다른회사,50,주식,487230,합성 연구 ETF 487230,2026-11-10",
    ])
    _,snaps,_,out=parse_bundle([("conflicting-name.csv",source)])
    assert not snaps
    assert out[0]["status"]!="성공"


def test_same_code_conflicting_names_rejected_in_krx_concentration():
    source=_data("종목코드,구성종목명,시가총액 구성비중",[
        "005930,삼성전자,50","005930,다른회사,50",
    ])
    _,snaps,_,out=parse_bundle([("bad-marketcap.csv",source)])
    assert not snaps
    assert out[0]["analysis_available"] is False
    assert "서로 다른 종목명" in out[0]["_standalone_stats"]["reason"]


def _xlsx(sheets):
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine="openpyxl") as writer:
        for name,data in sheets:
            data.to_excel(writer,index=False,sheet_name=name)
    return buf.getvalue()


def _holdings_dataframe(etfcode):
    return pd.DataFrame([
        {"종목코드":"005930","종목명":"삼성전자","비중(%)":60,"자산유형":"주식",
         "ETF코드":etfcode,"ETF상품명":f"합성 연구 ETF {etfcode}","기준일":"2026-11-10"},
        {"종목코드":"000660","종목명":"SK하이닉스","비중(%)":40,"자산유형":"주식",
         "ETF코드":etfcode,"ETF상품명":f"합성 연구 ETF {etfcode}","기준일":"2026-11-10"},
    ])


def test_catalog_and_holdings_sheets_in_one_workbook_both_processed():
    catalog=pd.DataFrame([{"종목코드":"487230","종목명":"합성 연구 ETF 487230",
                           "운용사":"가상운용사","기초지수":"가상지수"}])
    content=_xlsx([("ETF기본정보",catalog),("PCF",_holdings_dataframe("487230"))])
    found,snaps,_,result=parse_bundle([("combined.xlsx",content)])
    assert found["487230"]["name"]=="합성 연구 ETF 487230"
    assert "487230" in snaps
    assert len(result)==2
    assert all(row["status"]=="성공" for row in result)


def test_two_separate_holdings_sheets_are_not_silently_dropped():
    content=_xlsx([("PCF_A",_holdings_dataframe("487230")),
                   ("PCF_B",_holdings_dataframe("487231"))])
    _,snaps,_,reports=parse_bundle([("two-pcf.xlsx",content)])
    assert not snaps
    assert any("여러 개" in r["message"] for r in reports)


def test_catalog_conflicting_name_duplicate_is_reported():
    raw=_data("종목코드,종목명,운용사,기초지수",[
        "487230,첫번째 ETF,테스트운용사,테스트지수",
        "487230,두번째 ETF,테스트운용사,테스트지수",
    ])
    cat,snaps,_,result=parse_bundle([("conflict-catalog.csv",raw)])
    assert not cat and not snaps
    assert result[0]["category"]=="기본정보 검증 실패"


def test_actual_grade_reason_uses_triggered_threshold():
    frame=pd.DataFrame({
        "security_id":[f"{i:06d}" for i in range(1,7)],
        "security_name":[f"종목{i}" for i in range(6)],
        "weight_pct":[19,18,17,16,15,15],
        "asset_type":["주식"]*6,
    })
    stats=concentration(frame)
    assert stats["grade"]=="고집중"
    assert "상위 5개" in stats["grade_reason"]
    stat2=krx_component_concentration(frame)
    assert stat2["grade"]=="고집중"
    assert "상위 5개" in stat2["grade_reason"]


def test_exported_excel_never_injects_uploaded_formulas():
    source=_holding_rows()
    cat,snaps,_,_=parse_bundle([("test.csv",source)])
    cat["487230"]["name"]='=HYPERLINK("https://example.com","fake")'
    snaps["487230"]["frame"].loc[0,"security_name"]="=2+2"
    data=excel_report("487230",cat,snaps)
    book=load_workbook(BytesIO(data),read_only=False,data_only=False)
    assert not book._external_links
    all_cells=[cell for sheet in book.worksheets for row in sheet for cell in row]
    assert all(cell.data_type!="f" for cell in all_cells)
    assert any("HYPERLINK" in str(cell.value) for cell in all_cells)
