"""KRX PDF evidence is a research cross-check, NOT proof of ETF NAV holdings."""
from io import BytesIO

import pandas as pd
import pytest

from etf_engine import excel_report_unlinked_krx, parse_bundle
from reference_match import load_reference_fingerprints, match_reference_candidates


TOP_TEN = [
    ("005930", "삼성전자", 19.24),
    ("000660", "SK하이닉스", 17.34),
    ("042700", "한미반도체", 10.91),
    ("036930", "주성엔지니어링", 7.86),
    ("222800", "심텍", 4.43),
    ("039030", "이오테크닉스", 4.41),
    ("000990", "DB하이텍", 4.24),
    ("240810", "원익IPS", 3.71),
    ("403870", "HPSP", 3.69),
    ("058470", "리노공업", 3.64),
]


def make_csv(*, changed_code=None, changed_weight=None, changed_name=None):
    rows = TOP_TEN[:]
    if changed_code:
        rows[0] = ("999999", rows[0][1], rows[0][2])
    if changed_weight:
        rows[0] = (rows[0][0], rows[0][1], rows[0][2] - 0.10)
    if changed_name:
        rows[0] = (rows[0][0], "다른회사", rows[0][2])
    other = [(f"{900001+i:06d}", f"참고용 테스트 종목{i}", 1.71) for i in range(12)]
    if changed_weight:
        other[0] = (other[0][0], other[0][1], 1.81)
    all_rows = rows + other
    raw = "종목코드,구성종목명,시가총액 구성비중\n"
    raw += "".join(f"{code},{name},{weight}\n" for code,name,weight in all_rows)
    return raw.encode("utf-8-sig")


def parse(raw=None):
    catalog, snapshots, seen, outcomes = parse_bundle(
        [("no_identity.csv", make_csv() if raw is None else raw)]
    )
    assert not catalog and not snapshots
    report=outcomes[0]
    assert report["analysis_available"]
    assert report["_standalone_frame"] is not None
    return report


def test_curated_pdf_reference_tracks_source_and_incomplete_scope():
    fingerprints = load_reference_fingerprints()
    assert len(fingerprints) >= 1
    ref = next(x for x in fingerprints if x["etf_code"]=="091230")
    assert ref["source_sha256"]=="5b2f1275715bb086380f8fa008e2f9f6e661970f6e7119c60a1f94befc27e1d5"
    assert ref["holdings_as_of_date"] is None
    assert len(ref["holdings"])==10
    assert sum(x["weight_pct"] for x in ref["holdings"])==pytest.approx(79.47)


def test_exact_ten_match_produces_nonbinding_identity_candidate_only():
    r=parse()
    matches=match_reference_candidates(r["_standalone_frame"],r["weight_basis"])
    assert len(matches)==1
    candidate=matches[0]
    assert candidate["etf_code"]=="091230"
    assert candidate["etf_name"]=="TIGER 반도체"
    assert candidate["matched_rows"]==10
    assert candidate["matched_weight_pct"]==pytest.approx(79.47)
    assert candidate["holdings_as_of_date"] is None
    assert "미검증" in candidate["verification_status"]
    assert r["identity"] is None  # No authoritative identity in Excel.
    assert r["_standalone_stats"]["raw_total_pct"]==pytest.approx(99.99)


@pytest.mark.parametrize("change",["changed_code","changed_weight","changed_name"])
def test_any_identification_or_weight_mismatch_blocks_candidate(change):
    report=parse(make_csv(**{change:True}))
    assert match_reference_candidates(report["_standalone_frame"],report["weight_basis"])==[]


def test_missing_one_of_ten_blocks_cross_document_candidate():
    frame=parse()["_standalone_frame"].copy()
    frame=frame[frame.security_id!="005930"]
    assert match_reference_candidates(frame,"시가총액 기준 비중")==[]


def test_reference_requires_marketcap_basis():
    frame=parse()["_standalone_frame"]
    assert match_reference_candidates(frame,"ETF 편입비중(원본 표기)")==[]


def test_duplicate_security_code_blocks_reference():
    frame=parse()["_standalone_frame"].copy()
    frame.loc[frame.index[-1],"security_id"]=frame.loc[frame.index[0],"security_id"]
    assert match_reference_candidates(frame,"시가총액 기준 비중")==[]


def test_excel_export_preserves_evidence_but_not_nav_attribution():
    report=parse()
    report["evidence_candidates"]=match_reference_candidates(
        report["_standalone_frame"],report["weight_basis"]
    )
    binary=excel_report_unlinked_krx(report)
    sheet=pd.read_excel(BytesIO(binary),sheet_name="분석요약")
    values=dict(zip(sheet["항목"],sheet["결과"]))
    assert values["자료 구분"].startswith("KRX 시가총액 구성비중")
    assert "091230" in str(values["PDF 교차대조 후보 1"])
    assert values["교차대조 확인 종목 1"]=="10개 / 비중 합계 79.47%"
    assert "미검증" in values["교차대조 한계 1"]
    assert values["참고 ETF 코드"]=="원본에서 미확인"
