"""Reference association is a display hint, not proof of ETF NAV weights."""
from io import BytesIO

import pandas as pd
import pytest

from etf_engine import (
    excel_report_unlinked_krx, manual_krx_reference, parse_bundle
)


def _csv(header, rows):
    return ("\n".join([header, *rows]) + "\n").encode("utf-8-sig")


IDENTIFIED_HEADER="ETF코드,ETF상품명,기준일,종목코드,구성종목명,시가총액 구성비중"
UNLABELED_HEADER="종목코드,구성종목명,시가총액 구성비중"
CATALOG={"091230":{"name":"TIGER 반도체","code":"091230","short_name":"TIGER 반도체"}}


def test_original_identifier_is_used_only_as_reference():
    raw=_csv(IDENTIFIED_HEADER, [
        "091230,TIGER 반도체,2026-11-11,005930,삼성전자,60",
        "091230,TIGER 반도체,2026-11-11,000660,SK하이닉스,40",
    ])
    catalog,snaps,_,r=parse_bundle([("krx.csv",raw)],catalog=CATALOG)
    assert not snaps
    assert r[0]["analysis_available"]
    identity=r[0]["identity"]
    assert identity["etf_code"]=="091230"
    assert identity["etf_name"]=="TIGER 반도체"
    assert identity["as_of_date"]=="2026-11-11"
    assert identity["status"].startswith("원본 내부")
    assert identity["verified"] is False
    assert r[0]["_standalone_stats"]["top1_pct"]==pytest.approx(60)


def test_code_only_matches_known_catalog_without_inventing_date():
    raw=_csv("ETF코드,종목코드,구성종목명,시가총액 구성비중",[
        "091230,005930,삼성전자,60",
        "091230,000660,SK하이닉스,40",
    ])
    _,snaps,_,r=parse_bundle([("krx.csv",raw)],catalog=CATALOG)
    assert not snaps
    assert r[0]["identity"]["etf_name"]=="TIGER 반도체"
    assert r[0]["identity"]["as_of_date"] is None


def test_missing_identifier_remains_unlinked_even_with_catalog():
    raw=_csv(UNLABELED_HEADER,["005930,삼성전자,60","000660,SK하이닉스,40"])
    _,snaps,_,r=parse_bundle([("data_5705_20261111.csv",raw)],catalog=CATALOG)
    assert not snaps
    assert r[0]["identity"] is None
    assert r[0]["analysis_available"]
    assert r[0]["_standalone_stats"]["raw_total_pct"]==pytest.approx(100)


def test_manual_label_does_not_register_portfolio_or_date():
    raw=_csv(UNLABELED_HEADER,["005930,삼성전자,60","000660,SK하이닉스,40"])
    _,snaps,_,r=parse_bundle([("no_etf_id.csv",raw)],catalog=CATALOG)
    label=manual_krx_reference(r[0],CATALOG,"091230")
    assert label["etf_code"]=="091230"
    assert label["verified"] is False
    assert label["as_of_date"] is None
    assert not snaps
    exported=excel_report_unlinked_krx({**r[0],"reference_identity":label})
    summary=pd.read_excel(BytesIO(exported),sheet_name="분석요약")
    fields=dict(zip(summary["항목"],summary["결과"]))
    assert fields["참고 ETF 코드"]==91230 or str(fields["참고 ETF 코드"])=="091230"
    assert "사용자 지정" in fields["참고 정보의 출처"]
    assert "ETF 순자산" in fields["참고 연결 한계"]


def test_file_preamble_explicit_etf_metadata_is_respected():
    data=_csv("a,b,c,d",[
        "ETF코드,091230,,",
        "ETF상품명,TIGER 반도체,,",
        "기준일,2026-11-11,,",
        "종목코드,구성종목명,시가총액 구성비중,",
        "005930,삼성전자,60,",
        "000660,SK하이닉스,40,",
    ])
    _,snaps,_,r=parse_bundle([("with_preamble.csv",data)],catalog=CATALOG)
    assert not snaps
    assert r[0]["identity"]["etf_code"]=="091230"
    assert r[0]["identity"]["as_of_date"]=="2026-11-11"


def test_conflicting_etf_codes_never_autolink_or_manual_override():
    raw=_csv(IDENTIFIED_HEADER,[
        "091230,TIGER 반도체,2026-11-11,005930,삼성전자,60",
        "091231,TIGER 반도체,2026-11-11,000660,SK하이닉스,40",
    ])
    _,snaps,_,r=parse_bundle([("conflict.csv",raw)],catalog=CATALOG)
    assert not snaps
    assert r[0]["identity"] is None
    assert "상충" in r[0]["identity_issue"]
    with pytest.raises(ValueError):
        manual_krx_reference(r[0],CATALOG,"091230")


def test_catalog_name_conflict_blocks_reference():
    raw=_csv(IDENTIFIED_HEADER,[
        "091230,다른 ETF,2026-11-11,005930,삼성전자,60",
        "091230,다른 ETF,2026-11-11,000660,SK하이닉스,40",
    ])
    _,snaps,_,r=parse_bundle([("conflict.csv",raw)],catalog=CATALOG)
    assert not snaps
    assert r[0]["identity"] is None
    assert "충돌" in r[0]["identity_issue"]


def test_manual_reference_rejects_unregistered_code():
    raw=_csv(UNLABELED_HEADER,["005930,삼성전자,60","000660,SK하이닉스,40"])
    _,_,_,r=parse_bundle([("unlinked.csv",raw)])
    with pytest.raises(ValueError,match="없는 코드"):
        manual_krx_reference(r[0],CATALOG,"999999")


def test_manual_reference_rejects_partial_or_missing_weights():
    raw=_csv(UNLABELED_HEADER,["005930,삼성전자,-","000660,SK하이닉스,-"])
    _,_,_,r=parse_bundle([("missing.csv",raw)],catalog=CATALOG)
    assert r[0]["identity"] is None
    with pytest.raises(ValueError,match="검증된"):
        manual_krx_reference(r[0],CATALOG,"091230")
