"""Small, reviewed *research references* from issuer and regulatory pages.

The records below are not a licensed mass-distribution of portfolio holdings.
Company labels describe documented activities, not how a stock's ETF weight is
split among products. Publication dates limit historical backfilling.
References were manually inspected on 2026-11-12, not live API verified.
"""
from __future__ import annotations

from datetime import date

REVIEWED_ON = "2026-11-12"

# Each record has a verifiable, named-company source; no company is classified
# from its ETF's name. Blank group = no specific group source established.
# A combined-business company remains a combined bucket. Do not allocate its
# ETF weight to DRAM/HBM/cathode fractions.
_RECORDS = (
    ("005930", "삼성전자", "복합사업", "복합사업(메모리·시스템LSI·파운드리·전자기기)", "한국", "삼성",
     "2026-10-29", "https://news.samsung.com/global/samsung-electronics-announces-third-quarter-2026-results",
     "공시된 DS·DX 사업을 구별하며 주식 비중을 사업별로 배분하지 않음"),
    ("000660", "SK하이닉스", "반도체", "메모리(DRAM·NAND·HBM)", "한국", "SK",
     "2026-10-28", "https://news.skhynix.com/en/q3-2026-business-results/",
     "DRAM·NAND·HBM 제품을 확인했지만 이들 간 ETF 노출비중은 구분할 수 없음"),
    ("042700", "한미반도체", "반도체", "후공정 장비(HBM TC 본더·패키징)", "한국", "",
     "2025-11-14", "https://kind.krx.co.kr/external/2025/11/14/003215/20251114007446/11013.htm",
     "공시된 HBM TC 본더·검사 장비 등 장비 공급 사업"),
    ("036930", "주성엔지니어링", "복합사업", "복합사업(반도체 전공정·디스플레이·태양광 장비)", "한국", "",
     "2025-03-17", "https://kind.krx.co.kr/external/2025/03/17/000511/20250317002402/11011.htm",
     "ALD·CVD 반도체 장비 외 디스플레이·태양광 장비도 영위"),
    ("000990", "DB하이텍", "반도체", "파운드리·전력반도체", "한국", "",
     "2026-03-16", "https://kind.krx.co.kr/external/2026/03/16/001993/20260316005760/11011.htm",
     "사업보고서에 수록된 위탁생산·전력반도체 사업"),
    ("039030", "이오테크닉스", "복합사업", "복합사업(반도체용·기타 레이저 장비)", "한국", "",
     "2026-03-23", "https://kind.krx.co.kr/external/2026/03/23/002295/20260323009640/11011.htm",
     "레이저 응용기기를 반도체 특정 사업의 순수 노출로 단정하지 않음"),
    ("240810", "원익IPS", "복합사업", "복합사업(반도체·디스플레이 전공정 장비)", "한국", "",
     "2026-05-15", "https://kind.krx.co.kr/external/2026/05/15/003220/20260515007352/11013.htm",
     "원익홀딩스의 공시에서 확인한 반도체·디스플레이 장비 생산 자회사"),
    ("095340", "ISC", "반도체", "후공정 검사·테스트 소켓 및 장비", "한국", "",
     "2026-03-18", "https://kind.krx.co.kr/external/2026/03/18/000082/20260318000201/11011.htm",
     "메모리·비메모리 테스트 소켓 및 별도 테스트솔루션을 함께 영위"),
    ("066970", "엘앤에프", "2차전지", "양극재", "한국", "",
     "2026-05-15", "https://kind.krx.co.kr/external/2026/05/15/001002/20260515002154/11013.htm",
     "사업보고서의 이차전지 양극활물질·NCM 제품 근거"),
    ("003670", "포스코퓨처엠", "2차전지", "복합사업(양극재·음극재)", "한국", "포스코",
     "2026-10-30", "https://www.poscofuturem.com/pr/view.do?num=1055",
     "LFP/하이니켈 양극재 및 인조흑연·실리콘 음극재 등 복수 소재 사업"),
    ("247540", "에코프로비엠", "2차전지", "양극재", "한국", "에코프로",
     REVIEWED_ON, "https://www.ecoprobm.com/sub010101",
     "발행일이 확인되지 않는 회사 공식 사업개요로, 검토일보다 과거로 소급하지 않음"),
    ("086520", "에코프로", "복합사업", "사업지주회사(이차전지 소재·환경)", "한국", "에코프로",
     REVIEWED_ON, "https://www.ecopro.co.kr/sub010101/view",
     "양극재 순수 제조사가 아닌 사업지주회사임을 구분"),
    ("051910", "LG화학", "복합사업", "복합사업(석유화학·양극재·생명과학)", "한국", "LG",
     "2026-03-13", "https://kind.krx.co.kr/external/2026/03/13/001833/20260313004559/11011.htm",
     "복수 사업부문 영위; ETF 주식 편입비중을 양극재 노출로 모두 합산하지 않음"),
)

# Derived aggregate research notes ONLY, not republished issuer basket rows.
# KODEX website calls this Portfolio Deposit File (PDF), *not* a .pdf document;
# disclosed component weights exclude cash and deposits. Do not label NAV.
_ISSUER_CASES = (
    {
        "etf_code": "091160",
        "etf_name": "KODEX 반도체",
        "source_url": "https://m.samsungfund.com/etf/product/view.do?id=2ETF07",
        "observation_date": "2026-10-13",
        "reviewed_on": REVIEWED_ON,
        "weight_basis": "운용사 구성종목(PDF) 현금성 제외 비중",
        "disclosed_non_cash_count": 21,
        "sum_disclosed_pct": 100.00,
        "coverage": "운용사 페이지에 표시된 비현금 21개 구성비중 합계 100%; NAV 전체 자산비중은 미확인",
        "top1_pct": 17.03,
        "top3_pct": 43.62,
        "top5_pct": 56.16,
        "hhi_disclosed": 878.5954,
        "grade": "집중",
        "review_note": "현금 제외 공시 구성비중으로 별도 재계산; 사용자 연구용 기준이며 공식 위험등급 아님",
        "full_nav_verified": False,
    },
    {
        "etf_code": "461950",
        "etf_name": "KODEX 2차전지핵심소재10",
        "source_url": "https://m.samsungfund.com/etf/product/view.do?id=2ETFK1",
        "observation_date": "2026-11-06",
        "reviewed_on": REVIEWED_ON,
        "weight_basis": "운용사 구성종목(PDF) 현금성 제외 비중",
        "disclosed_non_cash_count": 6,
        "sum_disclosed_pct": 91.06,
        "coverage": "운용사 검색자료에서 확인한 상위 6종목만 합계 91.06%; 전체 구성비중 미검증",
        "top1_pct": 20.53,
        "top3_pct": 53.04,
        "top5_pct": 81.76,
        "hhi_disclosed": None,
        "grade": "부분자료(상위5 합계 70% 이상 관찰)",
        "review_note": "일부 종목만 확보했으므로 HHI와 ETF 전체 구조 및 NAV 유사도는 산출하지 않음",
        "full_nav_verified": False,
    },
)


def reviewed_company_evidence():
    """The same shape as validated user evidence, with explicit review origin."""
    result = {}
    for code, name, sector, subsector, country, group, as_of, url, note in _RECORDS:
        result[code] = {
            "security_id": code, "security_name": name, "sector": sector,
            "subsector": subsector, "country": country, "group": group,
            "source_url": url, "as_of_date": as_of,
            "reviewed_on": REVIEWED_ON, "note": note,
            "provenance": "공식 기업자료 웹 열람·사업 분야 연구 분류(ETF 비중 독립 인증 아님)",
        }
    return result


def issuer_research_cases():
    """Issuer research examples with only arithmetic aggregates and provenance."""
    return [dict(row) for row in _ISSUER_CASES]


def combine_company_evidence(reviewed, uploaded):
    """Use the reviewed company entry on conflicts, add new user evidence.

    A user-uploaded URL is not issuer-authenticated and cannot silently
    overwrite the pre-reviewed label. Conflict codes are disclosed by the UI.
    """
    output = {code: dict(row) for code, row in (reviewed or {}).items()}
    conflicts = []
    for code, row in (uploaded or {}).items():
        if code not in output:
            output[code] = dict(row)
        elif any(str(output[code].get(k, "")) != str(row.get(k, ""))
                 for k in ("security_name", "sector", "subsector", "country", "group")):
            conflicts.append(code)
    return output, sorted(conflicts)


def verify_registry():
    """Sanity checks for curated records; called in CI and optionally locally."""
    records = reviewed_company_evidence()
    if len(records) != len(_RECORDS):
        raise ValueError("종목코드가 중복됩니다.")
    for code, record in records.items():
        if not code.isdecimal() or len(code) != 6:
            raise ValueError("회사 종목코드가 올바르지 않습니다.")
        if date.fromisoformat(record["as_of_date"]) > date.fromisoformat(REVIEWED_ON):
            raise ValueError("분류 근거 발행일이 검토일보다 미래입니다.")
        if not record["source_url"].startswith("https://"):
            raise ValueError("출처는 HTTPS URL이어야 합니다.")
        if "복합사업" in record["subsector"] and record["subsector"] in (
            "DRAM", "NAND", "HBM", "양극재",
        ):
            raise ValueError("복합사업을 단일 사업으로 잘못 배정했습니다.")
    cases = issuer_research_cases()
    for item in cases:
        if item["full_nav_verified"] or not 0 <= item["sum_disclosed_pct"] <= 100.05:
            raise ValueError("참고 자료를 NAV 인증으로 잘못 표기했습니다.")
        if item["top5_pct"] < item["top3_pct"] or item["top3_pct"] < item["top1_pct"]:
            raise ValueError("상위 비중 합계가 잘못됐습니다.")
        if item["sum_disclosed_pct"] < item["top5_pct"]:
            raise ValueError("부분 종목 합계가 상위 5개 합보다 작습니다.")
    return len(records), len(cases)
