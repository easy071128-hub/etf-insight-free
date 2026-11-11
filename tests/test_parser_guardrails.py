"""Regression tests for KRX ingestion safety and comparison candidate limits."""
import pytest
from etf_engine import parse_bundle, candidate_etfs, concentration


def _csv(header, records):
    return ("\n".join([header, *records]) + "\n").encode("utf-8-sig")


@pytest.mark.parametrize("header", [
    "종목코드,구성종목명,시가총액 구성비중(%)",
    "종목코드,구성종목명,시가총액 구성비중",
])
def test_krx_marketcap_header_variants_are_standalone(header):
    data = _csv(header, ["005930,삼성전자,60", "000660,SK하이닉스,40"])
    catalog, snaps, seen, reports = parse_bundle([("krx.csv", data)])
    assert not catalog and not snaps
    assert reports[0]["status"] == "성공"
    assert reports[0]["weight_basis"] == "시가총액 기준 비중"
    assert reports[0]["_standalone_stats"]["top1_pct"] == pytest.approx(60)


def test_holdings_parenthesized_weight_header():
    data = _csv(
        "종목코드,종목명,편입비중(%),자산유형,ETF코드,ETF상품명,기준일",
        ["005930,삼성전자,60,주식,123456,검증용 ETF,2026-11-10",
         "000660,SK하이닉스,40,주식,123456,검증용 ETF,2026-11-10"],
    )
    _, snapshots, _, reports = parse_bundle([("holdings.csv", data)])
    assert reports[0]["status"] == "성공"
    assert concentration(snapshots["123456"]["frame"])["top1_pct"] == pytest.approx(60)


def test_conflicting_asset_type_same_code_is_rejected():
    data = _csv(
        "종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",
        ["005930,삼성전자,50,주식,123456,검증용 ETF,2026-11-10",
         "005930,삼성전자,50,현금,123456,검증용 ETF,2026-11-10"],
    )
    _, snapshots, _, reports = parse_bundle([("conflict.csv", data)])
    assert not snapshots
    assert reports[0]["status"] == "확인 필요"


def test_candidate_limit_defaults_to_five():
    catalog = {
        "123456": {"name": "테스트 반도체 ETF", "index_name": "반도체", "category": "테스트"}
    }
    for i in range(8):
        catalog[f"{i+200000:06d}"] = {
            "name": f"테스트 반도체 ETF {i}", "index_name": "반도체", "category": "테스트"
        }
    assert len(candidate_etfs("123456", catalog, {})) == 5


def test_unexpected_file_detection_error_is_isolated(monkeypatch):
    import etf_engine
    original = etf_engine._evidence_of_etf_list
    def faulty(content, filename):
        if filename == "failure.csv":
            raise RuntimeError("synthetic parser failure")
        return original(content, filename)
    monkeypatch.setattr(etf_engine, "_evidence_of_etf_list", faulty)
    valid = _csv(
        "종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",
        ["005930,삼성전자,100,주식,123456,검증용 ETF,2026-11-10"],
    )
    _, snapshots, _, reports = parse_bundle([
        ("failure.csv", valid), ("good.csv", valid),
    ])
    assert reports[0]["status"] == "오류"
    assert "123456" in snapshots
    assert reports[1]["status"] == "성공"
