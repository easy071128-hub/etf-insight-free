"""Evidence-safety regression tests. Inputs are synthetic, NOT official holdings."""
from __future__ import annotations

import pandas as pd
import pytest

from etf_engine import (
    candidate_etfs,
    compare_krx_component_tables,
    manual_krx_reference,
    parse_bundle,
)
from reference_match import load_reference_fingerprints
from structure_similarity import (
    explain_pair, holdings_differences, research_candidates, score_pair,
)


def _csv(*rows):
    return ("\n".join(rows) + "\n").encode("utf-8-sig")


CATALOG = {
    "091230": {"code": "091230", "name": "TIGER 반도체"},
    "999999": {"code": "999999", "name": "임의 ETF"},
}


def _unlinked(rows):
    raw = _csv("종목코드,구성종목명,시가총액 구성비중", *rows)
    _, snapshots, _, result = parse_bundle([("unknown.csv", raw)], catalog=CATALOG)
    assert not snapshots and result[0]["analysis_available"]
    return result[0]


def _snapshot(day="2026-11-10", *, nav=True, pcf=False):
    frame = pd.DataFrame({
        "security_id": ["005930", "000660"],
        "security_name": ["가상기업1", "가상기업2"],
        "asset_type": ["주식", "주식"],
        "weight_pct": [60.0, 40.0],
    })
    return {
        "frame": frame,
        "meta": {
            "as_of_date": day,
            "nav_basis_claimed": nav,
            "pcf_context_detected": pcf,
        },
    }


def test_public_reference_gate_rejects_unidentified_etf_without_pdf_agreement():
    report = _unlinked(["005930,삼성전자,60", "000660,SK하이닉스,40"])
    with pytest.raises(ValueError, match="교차|PDF"):
        manual_krx_reference(report, CATALOG, "091230", require_crosscheck=True)
    assert report["identity"] is None


def test_matching_pdf_fingerprint_allows_display_only_reference_not_nav():
    record = next(r for r in load_reference_fingerprints() if r["etf_code"] == "091230")
    rows = [
        f'{r["security_id"]},{r["security_name"]},{r["weight_pct"]}'
        for r in record["holdings"]
    ]
    remaining = round(100.0 - sum(float(r["weight_pct"]) for r in record["holdings"]), 2)
    fillers = [1.71] * 11
    fillers.append(round(remaining - sum(fillers), 2))
    rows.extend(f"{900001+i:06d},가상종목{i},{w}" for i, w in enumerate(fillers))
    report = _unlinked(rows)

    with pytest.raises(ValueError, match="충돌"):
        manual_krx_reference(report, CATALOG, "999999", require_crosscheck=True)
    label = manual_krx_reference(report, CATALOG, "091230", require_crosscheck=True)
    assert label["etf_code"] == "091230"
    assert label["verified"] is False
    assert label["as_of_date"] is None


@pytest.mark.parametrize("a,b", [
    (_snapshot(nav=False), _snapshot()),
    (_snapshot(pcf=True), _snapshot()),
    (_snapshot(), _snapshot(day="2026-11-11")),
])
def test_candidate_discovery_never_uses_noncomparable_nav_overlap(a, b):
    catalog = {
        "AAA001": {"name": "가상알파", "index_name": ""},
        "BBB002": {"name": "별개베타", "index_name": ""},
    }
    assert candidate_etfs("AAA001", catalog, {"AAA001": a, "BBB002": b}) == []


def test_candidate_discovery_can_use_same_date_declared_nav_overlap():
    catalog = {
        "AAA001": {"name": "가상알파", "index_name": ""},
        "BBB002": {"name": "별개베타", "index_name": ""},
    }
    results = candidate_etfs(
        "AAA001", catalog, {"AAA001": _snapshot(), "BBB002": _snapshot()})
    assert len(results) == 1
    assert results[0]["근거 수준"] == "실제 편입종목 중복비중 높음"
    assert "NAV" in results[0]["후보 근거"]


def test_research_candidates_do_not_rank_or_display_cross_date_overlap():
    catalog = {
        "AAA001": {"name": "동일 반도체 A", "index_name": "합성 반도체"},
        "BBB002": {"name": "동일 반도체 B", "index_name": "합성 반도체"},
    }
    a, b = _snapshot(), _snapshot(day="2026-11-11")
    candidates = research_candidates("AAA001", catalog, {"AAA001": a, "BBB002": b}, {})
    assert candidates
    assert candidates[0]["실제 종목 중복비중(%)"] is None
    assert "날짜" in candidates[0]["자료 상태"]

    pair = score_pair(a, b, {})
    assert holdings_differences(a, b) == []
    explanation = explain_pair(pair, [], {"available": False})
    assert "기준일이 달라" in explanation
    assert "100.0%" not in explanation


def test_cross_file_security_id_name_conflict_is_not_counted_as_common_stock():
    a = _unlinked(["005930,삼성전자,60", "000660,SK하이닉스,40"])
    b = _unlinked(["005930,동명이종목,60", "000660,SK하이닉스,40"])
    result = compare_krx_component_tables(a, b)
    assert result["available"] is False
    assert "005930" in result["reason"]
