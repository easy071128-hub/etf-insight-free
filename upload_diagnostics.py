"""Explain verified facts and the *next missing evidence* for each uploaded KRX file.

An observed market-cap component table is not ETF NAV holdings. Neither file
name, matching holdings, a 100% sum nor a NAV-labelled column authenticates
an issuer's filing. This module never assigns an unidentified file to an ETF.
"""
from __future__ import annotations


def _n(value, fallback=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def describe_upload(report, snapshots=None):
    """Conservative, user-facing diagnostics based only on parser reports."""
    snapshots = snapshots or {}
    kind = str(report.get("kind") or "")
    status = str(report.get("status") or "확인 필요")
    rows = _n(report.get("holding_count"))
    if report.get("valid_weights") is not None:
        valid = min(rows, _n(report.get("valid_weights")))
    else:
        valid = rows if report.get("weight_available") else 0

    result = {
        "파일": str(report.get("file") or ""),
        "파일 상태": status,
        "자료 종류": kind or "인식 전",
        "구성항목": rows,
        "수치 비중": valid,
        "분석 가능 범위": "미확인",
        "다음에 필요한 것": "",
        "원출처 검증": "미완료",
    }
    if status == "중복":
        result["분석 가능 범위"] = "이 세션에서 이미 처리한 동일 파일"
        result["다음에 필요한 것"] = "추가 업로드 불필요"
    elif kind == "ETF 기본정보":
        result["분석 가능 범위"] = "ETF 이름·코드·지수 검색 (편입비중 미확인)"
        result["다음에 필요한 것"] = "ETF별 기준일·비중 종류가 명시된 실제 구성자료"
    elif kind in ("구성비중 단독 분석(ETF 미연결)", "미연결 구성종목"):
        basis = str(report.get("weight_basis") or "비중 기준 미확인")
        if valid == rows and rows > 0 and report.get("analysis_available"):
            result["분석 가능 범위"] = (
                f"{basis} 기준 구성표 자체의 집중도·HHI "
                "(ETF 실제 NAV 노출 아님)"
            )
            result["다음에 필요한 것"] = (
                "원본 ETF 코드·기준일 확인 + 운용사/공식 NAV 편입비중 확보. "
                "종목 일치만으로 ETF 자동 연결 불가"
            )
        else:
            result["분석 가능 범위"] = (
                f"구성종목 목록 {rows}개만 확인; "
                f"수치 비중 {valid}/{rows}개 → 집중도·유사도 미산출"
            )
            result["다음에 필요한 것"] = (
                "구성비중의 숫자가 포함된 공식 Excel 또는 "
                "운용사 NAV 구성자료; 수량·평가금액으로 비중 추정 금지"
            )
    elif kind == "구성종목" and status == "성공":
        result["분석 가능 범위"] = "제출한 구성비중에 대한 종목 집중도"
        raw_name = report.get("file")
        snapshot = next(
            (snap for snap in snapshots.values() if snap.get("filename") == raw_name),
            None,
        )
        meta = snapshot.get("meta", {}) if snapshot else {}
        if meta.get("nav_basis_claimed") and not meta.get("pcf_context_detected"):
            result["분석 가능 범위"] = (
                "업로드 파일에서 NAV 비중이라고 표기됨; 종목 집중도 계산 가능 "
                "(공식 원출처 독립 확인 전)"
            )
            result["다음에 필요한 것"] = (
                "원발행기관·편입일·전체 보유항목 확인 및 "
                "기업별 산업 분류 공시 근거"
            )
        else:
            result["다음에 필요한 것"] = (
                "NAV 비중 종류 확인 + 기업별 산업 분류 공시 근거"
            )
    elif kind == "PDF":
        result["분석 가능 범위"] = "PDF 문서 자동 표 추출 미지원"
        result["다음에 필요한 것"] = (
            "동일 원천의 Excel/CSV 공개 다운로드 파일. "
            "ETF PDF(Portfolio Deposit File)는 .pdf 문서와 다름"
        )
    else:
        result["분석 가능 범위"] = "등록 보류 — 원본 형식·비중·식별 조건 미충족"
        result["다음에 필요한 것"] = (
            str(report.get("message") or "원본 파일의 머리글과 값 확인")[:240]
        )
    return result


def describe_batch(reports, snapshots=None):
    return [describe_upload(report, snapshots) for report in reports]


def plain_text_diagnostics(reports, snapshots=None):
    """Downloadable UTF-8 diagnostic explanation, without uploading any raw rows."""
    items = describe_batch(reports, snapshots)
    lines = [
        "ETF Insight · 파일별 자동 진단 (업로드 원본 독립 인증 전)",
        "파일명·구성종목 일치·시가총액 비중을 ETF NAV 데이터로 단정하지 않습니다.",
        "",
    ]
    for row in items:
        lines.extend([
            f"파일: {row['파일']}",
            f"상태: {row['파일 상태']} / {row['자료 종류']}",
            f"구성항목: {row['구성항목']}개 / 수치 비중: {row['수치 비중']}개",
            f"가능한 분석: {row['분석 가능 범위']}",
            f"추가로 필요한 자료: {row['다음에 필요한 것']}",
            f"원출처 검증: {row['원출처 검증']}",
            "",
        ])
    return "\n".join(lines).encode("utf-8-sig")
