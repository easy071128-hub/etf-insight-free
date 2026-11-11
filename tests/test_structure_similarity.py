"""Synthetic, explicitly non-market-data regression tests for research similarity."""
from __future__ import annotations

import pandas as pd
import pytest

from etf_engine import concentration, parse_bundle
from research_analysis import parse_company_evidence, compare_labeled_portfolios
from industry_taxonomy import taxonomy_rows
from structure_similarity import (
    WEIGHTS, score_pair, holdings_differences, research_candidates, explain_pair,
)


def csv(*rows):
    return ("\n".join(rows) + "\n").encode("utf-8-sig")


def fixture(date_b="2026-11-10"):
    holdings = [
        ("AAA001", "서로 다른 ETF 이름 A", "2026-11-10", 70, 30),
        ("BBB002", "서로 다른 ETF 이름 B", date_b, 60, 40),
    ]
    uploads = []
    for code, name, day, x, y in holdings:
        uploads.append((f"{code}.csv", csv(
            "종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",
            f"005930,가상기업A,{x},주식,{code},{name},{day}",
            f"000660,가상기업B,{y},주식,{code},{name},{day}",
        )))
    catalog, snaps, _, results = parse_bundle(uploads)
    assert all(r["status"] == "성공" for r in results), results
    labels, _ = parse_company_evidence(csv(
        "종목코드,종목명,섹터,세부산업,국가,기업집단,근거URL,기준일",
        "005930,가상기업A,반도체,DRAM,한국,A,https://example.org/a,2026-11-10",
        "000660,가상기업B,반도체,반도체 장비,한국,B,https://example.org/b,2026-11-10",
    ), "classifications.csv")
    return catalog, snaps, labels


def test_all_five_components_use_explicit_weights_and_no_imputation():
    cat, s, labels = fixture()
    result = score_pair(s["AAA001"], s["BBB002"], labels)
    assert sum(WEIGHTS.values()) == 100
    assert result["same_date"]
    assert result["missing"] == []
    assert result["components"] == {
        "세부 산업 구성": 90.0,
        "실제 편입종목": 90.0,
        "상위 5종목 집중도": 100.0,
        "국가 구성": 100.0,
        "기업집단 구성": 90.0,
    }
    assert result["overall_score"] == pytest.approx(92.5)


def test_a_portfolio_compared_to_itself_has_score_100():
    _, snapshots, labels = fixture()
    result = score_pair(snapshots["AAA001"], snapshots["AAA001"], labels)
    assert result["overall_score"] == pytest.approx(100.0)


def test_no_metadata_means_no_full_score_but_holdings_overlap_survives():
    _, s, _ = fixture()
    out = score_pair(s["AAA001"], s["BBB002"], {})
    assert out["overall_score"] is None
    assert out["components"]["실제 편입종목"] == pytest.approx(90)
    assert len(out["missing"]) >= 3


def test_missing_company_group_must_not_be_treated_as_zero():
    _, s, labels = fixture()
    labels["000660"]["group"] = ""
    out = score_pair(s["AAA001"], s["BBB002"], labels)
    assert out["overall_score"] is None
    assert "기업집단 구성" not in out["components"]
    assert any("기업집단" in part for part in out["missing"])


def test_different_holdings_dates_block_overall_even_with_full_evidence():
    _, s, labels = fixture(date_b="2026-11-11")
    out = score_pair(s["AAA001"], s["BBB002"], labels)
    assert out["overall_score"] is None
    assert not out["same_date"]
    assert any("편입 기준일" in part for part in out["missing"])


def test_future_relative_to_historical_holdings_blocks_sector():
    _, s, labels = fixture()
    s["AAA001"]["meta"]["as_of_date"] = "2026-11-09"
    out = score_pair(s["AAA001"], s["BBB002"], labels)
    assert out["overall_score"] is None
    assert "세부 산업 구성" not in out["components"]


def test_candidates_prioritize_actual_data_even_if_names_different():
    cat, snaps, labels = fixture()
    rows = research_candidates("AAA001", cat, snaps, labels)
    assert rows and rows[0]["코드"] == "BBB002"
    assert rows[0]["5요소 연구 점수"] == pytest.approx(92.5)
    assert "실제 종목 중복비중" in rows[0]


def test_name_only_candidates_do_not_get_a_numerical_score():
    cat = {
        "AAA001": {"name": "반도체 첫번째", "index_name": "연구 반도체"},
        "BBB002": {"name": "반도체 두번째", "index_name": "연구 반도체"},
    }
    out = research_candidates("AAA001", cat, {}, {})
    assert out and out[0]["5요소 연구 점수"] is None
    assert "기본정보 기반" in out[0]["비교 신뢰도"]


def test_exact_holdings_difference_and_explanation():
    _, s, labels = fixture()
    rows = holdings_differences(s["AAA001"], s["BBB002"])
    assert len(rows) == 2
    assert all(r["구분"] == "공통" for r in rows)
    assert all(abs(r["차이(%p)"]) == pytest.approx(10) for r in rows)
    pair = score_pair(s["AAA001"], s["BBB002"], labels)
    industry = compare_labeled_portfolios(s["AAA001"], s["BBB002"], labels)
    explanation = explain_pair(pair, rows, industry)
    assert "투자 추천 점수는 아닙니다" in explanation
    assert "90.0%" in explanation
    assert "세부 산업" in explanation


def test_single_20_percent_alert_is_separate_from_portfolio_grade():
    df = pd.DataFrame({
        "security_id": [f"{x:06d}" for x in range(9)],
        "security_name": [f"가상 {x}" for x in range(9)],
        "weight_pct": [20, 10, 10, 10, 10, 10, 10, 10, 10],
        "asset_type": ["주식"] * 9,
    })
    result = concentration(df)
    assert result["single_stock_flag"]
    assert result["grade"] == "집중"
    assert result["top5_pct"] == pytest.approx(60)
    assert result["stock_count"] == 9


def test_multibusiness_is_listed_but_never_automatically_split():
    rows = taxonomy_rows()
    assert any(row["대분류"] == "반도체" and "DRAM" in row["세부사업 예시"] for row in rows)
    assert any(row["대분류"] == "2차전지" and row["산업 가치사슬"] == "양극재" for row in rows)
    assert any("비중 미배분" in row["세부사업 예시"] for row in rows)


def test_repeated_scoring_is_deterministic():
    _, s, labels = fixture()
    outputs = [score_pair(s["AAA001"], s["BBB002"], labels) for _ in range(4)]
    assert outputs[1:] == outputs[:-1]


def test_explanation_does_not_predict_returns_or_safe_products():
    _, s, _ = fixture()
    pair = score_pair(s["AAA001"], s["BBB002"], {})
    text = explain_pair(pair, holdings_differences(s["AAA001"], s["BBB002"]),
                        {"available": False})
    assert "더 안전" in text
    assert "높다고 단정" in text
    assert "미산출" in text
