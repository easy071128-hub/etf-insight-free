"""No synthetic input must be attributed to a real ETF by name alone."""
from pathlib import Path

from etf_engine import parse_bundle
from upload_diagnostics import describe_upload, describe_batch, plain_text_diagnostics


def csv(*lines):
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


def test_marketcap_table_can_calculate_only_unlinked_component_structure():
    raw = csv(
        "종목코드,구성종목명,주식수(계약수),평가금액,시가총액,시가총액 구성비중",
        "005930,가상기업A,10,10000,11000,60",
        "000660,가상기업B,20,20000,22000,40",
    )
    _, snaps, _, reports = parse_bundle([("data_2340_20261112.csv", raw)])
    assert not snaps
    result = describe_upload(reports[0])
    assert result["구성항목"] == 2
    assert result["수치 비중"] == 2
    assert "ETF 실제 NAV 노출 아님" in result["분석 가능 범위"]
    assert "ETF 코드·기준일" in result["다음에 필요한 것"]
    assert result["원출처 검증"] == "미완료"


def test_missing_marketcap_weights_are_not_invented_from_quantity_or_price():
    raw = csv(
        "종목코드,구성종목명,주식수(계약수),평가금액,시가총액,시가총액 구성비중",
        "US88579Y1010,가상회사A,7.41,-,-,-",
        "US0028241000,가상회사B,24.85,-,-,-",
    )
    _, snapshots, _, reports = parse_bundle([("data_2308_20261112.csv", raw)])
    assert not snapshots
    result = describe_batch(reports)[0]
    assert result["구성항목"] == 2
    assert result["수치 비중"] == 0
    assert "집중도·유사도 미산출" in result["분석 가능 범위"]
    assert "수량·평가금액으로 비중 추정 금지" in result["다음에 필요한 것"]


def test_nav_labeled_upload_remains_unverified():
    raw = csv(
        "종목코드,종목명,NAV 편입비중(%),자산유형,ETF코드,ETF상품명,기준일",
        "005930,가상기업A,60,주식,487230,연구용ETF,2026-11-10",
        "000660,가상기업B,40,주식,487230,연구용ETF,2026-11-10",
    )
    _, snapshots, _, reports = parse_bundle([("NAV.csv", raw)])
    result = describe_batch(reports, snapshots)[0]
    assert result["구성항목"] == 2
    assert "업로드 파일에서 NAV 비중이라고 표기됨" in result["분석 가능 범위"]
    assert result["원출처 검증"] == "미완료"


def test_duplicates_and_empty_report_are_handled():
    assert describe_batch([]) == []
    duplicate = describe_upload({"file": "same.csv", "status": "중복"})
    assert duplicate["다음에 필요한 것"] == "추가 업로드 불필요"
    raw = plain_text_diagnostics([{"file": "name.csv", "status": "확인 필요"}])
    assert raw.startswith(b"\xef\xbb\xbf")
    txt = raw.decode("utf-8-sig")
    assert "name.csv" in txt
    assert "원출처 검증: 미완료" in txt


def test_pdf_document_is_not_confused_with_pcf_excel_data():
    row = describe_upload({"file": "document.pdf", "status": "확인 필요", "kind": "PDF"})
    assert ".pdf 문서와 다름" in row["다음에 필요한 것"]
    assert row["분석 가능 범위"] == "PDF 문서 자동 표 추출 미지원"


def test_app_renders_upload_guidance_without_browser():
    from streamlit.testing.v1 import AppTest
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(root / "app.py", default_timeout=30)
    app.session_state["upload_results"] = [{
        "file": "missing_weights.csv", "status": "확인 필요",
        "kind": "미연결 구성종목", "holding_count": 2,
        "valid_weights": 0, "weight_available": False,
        "analysis_available": False, "message": "비중 미제공",
    }]
    app.run()
    assert not app.exception
    assert any("파일별 분석 가능 범위" in x.value for x in app.subheader)
