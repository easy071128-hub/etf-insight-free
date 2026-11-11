"""Streamlit smoke checks without a browser or production account."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_FILE=Path(__file__).resolve().parents[1] / "app.py"


def test_streamlit_starts_without_uploaded_files():
    app=AppTest.from_file(APP_FILE,default_timeout=30).run()
    assert not app.exception
    assert any("ETF Insight" in title.value for title in app.title)


def test_streamlit_displays_unlinked_krx_without_crashing():
    from etf_engine import parse_bundle
    content=("종목코드,구성종목명,시가총액 구성비중\n"
             "005930,삼성전자,60\n000660,SK하이닉스,40\n").encode("utf-8-sig")
    _,_,_,reports=parse_bundle([("marketcap.csv",content)])
    report=reports[0]
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["catalog"]={"091230":{"name":"TIGER 반도체","code":"091230","short_name":"TIGER 반도체"}}
    app.session_state["unlinked_reports"]={report["source_sha256"]:report}
    app.run()
    assert not app.exception
    assert any("KRX 시가총액" in item.value for item in app.subheader)


def test_manual_link_requires_explicit_code_and_confirmation():
    from etf_engine import parse_bundle
    content=("종목코드,구성종목명,시가총액 구성비중\n"
             "005930,삼성전자,60\n000660,SK하이닉스,40\n").encode("utf-8-sig")
    _,_,_,reports=parse_bundle([("marketcap.csv",content)])
    item=reports[0]
    source_id=item["source_sha256"]
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["catalog"]={
        "00000D":{"name":"TIGER NVDA-UST커버드콜","code":"00000D"},
        "091230":{"name":"TIGER 반도체","code":"091230"},
    }
    app.session_state["unlinked_reports"]={source_id:item}
    app.run()
    assert not app.exception
    assert app.text_input(key=f"ref_code_{source_id}").value == ""
    assert app.button(key=f"link_{source_id}").disabled

    app.text_input(key=f"ref_code_{source_id}").input("NOTREAL").run()
    assert not app.exception
    assert app.button(key=f"link_{source_id}").disabled

    app.text_input(key=f"ref_code_{source_id}").input("091230").run()
    assert not app.exception
    assert app.button(key=f"link_{source_id}").disabled
    app.checkbox(key=f"ref_confirm_{source_id}_091230").check().run()
    assert not app.exception
    assert not app.button(key=f"link_{source_id}").disabled


def test_reference_checkbox_resets_when_etf_code_changes():
    from etf_engine import parse_bundle
    content=("종목코드,구성종목명,시가총액 구성비중\n"
             "005930,삼성전자,60\n000660,SK하이닉스,40\n").encode("utf-8-sig")
    _,_,_,reports=parse_bundle([("marketcap.csv",content)])
    item=reports[0]
    source_id=item["source_sha256"]
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["catalog"]={
        "00000D":{"name":"TIGER NVDA-UST커버드콜","code":"00000D"},
        "091230":{"name":"TIGER 반도체","code":"091230"},
    }
    app.session_state["unlinked_reports"]={source_id:item}
    app.run()
    app.text_input(key=f"ref_code_{source_id}").input("091230").run()
    app.checkbox(key=f"ref_confirm_{source_id}_091230").check().run()
    assert not app.button(key=f"link_{source_id}").disabled
    app.text_input(key=f"ref_code_{source_id}").input("00000D").run()
    assert not app.exception
    assert app.button(key=f"link_{source_id}").disabled


def test_krx_pdf_evidence_candidate_is_visible_without_identity_link():
    from etf_engine import parse_bundle
    from reference_match import load_reference_fingerprints
    doc=next(x for x in load_reference_fingerprints() if x["etf_code"]=="091230")
    rows=[(x["security_id"],x["security_name"],x["weight_pct"]) for x in doc["holdings"]]
    rows += [(f"{900001+i:06d}",f"테스트기업{i}",1.71) for i in range(12)]
    content=("종목코드,구성종목명,시가총액 구성비중\n"+
             "".join(f"{code},{name},{weight}\n" for code,name,weight in rows)).encode("utf-8-sig")
    _, snapshots, _, reports=parse_bundle([("unlinked.csv",content)])
    assert not snapshots
    report=reports[0]
    assert report["identity"] is None
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["unlinked_reports"]={report["source_sha256"]:report}
    app.run()
    assert not app.exception
    assert any("TIGER 반도체" in item.value for item in app.success)
    assert not app.session_state["snapshots"]
    assert not app.session_state["reference_links"]


def test_new_analysis_clears_previous_manual_link_confirmations():
    from etf_engine import parse_bundle
    raw=("종목코드,구성종목명,시가총액 구성비중\n"
         "005930,삼성전자,60\n000660,SK하이닉스,40\n").encode("utf-8-sig")
    _,_,_,reports=parse_bundle([("marketcap.csv",raw)])
    result=reports[0]
    sha=result["source_sha256"]
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["catalog"]={"091230":{"name":"TIGER 반도체","code":"091230"}}
    app.session_state["unlinked_reports"]={sha:result}
    app.session_state[f"ref_code_{sha}"]="091230"
    app.session_state[f"ref_confirm_{sha}_091230"]=True
    app.run()
    assert not app.exception
    assert not app.button(key=f"link_{sha}").disabled
    reset=next(button for button in app.button if button.label=="새 분석 시작 (현재 세션 자료 삭제)")
    reset.click().run()
    assert not app.exception
    assert not app.session_state["reference_links"]
    assert f"ref_confirm_{sha}_091230" not in app.session_state
    assert f"ref_code_{sha}" not in app.session_state
