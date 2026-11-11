"""Coverage-aware financial research metadata and candidate reasoning tests."""
from io import BytesIO

import pandas as pd
import pytest

from etf_engine import candidate_etfs, parse_bundle
from research_analysis import (
    TEMPLATE, analyze_labeled_portfolio, assess_product_name,
    compare_labeled_portfolios, parse_company_evidence, excel_report_research,
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
    assert "종합점수 미산출" in result[0]["자료 상태"]


def test_evidence_newer_than_holdings_cannot_claim_historical_sector():
    new=_evidence().decode("utf-8-sig").replace("2026-11-10","2026-11-11")
    labels,_=parse_company_evidence(new.encode("utf-8-sig"),"later.csv")
    result=analyze_labeled_portfolio(_snap(),labels)
    assert result["sector_grade"]=="자료부족"
    assert set(result["future_relative_to_holdings"])=={"005930","000660"}


def test_research_excel_includes_sources_and_does_not_execute_formulas():
    from openpyxl import load_workbook
    labels,source=parse_company_evidence(_evidence(),"research.csv")
    snapshots={"091230":_snap()}
    catalog={"091230":{"name":"TIGER 반도체","short_name":"TIGER 반도체"}}
    workbook=excel_report_research("091230",catalog,snapshots,labels,source)
    excel=load_workbook(BytesIO(workbook),data_only=False)
    assert {"검증요약","섹터","세부산업","근거기록"} <= set(excel.sheetnames)
    summary={r[0]:r[1] for r in excel["검증요약"].values if r[0]}
    assert summary["이름·투자구조 잠정 판정"]=="명확·부합"
    assert summary["섹터 집중도"]=="고집중"
    assert summary["분류 원본 SHA256"]==source["source_sha256"]
    assert any("example.org" in str(cell.value) for row in excel["근거기록"] for cell in row)
    assert all(cell.data_type!="f" for sheet in excel for row in sheet for cell in row)


def test_research_report_missing_metadata_keeps_data_insufficient():
    from openpyxl import load_workbook
    data=excel_report_research("091230",
        {"091230":{"name":"TIGER 반도체"}},{"091230":_snap()},{})
    book=load_workbook(BytesIO(data))
    summary={r[0]:r[1] for r in book["검증요약"].values if r[0]}
    assert summary["이름·투자구조 잠정 판정"]=="자료부족"
    assert summary["섹터 집중도"]=="자료부족"


def test_high_verified_nav_overlap_can_find_differently_named_etf():
    raw=_csv("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        "005930,삼성전자,70,주식,091230,원래 상품,2026-11-10",
        "000660,SK하이닉스,30,주식,091230,원래 상품,2026-11-10",
    ])
    raw2=_csv("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        "005930,삼성전자,65,주식,091231,다른 상품,2026-11-10",
        "000660,SK하이닉스,35,주식,091231,다른 상품,2026-11-10",
    ])
    catalog,snapshots,_,reports=parse_bundle([("a.csv",raw),("b.csv",raw2)])
    assert all(r["status"]=="성공" for r in reports)
    catalog["091230"]["name"]="알파"
    catalog["091231"]["name"]="베타"
    matches=candidate_etfs("091230",catalog,snapshots)
    assert len(matches)==1
    assert matches[0]["코드"]=="091231"
    assert matches[0]["근거 수준"]=="실제 편입종목 중복비중 높음"
    assert "95.00%" in matches[0]["후보 근거"]
    assert "기준일 2026-11-10" in matches[0]["자료 상태"]


def test_weak_holdings_overlap_without_name_cue_not_shown_as_similar():
    raw=_csv("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        "005930,삼성전자,10,주식,091230,원래 상품,2026-11-10",
        "000660,SK하이닉스,90,주식,091230,원래 상품,2026-11-10",
    ])
    raw2=_csv("종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일",[
        "005930,삼성전자,10,주식,091231,다른 상품,2026-11-10",
        "123456,가상기업,90,주식,091231,다른 상품,2026-11-10",
    ])
    catalog,snapshots,_,_=parse_bundle([("a.csv",raw),("b.csv",raw2)])
    catalog["091230"]["name"]="알파"
    catalog["091231"]["name"]="베타"
    assert candidate_etfs("091230",catalog,snapshots)==[]


def test_independent_companies_not_merged_into_one_conglomerate():
    raw=_evidence().decode("utf-8-sig").replace(",삼성,",",독립,").replace(",SK,",",독립,")
    labels,_=parse_company_evidence(raw.encode("utf-8-sig"),"independent.csv")
    result=analyze_labeled_portfolio(_snap(),labels)
    assert result["complete"]["group"]
    assert len(result["breakdowns"]["group"])==2
    assert set(result["breakdowns"]["group"].values())=={75.0,25.0}
