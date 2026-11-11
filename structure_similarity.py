"""Evidence-aware ETF similarity and explainable, NAV-based comparisons.

Scores are *research-model scores using user-supplied evidence*, not a
certified similarity, risk or investment recommendation. No missing component
is imputed, and incomplete scores are NEVER rescaled to 100.
"""
from __future__ import annotations

from math import isfinite

from etf_engine import candidate_etfs, comparison, concentration
from research_analysis import analyze_labeled_portfolio

WEIGHTS = {
    "세부 산업 구성": 40,
    "실제 편입종목": 25,
    "상위 5종목 집중도": 15,
    "국가 구성": 10,
    "기업집단 구성": 10,
}
DIMENSIONS = {
    "세부 산업 구성": "subsector",
    "국가 구성": "country",
    "기업집단 구성": "group",
}


def _date(snapshot):
    return str(snapshot.get("meta", {}).get("as_of_date") or "")


def _dist(exposure, dimension):
    """Retain genuine NAV percentages; cash/other gets its own shared bucket."""
    values = dict(exposure["breakdowns"][dimension])
    remainder = 100.0 - float(exposure["stock_weight_pct"])
    if remainder > 0.000001:
        values["비주식/기타"] = values.get("비주식/기타", 0.0) + remainder
    return values


def _distribution_score(a, b):
    """100 - total variation distance of two NAV-weight percentage vectors."""
    keys = set(a) | set(b)
    score = 100.0 - sum(abs(float(a.get(k, 0)) - float(b.get(k, 0)))
                        for k in keys) / 2.0
    return max(0.0, min(100.0, score))


def score_pair(a, b, metadata):
    """Calculate five research components and a score only with complete evidence.

    A full score requires independently identified ETF holdings, full metadata
    coverage in each of three dimensions and matching known holdings dates.
    The supplied label URLs are recorded but NOT independently authenticated.
    """
    comp = comparison(a, b)
    ca = concentration(a.get("frame"))
    cb = concentration(b.get("frame"))
    ea = analyze_labeled_portfolio(a, metadata)
    eb = analyze_labeled_portfolio(b, metadata)
    components = {}
    missing = []
    overlap = comp.get("overlap_pct")
    if overlap is not None and isfinite(float(overlap)):
        components["실제 편입종목"] = round(float(overlap), 4)
    else:
        missing.append("실제 편입종목: 두 ETF의 유효 NAV 비중 필요")
    if ca.get("available") and cb.get("available"):
        gap = abs(float(ca["top5_pct"]) - float(cb["top5_pct"]))
        components["상위 5종목 집중도"] = round(max(0.0, 100.0 - gap), 4)
    else:
        missing.append("상위 5종목 집중도: 유효 편입구조 필요")
    for label, dim in DIMENSIONS.items():
        if (ea.get("available") and eb.get("available")
                and ea["complete"].get(dim) and eb["complete"].get(dim)):
            components[label] = round(
                _distribution_score(_dist(ea, dim), _dist(eb, dim)), 4
            )
        else:
            missing.append(f"{label}: 양쪽 ETF의 종목별 분류 근거 100% 필요")
    date_a, date_b = _date(a), _date(b)
    same_date = bool(date_a and date_b and date_a == date_b)
    if not same_date:
        missing.append("편입 기준일: 두 ETF의 동일한 기준일 필요")
    complete = same_date and len(components) == len(WEIGHTS)
    score = (round(sum(components[k] * w for k, w in WEIGHTS.items()) / 100.0, 2)
             if complete else None)
    return {
        "overall_score": score,
        "status": ("5요소 점수 산출(사용자 제출 근거 기준·독립 인증 전)"
                   if complete else "정량 근거 일부 확인 · 종합점수 미산출"),
        "components": components,
        "weights": WEIGHTS.copy(),
        "missing": missing,
        "date_a": date_a or "미확인",
        "date_b": date_b or "미확인",
        "same_date": same_date,
        "overlap_pct": overlap,
        "source_note": "NAV 편입비중과 별도 업로드한 종목 분류표의 URL·기준일을 사용합니다. 원출처의 진위는 독립 검증되지 않았습니다.",
    }


def holdings_differences(a, b):
    """Use security codes, not names, to align holding weights and differences."""
    comp = comparison(a, b)
    if comp.get("overlap_pct") is None:
        return []
    def as_map(snapshot):
        rows = {}
        for r in snapshot["frame"].itertuples():
            code = str(r.security_id)
            item = rows.setdefault(code, {"name": str(r.security_name), "pct": 0.0})
            item["pct"] += float(r.weight_pct)
        total = sum(x["pct"] for x in rows.values())
        if total > 0:
            for item in rows.values():
                item["pct"] *= 100.0 / total
        return rows
    wa, wb = as_map(a), as_map(b)
    rows = []
    for code in sorted(set(wa) | set(wb)):
        av, bv = wa.get(code), wb.get(code)
        pa, pb = av["pct"] if av else 0.0, bv["pct"] if bv else 0.0
        rows.append({
            "종목코드": code, "종목명": (av or bv)["name"],
            "ETF A(%)": round(pa, 4), "ETF B(%)": round(pb, 4),
            "차이(%p)": round(pa - pb, 4),
            "구분": ("공통" if av and bv else ("A에만" if av else "B에만")),
        })
    return sorted(rows, key=lambda r: (-abs(r["차이(%p)"]), r["종목코드"]))


def research_candidates(code, catalog, snapshots, metadata, limit=5):
    """Rank evidenced structure first, keep weak title/index leads labelled."""
    if code not in catalog or limit < 1:
        return []
    old = {r["코드"]: dict(r)
           for r in candidate_etfs(code, catalog, snapshots, limit=len(catalog))}
    if code in snapshots:
        for other in snapshots:
            if other == code or other not in catalog:
                continue
            analysis = score_pair(snapshots[code], snapshots[other], metadata)
            sector_score = analysis["components"].get("세부 산업 구성")
            if other not in old and sector_score is not None and sector_score >= 80:
                old[other] = {
                    "코드": other,
                    "ETF 이름": catalog[other].get("short_name") or catalog[other]["name"],
                    "근거 수준": "세부 산업 구성 근거 확인",
                    "후보 근거": f"제출 근거 기준 세부 산업 구성 유사성 {sector_score:.1f}% (탐색 기준 80점 이상)",
                    "자료 상태": "기초 종목 분류 근거 기준 · 독립 검증 전",
                    "주의사항": "산업 구성이 비슷해도 보유종목·가격 변동 위험이 다를 수 있음",
                }
    output = []
    for other, row in old.items():
        score = (score_pair(snapshots[code], snapshots[other], metadata)
                 if code in snapshots and other in snapshots else None)
        row["5요소 연구 점수"] = score["overall_score"] if score else None
        row["실제 종목 중복비중(%)"] = score["overlap_pct"] if score else None
        row["비교 신뢰도"] = (score["status"] if score else
                         "기본정보 기반 검색 후보 · 실제 편입구조 미검증")
        if score:
            if not score["same_date"]:
                row["주의사항"] += " · ETF 편입자료 기준일 불일치 또는 미확인"
            if score["overall_score"] is not None:
                row["후보 근거"] += f" · 5요소 연구 점수 {score['overall_score']:.2f}/100"
            if score["missing"]:
                row["자료 상태"] += " · 누락: " + "; ".join(score["missing"][:3])
        priority = (3 if score and score["overall_score"] is not None
                    else 2 if score and score["overlap_pct"] is not None
                    else 1 if row["근거 수준"] == "세부 산업 구성 근거 확인"
                    else 0)
        metric = (row["5요소 연구 점수"] if priority == 3
                  else row["실제 종목 중복비중(%)"] if priority == 2
                  else (score["components"].get("세부 산업 구성", 0)
                        if score and priority == 1 else 0))
        output.append((priority, float(metric or 0), other, row))
    output.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[3] for item in output[:limit]]


def explain_pair(pair, differences, industry):
    """Neutral, templated beginner explanation; no price or risk prediction."""
    lines = []
    if pair["overlap_pct"] is not None:
        lines.append(f"두 ETF가 공통으로 보유한 종목의 최소 편입비중 합계는 {pair['overlap_pct']:.1f}%입니다. 이것은 수익률 상관계수가 아닙니다.")
    else:
        lines.append("두 ETF의 실제 보유종목 중복률은 확인할 수 없습니다.")
    if differences:
        largest = differences[0]
        lines.append(f"가장 큰 종목별 비중 차이는 {largest['종목명']}({largest['종목코드']})로 {abs(largest['차이(%p)']):.1f}%p입니다.")
    if industry.get("available"):
        parts = industry["comparisons"].get("subsector", [])
        if parts:
            largest = parts[0]
            lines.append(f"근거가 확인된 세부 산업 중 가장 큰 비중 차이는 {largest['산업']}({abs(largest['차이(%p)']):.1f}%p)입니다.")
    if pair["overall_score"] is None:
        lines.append("5요소 종합 유사도는 자료가 부족하거나 기준일이 달라 계산하지 않았습니다.")
    else:
        lines.append(f"제출한 근거표 기준 연구용 유사도는 {pair['overall_score']:.1f}점이며, 독립 검증된 투자 추천 점수는 아닙니다.")
    lines.append("종목 집중도만으로 어느 ETF가 더 안전하거나 수익률이 높다고 단정할 수 없습니다.")
    if not pair["same_date"]:
        lines.append(f"기준일: A {pair['date_a']}, B {pair['date_b']} — 동일 시점 비교가 아닙니다.")
    return " ".join(lines)
