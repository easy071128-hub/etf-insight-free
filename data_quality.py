"""Conservative, reproducible ETF data readiness audit.

The public bundled catalog is NOT evidence of NAV holdings. Uploaded NAV-labelled
columns and user-supplied evidence URLs are NOT independently authenticated.
No publisher verification is inferred from a URL, a file name or weight totals.
"""
from __future__ import annotations

from io import BytesIO
from math import isfinite

import pandas as pd

from etf_engine import concentration
from research_analysis import analyze_labeled_portfolio


LEVELS = ("기본정보만 확인", "자료부족", "일부 분석 가능", "분석 가능(제출 근거 기준)")


def _literal(value):
    """Prevent spreadsheet formula/URL interpretation of user-controlled text."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def review_etf(code, catalog_item, snapshot=None, company_evidence=None):
    """Explain exactly which research operations are supported for one ETF.

    '분석 가능' means a calculation on *submitted* evidence, not an official
    independently verified portfolio. The audit never marks an uploader's
    source URL as verified by the publisher.
    """
    result = {
        "code": str(code),
        "name": str((catalog_item or {}).get("short_name") or (catalog_item or {}).get("name") or ""),
        "level": LEVELS[0],
        "has_catalog": catalog_item is not None,
        "holdings_loaded": False,
        "concentration_calculable": False,
        "nav_label_present": False,
        "nav_source_independently_verified": False,
        "company_source_independently_verified": False,
        "full_sector_classification": False,
        "full_subsector_classification": False,
        "full_country_classification": False,
        "full_group_classification": False,
        "quantitative_pair_ready": False,
        "as_of_date": "",
        "weight_basis": "편입비중 없음",
        "holding_rows": 0,
        "sector_coverage_pct": None,
        "subsector_coverage_pct": None,
        "country_coverage_pct": None,
        "group_coverage_pct": None,
        "source_sha256": "",
        "notes": ["실제 ETF 구성종목과 비중 파일이 등록되지 않았습니다."],
    }
    if snapshot is None:
        return result

    frame = snapshot.get("frame")
    meta = snapshot.get("meta") or {}
    result.update(
        holdings_loaded=True,
        as_of_date=str(meta.get("as_of_date") or ""),
        weight_basis=str(meta.get("weight_basis") or "비중 기준 미확인"),
        source_sha256=str(snapshot.get("sha256") or ""),
        holding_rows=len(frame) if frame is not None else 0,
    )
    stats = concentration(frame)
    if not stats.get("available"):
        result["level"] = LEVELS[1]
        result["notes"] = [str(stats.get("reason") or "유효한 구성비중이 없습니다.")]
        return result

    result["concentration_calculable"] = True
    result["level"] = LEVELS[2]
    issues = ["원본의 ETF 식별·비중 합계는 프로그램이 검증했지만 제공기관 원출처는 독립 인증되지 않았습니다."]
    if not result["as_of_date"]:
        issues.append("ETF 편입 기준일을 확인할 수 없습니다.")
    is_nav = bool(meta.get("nav_basis_claimed") and not meta.get("pcf_context_detected"))
    result["nav_label_present"] = is_nav
    if not is_nav:
        issues.append("NAV 편입비중 근거가 확인되지 않아 산업별 NAV 노출과 정량 유사도는 미산출입니다.")
        result["notes"] = issues
        return result

    # URLs and dates typed into an uploaded file are provenance hints, not
    # independently corroborated corporate filings.
    evidence = analyze_labeled_portfolio(snapshot, company_evidence or {})
    if not evidence.get("available"):
        issues.append(str(evidence.get("reason") or "기업 분류자료가 없습니다."))
        result["notes"] = issues
        return result
    for dim in ("sector", "subsector", "country", "group"):
        result[f"full_{dim}_classification"] = bool(evidence["complete"].get(dim))
        val = evidence["coverage_pct"].get(dim)
        result[f"{dim}_coverage_pct"] = round(float(val), 4) if val is not None and isfinite(float(val)) else None
        if not evidence["complete"].get(dim):
            issues.append({
                "sector": "주요 섹터", "subsector": "세부 산업",
                "country": "국가", "group": "기업집단",
            }[dim] + "의 편입종목 분류 근거가 일부 누락되었습니다.")

    if all(result[f"full_{dim}_classification"] for dim in ("sector", "subsector", "country", "group")):
        result["level"] = LEVELS[3]
        # Pairwise eligibility depends additionally on a *second* ETF with
        # the same dated, valid holdings; never assert it from one snapshot.
        result["quantitative_pair_ready"] = False
        issues.append("5요소 종합점수는 동일 기준일의 다른 ETF 및 추가 비교 검증 후에만 산출할 수 있습니다.")
    else:
        issues.append("분류 누락 부분을 0%로 가정하거나 다른 지표로 대체하지 않습니다.")

    issues.append("내장 기업 분류는 공식 기업자료에서 검토한 사업 정보이며, 사용자 추가 URL은 별도 인증되지 않았습니다. 이 근거를 ETF 전체 NAV 비중 또는 사업별 노출로 승격할 수 없습니다.")
    result["notes"] = issues
    return result


def build_readiness_audit(catalog, snapshots=None, company_evidence=None, catalog_provenance=None):
    """One row per ETF, keeping every catalog item even without holdings."""
    snapshots = snapshots or {}
    company_evidence = company_evidence or {}
    catalog = catalog or {}
    rows = []
    for code in sorted(set(catalog) | set(snapshots)):
        rows.append(review_etf(code, catalog.get(code), snapshots.get(code), company_evidence))
    counts = {
        "기본 ETF 수": len(catalog),
        "실제 구성종목 등록 ETF 수(사용자 세션)": sum(row["holdings_loaded"] for row in rows),
        "유효 종목 집중도 산출 가능 ETF 수": sum(row["concentration_calculable"] for row in rows),
        "NAV 비중 표시가 있는 ETF 수(독립 검증 전)": sum(row["nav_label_present"] for row in rows),
        "세부 산업 분류 100% 확보 ETF 수(사용자 근거)": sum(row["full_subsector_classification"] for row in rows),
        "제출 근거 기준 구조 분석 가능 ETF 수": sum(row["level"] == LEVELS[3] for row in rows),
        "공식 NAV 원출처 독립 검증 완료 ETF 수": 0,
        "공식 기업 분류 원출처 독립 검증 완료 ETF 수": 0,
    }
    provenance = catalog_provenance or {}
    return {
        "counts": counts,
        "rows": rows,
        "catalog_source_url": provenance.get("source_url", "미확인"),
        "catalog_date": provenance.get("as_of_date", "미확인"),
        "catalog_rights": provenance.get("rights_status", "재배포 권한 확인되지 않음"),
        "limitations": (
            "사이트 내장 목록은 ETF 기본정보이며 NAV 구성종목이 아닙니다. "
            "세션 업로드는 사용자 제출 자료입니다. 비중 열 표기와 기업 분류 URL만으로 "
            "원출처 인증·전체 편입항목 완전성·공개 재배포 허가를 확정할 수 없습니다."
        ),
    }


def excel_readiness_audit(audit):
    """Produce a session-only audit workbook; never package source KRX rows."""
    fields = [
        ("ETF 코드", "code"), ("ETF 상품명", "name"), ("분석 상태", "level"),
        ("구성종목 파일 여부", "holdings_loaded"),
        ("종목 집중도 산출 가능", "concentration_calculable"),
        ("NAV 열 표기 확인", "nav_label_present"),
        ("NAV 원출처 독립검증", "nav_source_independently_verified"),
        ("섹터 근거 100%", "full_sector_classification"),
        ("세부산업 근거 100%", "full_subsector_classification"),
        ("국가 근거 100%", "full_country_classification"),
        ("기업집단 근거 100%", "full_group_classification"),
        ("편입 기준일", "as_of_date"), ("비중 종류", "weight_basis"),
        ("구성항목 수", "holding_rows"), ("원본 SHA256", "source_sha256"),
        ("섹터 근거율(%)", "sector_coverage_pct"),
        ("세부산업 근거율(%)", "subsector_coverage_pct"),
        ("국가 근거율(%)", "country_coverage_pct"),
        ("기업집단 근거율(%)", "group_coverage_pct"),
        ("추가 검증 필요", "notes"),
    ]
    details = [
        {title: _literal("; ".join(row[key]) if key == "notes" else row.get(key))
         for title, key in fields}
        for row in audit["rows"]
    ]
    overview = [
        {"검증 항목": _literal(key), "결과": _literal(value)}
        for key, value in audit["counts"].items()
    ] + [
        {"검증 항목": "기본정보 출처", "결과": _literal(audit["catalog_source_url"])},
        {"검증 항목": "기본정보 수집일 기록", "결과": _literal(audit["catalog_date"])},
        {"검증 항목": "기본정보 재배포 상태", "결과": _literal(audit["catalog_rights"])},
        {"검증 항목": "분석 한계", "결과": _literal(audit["limitations"])},
    ]
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter", engine_kwargs={
        "options": {"strings_to_formulas": False, "strings_to_urls": False}
    }) as writer:
        pd.DataFrame(overview, columns=["검증 항목", "결과"]).to_excel(
            writer, sheet_name="연구검증현황", index=False
        )
        pd.DataFrame(details, columns=[title for title, _ in fields]).to_excel(
            writer, sheet_name="ETF별자료상태", index=False
        )
        for sheet in writer.sheets.values():
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, 0, 28)
            sheet.set_column(1, 21, 29)
    return out.getvalue()
