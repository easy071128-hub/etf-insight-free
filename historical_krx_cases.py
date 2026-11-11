"""Historical KRX user-file verification *summary*, never original holdings.

This casebook retains previously produced numerical findings after user uploads
are no longer available. It does NOT reconstitute the 2026-11-12 Excel files,
claim they were re-opened, or enroll an ETF identity or NAV portfolio.

Inputs: prior ETF Insight real-upload validation report and user-issued
development directive; source original files were not retrievable when
this archival summary was written (2026-11-12).
"""
from __future__ import annotations

HISTORICAL_CASES = (
    {
        "file": "data_2325_20261112.xlsx",
        "reviewed_date": "2026-11-12",
        "observed_component_count": 20,
        "top1_pct": 22.23, "top3_pct": 59.60, "top5_pct": 88.53,
        "hhi": 1642.09, "grade": "고집중",
        "status": "시가총액 구성비중 계산 기록 있음",
        "weight_basis": "KRX 시가총액 구성비중",
        "limitation": "원본 Excel 재접근 불가; ETF 코드·기준일·전체 NAV 보유비중 독립 검증 불가",
    },
    {
        "file": "data_2340_20261112.xlsx",
        "reviewed_date": "2026-11-12",
        "observed_component_count": 17,
        "top1_pct": 24.92, "top3_pct": 52.34, "top5_pct": 70.65,
        "hhi": 1312.94, "grade": "고집중",
        "status": "시가총액 구성비중 계산 기록 있음",
        "weight_basis": "KRX 시가총액 구성비중",
        "limitation": "원본 Excel 재접근 불가; ETF 코드·기준일·전체 NAV 보유비중 독립 검증 불가",
    },
    {
        "file": "data_2308_20261112.xlsx",
        "reviewed_date": "2026-11-12",
        "observed_component_count": 505,
        "top1_pct": None, "top3_pct": None, "top5_pct": None,
        "hhi": None, "grade": "자료부족",
        "status": "약 505개 구성항목; 구성비중 숫자 미확보",
        "weight_basis": "구성비중 수치 없음",
        "limitation": "종목 목록만 보유; 집중도·HHI·정량 유사도 산출 불가",
    },
    {
        "file": "data_5705_20261111.xlsx",
        "reviewed_date": "2026-11-11",
        "observed_component_count": 22,
        "top1_pct": 19.24, "top3_pct": 47.49, "top5_pct": 59.79,
        "hhi": 989.47, "grade": "집중",
        "status": "22개 구성항목, 원본 시가총액 구성비중 합 99.99%; TIGER 반도체 PDF 상위10 교차대조 기록",
        "weight_basis": "KRX 시가총액 구성비중",
        "original_sha256": "5d9a0e1ea544eed8a64e0d72b7622acf72702e12dc6db42ff914b7c606b26664",
        "limitation": "원본 Excel 내 ETF 코드와 구성 기준일 미기재; PDF 상위10 비교는 공식 전체 NAV 보유비중 검증 아님",
    },
)

HISTORICAL_PAIR = {
    "file_a": "data_2325_20261112.xlsx",
    "file_b": "data_2340_20261112.xlsx",
    "observed_common_non_cash_security_count": 0,
    "source": "2026-11-12 당시 실제 파일 분석 검증 기록",
    "limitation": (
        "두 사용자 구성표에 나타난 종목만 비교한 값. ETF 식별·기준일·"
        "전체 NAV 투자구조의 차이 또는 두 ETF 간 유사도 0점을 증명하지 않는다."
    ),
}


def archived_user_results():
    """Historical record only; NEVER feed these into live NAV comparisons."""
    return [dict(item) for item in HISTORICAL_CASES]


def archived_pair_observation():
    return dict(HISTORICAL_PAIR)


def audit_historical_results():
    """Minimal invariants, not independent numerical re-verification."""
    cases = archived_user_results()
    files = [r["file"] for r in cases]
    if len(files) != len(set(files)):
        raise ValueError("이전 사용자 자료명이 중복됐습니다.")
    for row in cases:
        top1, top3, top5, hhi = (
            row["top1_pct"], row["top3_pct"], row["top5_pct"], row["hhi"]
        )
        if None in (top1, top3, top5, hhi):
            if any(x is not None for x in (top1, top3, top5, hhi)):
                raise ValueError("과거 누락자료의 집중도 값을 일부만 만든 것으로 표시했습니다.")
            if row["grade"] != "자료부족":
                raise ValueError("집중도 계산 불가에 자료부족이 누락됐습니다.")
            continue
        if not 0 <= top1 <= top3 <= top5 <= 100:
            raise ValueError("상위 구성비중 합의 단조성 오류")
        if not 0 <= hhi <= 10000:
            raise ValueError("HHI가 올바른 범위에 없습니다.")
        if not row["weight_basis"].startswith("KRX 시가총액"):
            raise ValueError("과거 시가총액 자료를 NAV 비중으로 잘못 표시했습니다.")
    pair = archived_pair_observation()
    if set((pair["file_a"],pair["file_b"])) - set(files):
        raise ValueError("과거 비교 파일이 목록에 없습니다.")
    return len(cases)
