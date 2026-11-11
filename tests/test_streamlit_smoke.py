"""Streamlit smoke checks without a browser or production account."""
from streamlit.testing.v1 import AppTest


def test_streamlit_starts_without_uploaded_files():
    app=AppTest.from_file("app.py",default_timeout=30).run()
    assert not app.exception
    assert any("ETF Insight" in title.value for title in app.title)


def test_streamlit_displays_unlinked_krx_without_crashing():
    from etf_engine import parse_bundle
    content=("종목코드,구성종목명,시가총액 구성비중\n"
             "005930,삼성전자,60\n000660,SK하이닉스,40\n").encode("utf-8-sig")
    _,_,_,reports=parse_bundle([("marketcap.csv",content)])
    report=reports[0]
    app=AppTest.from_file("app.py",default_timeout=30)
    app.session_state["catalog"]={"091230":{"name":"TIGER 반도체","code":"091230","short_name":"TIGER 반도체"}}
    app.session_state["unlinked_reports"]={report["source_sha256"]:report}
    app.run()
    assert not app.exception
    assert any("KRX 시가총액" in item.value for item in app.subheader)
