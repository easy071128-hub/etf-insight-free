"""Documented industry-vocabulary guide, NOT guessed firm classifications.

Each company's business labels still require dated, source-backed evidence.
The taxonomy below is a research guide and does not imply any allocation of
a conglomerate's ETF weight to revenue segments.
"""
from __future__ import annotations

TAXONOMY = {
    "반도체": {
        "메모리 반도체": ("DRAM", "NAND", "HBM"),
        "시스템 반도체": ("CPU", "GPU/AI 반도체", "팹리스"),
        "파운드리": ("위탁생산",),
        "반도체 장비": ("전공정 장비", "후공정 장비", "검사/테스트 장비"),
        "반도체 소재": ("웨이퍼", "화학소재", "반도체 부품"),
        "후공정": ("패키징", "테스트", "첨단 패키징"),
        "복합사업": ("복합사업(비중 미배분)",),
        "미확인": ("미확인",),
    },
    "2차전지": {
        "셀": ("배터리 셀",),
        "양극재": ("양극재",),
        "음극재": ("음극재",),
        "전해질": ("전해질",),
        "분리막": ("분리막",),
        "장비": ("배터리 제조 장비",),
        "리사이클링": ("배터리 재활용",),
        "원재료·광물": ("리튬", "니켈", "기타 광물"),
        "기타 관련 사업": ("기타",),
        "복합사업": ("복합사업(비중 미배분)",),
        "미확인": ("미확인",),
    },
}


def taxonomy_rows():
    return [
        {"대분류": sector, "산업 가치사슬": category,
         "세부사업 예시": ", ".join(details),
         "주의": "기업별 공시와 기준일을 따로 확인; 복합사업은 임의 분해 금지"}
        for sector, groups in TAXONOMY.items()
        for category, details in groups.items()
    ]


def unresolved_multibusiness(metadata, exposure):
    """Evidence-backed metadata can mark composite businesses explicitly."""
    if not exposure.get("available"):
        return []
    return [
        item["security_id"]
        for item in metadata.values()
        if ("복합사업" in str(item.get("subsector", ""))
            or "복합사업" in str(item.get("sector", "")))
    ]
