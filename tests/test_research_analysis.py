"""Coverage-aware financial research metadata and candidate reasoning tests."""
from io import BytesIO

import pandas as pd
import pytest

from etf_engine import candidate_etfs, parse_bundle
from research_analysis import (
    TEMPLATE, analyze_labeled_portfolio, assess_product_name,
    compare_labeled_portfolios, parse_company_evidence,
)


def _csv(header,rows):
    return ("\n".join([header,*rows])+"\n").encode("utf-8-sig")


def _snap(code="091230",weight_a=75):
    data=_csv("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        f"005930,삼성전자,{weight_a},주식,{code},TIGER 반도체,2026-11-10",
        f"000660,SK하이닉스,{100-weight_a},주식,{code},TIGER 반도체,2026-11-10",
    ])
    _,snapshots,_,reports=parse_bundle([("hold.csv",data)])
    assert reports[0]["status"]=="성공"
    return snapshots[code]


def _evidence(a="반도체",b="2차전지",with_b=True):
    rows=[
        f"005930,삼성전자,{a},메모리,한국,삼성,https://example.org/a,2026-11-10",
    ]
    if with_b:
        rows.append(
            f"000660,SK하이닉스,{b},양극재,한국,SK,https://example.org/b,2026-11-10"
        )
    return _csv("종목코드,종목명,섹터,세부산업,국가,기업집단,근거URL,기준일",rows)


def test_template_has_required_provenance_fields():
    text=TEMPLATE.decode("utf-8-sig")
    assert "근거URL" in text and "기준일" in text and "세부산업" in text


def test_documented_labels_allow_complete_sector_and_group_exposure():
    labels,source=parse_company_evidence(_evidence(),"labels.csv")
    assert source["count"]==2
    assert "독립 인증 전" in source["provenance"]
    result=analyze_labeled_portfolio(_snap(),labels)
    assert result["available"]
    assert result["sector_grade"]=="고집중"
    assert result["country_grade"]=="국내"
    assert result["group_grade"]=="고집중"
    assert result["coverage_pct"]["sector"]==pytest.approx(100)
    assert result["breakdowns"]["sector"]["반도체"]==pytest.approx(75)


def test_missing_company_sector_blocks_grade_not_fabricated():
    labels,_=parse_company_evidence(_evidence(with_b=False),"incomplete.csv")
    result=analyze_labeled_portfolio(_snap(),labels)
    assert result["sector_grade"]=="자료부족"
    assert result["coverage_pct"]["sector"]==pytest.approx(75)
    assessment=assess_product_name({"name":"TIGER 반도체"},result)
    assert assessment["grade"]=="자료부족"


def test_provisional_name_assessment_follows_investment_subject_evidence():
    labels,_=parse_company_evidence(_evidence(),"full.csv")
    exp=analyze_labeled_portfolio(_snap(),labels)
    assert assess_product_name({"name":"TIGER 반도체"},exp)["grade"]=="명확·부합"
    assert assess_product_name({"name":"TIGER 밸류업","index_name":"반도체"},exp)["grade"]=="모호·부합"
    assert assess_product_name({"name":"TIGER 2차전지"},exp)["grade"]=="불일치"
    assert assess_product_name({"name":"TIGER 밸류업"},exp)["grade"]=="자료부족"


def test_name_conflict_must_not_be_counted_as_verified_sector():
    raw=_evidence().decode("utf-8-sig").replace("005930,삼성전자,", "005930,삼성전자오류,")
    labels,_=parse_company_evidence(raw.encode("utf-8-sig"),"conflict.csv")
    result=analyze_labeled_portfolio(_snap(),labels)
    assert result["sector_grade"]=="자료부족"
    assert "005930" in result["name_conflicts"]


def test_metadata_url_must_be_https_and_date_not_future():
    a=_evidence().replace(b"https://example.org/a",b"javascript:evil.com")
    with pytest.raises(ValueError,match="근거URL"):
        parse_company_evidence(a,"bad.csv")
    bad=_evidence().decode("utf-8-sig").replace("2026-11-10","2099-01-01")
    with pytest.raises(ValueError,match="미래"):
        parse_company_evidence(bad.encode("utf-8-sig"),"future.csv")


def test_conflicting_rows_for_same_code_rejected():
    data=_evidence().decode("utf-8-sig")
    line=data.splitlines()[1]
    changed=line.replace("반도체","2차전지")
    bad=(data+changed+"\n").encode("utf-8-sig")
    with pytest.raises(ValueError,match="중복"):
        parse_company_evidence(bad,"conflict.csv")


def test_nonmatching_coverage_blocks_subsector_comparison():
    a=_snap("091230",75)
    b=_snap("091231",65)
    labels,_=parse_company_evidence(_evidence(with_b=False),"partial.csv")
    diff=compare_labeled_portfolios(a,b,labels)
    assert not diff["available"]


def test_sector_comparison_uses_explicit_nav_weights_without_overall_score():
    a=_snap("091230",75)
    b=_snap("091231",65)
    labels,_=parse_company_evidence(_evidence(),"full.csv")
    diff=compare_labeled_portfolios(a,b,labels)
    assert diff["available"]
    first=diff["comparisons"]["sector"][0]
    assert abs(first["차이(%p)"])==pytest.approx(10)
    assert "독립 검증 전" in diff["provenance"]


def test_candidates_do_not_claim_similarity_from_broad_category_alone():
    items={
        "091230":{"name":"TIGER 반도체","index_name":"KRX 반도체","category":"국내주식"},
        "999999":{"name":"KODEX 농산물","index_name":"농산물","category":"국내주식"},
    }
    assert candidate_etfs("091230",items,{})==[]


def test_candidate_explains_exact_index_and_strategy_warning():
    items={
        "091230":{"name":"TIGER 반도체","index_name":"KRX 반도체"},
        "091231":{"name":"KODEX 반도체 레버리지","index_name":"KRX 반도체"},
        "091232":{"name":"ACE 반도체 장비","index_name":"KRX 반도체 장비"},
    }
    result=candidate_etfs("091230",items,{},limit=5)
    assert result[0]["코드"]=="091231"
    assert "기초지수 동일" in result[0]["근거 수준"]
    assert "전략 차이" in result[0]["후보 근거"]
    assert "실제 편입비중 자료 부족" in result[0]["자료 상태"]
    assert any("공통 투자주제" in r["후보 근거"] for r in result[1:])


def test_candidate_evidence_from_holdings_is_not_overall_score():
    raw=_csv("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        "005930,삼성전자,60,주식,091230,TIGER 반도체,2026-11-10",
        "000660,SK하이닉스,40,주식,091230,TIGER 반도체,2026-11-10",
    ])
    raw2=raw.replace(b"091230",b"091231")
    catalog,snapshots,_,r=parse_bundle([("a.csv",raw),("b.csv",raw2)])
    catalog["091230"]["index_name"]="KRX 반도체"
    catalog["091231"]["index_name"]="KRX 반도체"
    result=candidate_etfs("091230",catalog,snapshots)
    assert len(result)==1
    assert "중복비중 100.00%" in result[0]["후보 근거"]
    assert "종합" not in result[0]["자료 상태"]
