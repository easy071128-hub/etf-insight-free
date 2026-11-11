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


def test_removed_research_upload_clears_stale_labels():
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["research_meta"]={"005930":{"sector":"반도체"}}
    app.session_state["research_source"]={"source_file":"old.csv"}
    app.session_state["research_signature"]="abc123"
    app.run()
    assert not app.exception
    assert not app.session_state["research_meta"]
    assert app.session_state["research_source"] is None
    assert app.session_state["research_signature"] is None


def test_sector_analysis_visible_only_with_complete_nav_and_documented_labels():
    from etf_engine import parse_bundle
    from research_analysis import parse_company_evidence
    hold=("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일\n"
          "005930,삼성전자,75,주식,091230,TIGER 반도체,2026-11-10\n"
          "000660,SK하이닉스,25,주식,091230,TIGER 반도체,2026-11-10\n").encode("utf-8-sig")
    proof=("종목코드,종목명,섹터,세부산업,국가,기업집단,근거URL,기준일\n"
           "005930,삼성전자,반도체,메모리,한국,삼성,https://example.org/a,2026-11-10\n"
           "000660,SK하이닉스,2차전지,양극재,한국,SK,https://example.org/b,2026-11-10\n").encode("utf-8-sig")
    catalog,snaps,_,_=parse_bundle([("hold.csv",hold)])
    metadata,source=parse_company_evidence(proof,"proof.csv")
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["catalog"]=catalog
    app.session_state["snapshots"]=snaps
    app.session_state["research_meta"]=metadata
    app.session_state["research_source"]=source
    app.run()
    assert not app.exception
    assert any("상품명과 투자구조의 일치 여부" in item.value for item in app.subheader)
    assert any(item.label=="섹터 집중도" for item in app.metric)


def test_two_krx_unlinked_files_show_direct_comparison_in_ui():
    from etf_engine import parse_bundle
    def csv(rows):
        return ("종목코드,구성종목명,시가총액 구성비중\n" +
                "".join(f"{code},{name},{weight}\n" for code,name,weight in rows)).encode("utf-8-sig")
    a=csv([("005930","삼성전자",60),("000660","SK하이닉스",40)])
    b=csv([("005930","삼성전자",50),("042700","한미반도체",50)])
    _,snapshots,_,reports=parse_bundle([("A.csv",a),("B.csv",b)])
    assert not snapshots
    app=AppTest.from_file(APP_FILE,default_timeout=30)
    app.session_state["unlinked_reports"]={r["source_sha256"]:r for r in reports}
    app.run()
    assert not app.exception
    assert any("KRX 구성비중표 2개 직접 비교" in x.value for x in app.subheader)
    assert any(x.label=="공통 비현금 구성비중" for x in app.metric)


def test_public_site_search_catalog_preloads_all_1190_etfs():
    app=AppTest.from_file(APP_FILE,default_timeout=40).run()
    assert not app.exception
    assert len(app.session_state["catalog"])==1190
    assert "091230" in app.session_state["catalog"]
    assert "0193M0" in app.session_state["catalog"]
    assert not app.session_state["snapshots"]
    assert any("1,190" in item.value for item in app.caption)
