"""Read-only issuer-business overlay for unidentified KRX composition tables.

A KRX '시가총액 구성비중' table may contain public company codes without
proving which ETF owns them. This module adds source-backed *business labels*
to observed rows without enrolling an ETF holding or asserting NAV exposure.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

import pandas as pd
from etf_engine import krx_component_concentration, normal


def annotate_component_business(frame, weight_basis, metadata, *, as_of_date=None):
    """Return evidenced company matches and guarded time-compatible aggregates.

    No numeric company/sector exposure for an undated table: corporate sources
    might describe a business introduced *after* the unknown historical date.
    Matched weights are still shown strictly as original table observations.
    """
    fail = lambda reason: {
        "available": False, "reason": reason, "matches": [], "sector_distribution": {},
        "matched_count": 0, "dated_count": 0, "matched_table_pct": 0,
    }
    if weight_basis != "시가총액 기준 비중":
        return fail("KRX 시가총액 기준 구성비중에 한해서만 이 참고 분석을 표시합니다.")
    stats = krx_component_concentration(frame)
    if not stats.get("available"):
        return fail(stats.get("reason", "구성표의 비중이 검증되지 않았습니다."))
    try:
        effective_date = date.fromisoformat(str(as_of_date)) if as_of_date else None
    except ValueError:
        return fail("파일 내부의 구성 기준일을 검증할 수 없습니다.")
    total = float(stats["raw_total_pct"])
    # A cash/deposit row is not a business and cannot inherit a stock-code
    # classification even if an issuer reuses its display name.
    cash_names = {"원화현금", "외화현금", "설정현금액", "현금", "예수금",
                  "cash", "krwcash", "usdcash"}
    matches = []
    groups = defaultdict(float)
    dated_count = 0
    matched_weight = 0.0
    for row in frame.itertuples():
        code = str(row.security_id).strip()
        name = str(row.security_name).strip()
        if normal(name) in cash_names or str(row.asset_type) == "현금":
            continue
        label = (metadata or {}).get(code)
        if not label:
            continue
        # No issuer name reconciliation with ticker alone.
        if not name or normal(name) != normal(label.get("security_name","")):
            continue
        weight = float(row.weight_pct) * 100.0 / total
        matched_weight += weight
        valid_date = bool(effective_date
                          and date.fromisoformat(label["as_of_date"]) <= effective_date)
        if valid_date:
            dated_count += 1
            groups[str(label.get("sector") or "미확인")] += weight
        matches.append({
            "구성종목코드": code,
            "기업명": name,
            "원본 구성비중(정규화, %)": round(weight,4),
            "확인된 산업": str(label.get("sector") or "미확인"),
            "세부사업(기업활동)": str(label.get("subsector") or "미확인"),
            "분류 근거일": label["as_of_date"],
            "원본 기준일과 비교": (
                "날짜 충족" if valid_date else
                "원본 기준일 없음·소급 불가" if not effective_date else
                "근거일이 더 늦음·소급 불가"),
            "기업분류 근거": label["source_url"],
            "근거 검토": ("공식 기업자료 검토" if label.get("reviewed_on")
                       else "사용자 제출·독립검증 전"),
        })
    matches.sort(key=lambda r:(-r["원본 구성비중(정규화, %)"],r["구성종목코드"]))
    sector_distribution = (
        {name: round(value,4) for name,value in sorted(groups.items())}
        if effective_date else {}
    )
    return {
        "available": True, "reason": "", "matched_count": len(matches),
        "dated_count": dated_count,
        "matched_table_pct": round(matched_weight,4),
        "as_of_date": str(effective_date) if effective_date else None,
        "matches": matches,
        "sector_distribution": sector_distribution,
        "note": (
            "이것은 시가총액 기준 구성표에 포함된 개별 기업의 사업 근거입니다. "
            "ETF의 NAV 비중이나 투자수익률·세부사업별 금액을 뜻하지 않습니다. "
            "복합사업은 개별 사업에 강제 배분하지 않으며, 누락 기업을 0%로 처리하지 않습니다."
        ),
    }
