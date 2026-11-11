"""Optional, evidence-labelled business classifications for ETF Insight.

No company sector, country, group or business mix is inferred from a ticker.
Every accepted label comes from a separately uploaded row with a source URL
and an as-of date. A URL is a citation supplied by a user, not authentication.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from hashlib import sha256
from io import BytesIO
from urllib.parse import urlsplit
import re

import pandas as pd

from etf_engine import concentration, norm, sheets


COLUMN_ALIASES = {
    "security_id": ("종목코드", "구성종목코드", "security_id", "securitycode"),
    "security_name": ("종목명", "구성종목명", "security_name"),
    "sector": ("섹터", "주요섹터", "산업", "sector"),
    "subsector": ("세부산업", "세부섹터", "사업영역", "subsector"),
    "country": ("국가", "투자국가", "country"),
    "group": ("기업집단", "동일기업집단", "group"),
    "source_url": ("근거URL", "자료URL", "출처URL", "source_url"),
    "as_of_date": ("기준일", "자료기준일", "as_of_date"),
}
HEADER={norm(alias):field for field,names in COLUMN_ALIASES.items() for alias in names}
TOPICS={
    "반도체":"반도체", "2차전지":"2차전지", "이차전지":"2차전지",
    "배터리":"2차전지", "로봇":"로봇", "바이오":"바이오", "전력":"전력",
    "방산":"방산", "조선":"조선", "은행":"은행", "자동차":"자동차",
}
UNCLEAR={"", "-", "—", "미확인", "자료부족", "미제공", "nan", "none"}
TEMPLATE=("종목코드,종목명,섹터,세부산업,국가,기업집단,근거URL,기준일\n").encode("utf-8-sig")


def _safe_text(value):
    value=str(value).strip()
    if len(value)>300:
        raise ValueError("분류자료의 입력 문자열이 너무 깁니다.")
    if value.startswith(("=", "+", "-", "@")) and value not in ("-",):
        raise ValueError("분류자료에 수식처럼 시작하는 문자열이 있습니다.")
    return value


def _date(value):
    s=_safe_text(value)
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",s):
        raise ValueError("분류자료 기준일은 YYYY-MM-DD 형식이어야 합니다.")
    try:
        d=date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError("분류자료 기준일이 실제 달력 날짜가 아닙니다.") from exc
    if d>date.today():
        raise ValueError("분류자료의 미래 기준일을 사용할 수 없습니다.")
    return d.isoformat()


def _url(value):
    value=_safe_text(value)
    result=urlsplit(value)
    if result.scheme!="https" or not result.hostname or "." not in result.hostname:
        raise ValueError("각 분류 항목에는 https:// 형식의 근거URL이 필요합니다.")
    return value


def parse_company_evidence(content:bytes,filename:str):
    """Parse one provenance-bearing security metadata sheet, no guesswork."""
    candidates=[]
    for sheet,raw in sheets(content,filename):
        if raw.empty:continue
        for i in range(min(len(raw),22)):
            columns=[HEADER.get(norm(cell)) for cell in raw.iloc[i]]
            found={x for x in columns if x}
            if {"security_id","sector","source_url","as_of_date"}.issubset(found):
                candidates.append((sheet,raw,i,columns))
    if len(candidates)!=1:
        raise ValueError("분류자료는 종목코드·섹터·근거URL·기준일이 있는 시트가 정확히 하나여야 합니다.")
    sheet,raw,header,cols=candidates[0]
    if len([x for x in cols if x])!=len(set(x for x in cols if x)):
        raise ValueError("분류자료에 의미가 같은 열이 중복되어 있습니다.")
    if len(raw)-header-1>5000:
        raise ValueError("분류자료는 최대 5,000종목까지 지원합니다.")
    rows={}
    for i,values in enumerate(raw.iloc[header+1:].itertuples(index=False,name=None),start=header+2):
        data={key:_safe_text(values[j]) for j,key in enumerate(cols) if key}
        if not any(v and v not in UNCLEAR for v in data.values()):
            continue
        code=data.get("security_id","").upper().removesuffix(".0")
        if code.isdecimal():code=code.zfill(6)
        if not re.fullmatch(r"[0-9A-Z]{6,12}",code):
            raise ValueError(f"{i}행의 종목코드가 올바르지 않습니다.")
        sector=data.get("sector","")
        if sector.casefold() in UNCLEAR:
            raise ValueError(f"{i}행의 섹터가 비어 있습니다.")
        item={
            "security_id":code,
            "security_name":data.get("security_name",""),
            "sector":sector,
            "subsector":data.get("subsector","") if data.get("subsector","").casefold() not in UNCLEAR else "",
            "country":data.get("country","") if data.get("country","").casefold() not in UNCLEAR else "",
            "group":data.get("group","") if data.get("group","").casefold() not in UNCLEAR else "",
            "source_url":_url(data.get("source_url","")),
            "as_of_date":_date(data.get("as_of_date","")),
        }
        if code in rows and rows[code]!=item:
            raise ValueError(f"종목코드 {code}의 서로 다른 분류·근거 값이 중복되어 있습니다.")
        rows[code]=item
    if not rows:raise ValueError("유효한 종목 분류행이 없습니다.")
    return rows,{"source_file":filename,"source_sheet":sheet,
                 "source_sha256":sha256(content).hexdigest(),"count":len(rows),
                 "provenance":"사용자 업로드 URL·기준일 포함; 외부 원본 독립 인증 전"}


def _same_name(a,b):
    return not a or re.sub(r"\W","",a).casefold()==re.sub(r"\W","",b).casefold()


def analyze_labeled_portfolio(snapshot,metadata):
    """Compute coverage-safe country, sector and group exposures from valid NAV data."""
    frame=snapshot.get("frame")
    stats=concentration(frame)
    if not stats.get("available"):
        return {"available":False,"reason":stats.get("reason","편입자료 없음")}
    total=float(pd.to_numeric(frame.weight_pct).sum())
    eligible=frame[frame.asset_type=="주식"].copy()
    if eligible.empty:
        return {"available":False,"reason":"주식형 편입종목이 없습니다."}
    records={}
    for r in eligible.itertuples():
        code=str(r.security_id)
        name=str(r.security_name)
        if code in records:
            records[code]["weight_pct"]+=float(r.weight_pct)*100/total
        else:
            records[code]={"security_id":code,"name":name,
                           "weight_pct":float(r.weight_pct)*100/total}
    stock_weight=sum(x["weight_pct"] for x in records.values())
    dimensions={"sector":"섹터","subsector":"세부산업","country":"국가","group":"기업집단"}
    weights={k:defaultdict(float) for k in dimensions}
    covered={k:0.0 for k in dimensions}
    mismatched=[]
    dated=[]
    out_of_period=[]
    holdings_date=snapshot.get("meta",{}).get("as_of_date")
    for code,item in records.items():
        label=metadata.get(code)
        if not label:continue
        if not _same_name(label["security_name"],item["name"]):
            mismatched.append(code)
            continue
        if holdings_date and label["as_of_date"]>holdings_date:
            # Classification published after this historical holding date
            # cannot be asserted to describe the earlier snapshot.
            out_of_period.append(code)
            continue
        dated.append(label["as_of_date"])
        for key in dimensions:
            value=label.get(key,"")
            if value and value.casefold() not in UNCLEAR:
                if key=="group" and value.casefold().replace(" ","") in {
                    "없음","해당없음","독립","독립기업","무소속","independent","none"
                }:
                    # Independent firms do not become one conglomerate merely
                    # because they share the literal string "independent".
                    value=f"독립기업({code})"
                weights[key][value]+=item["weight_pct"]
                covered[key]+=item["weight_pct"]
    full={k:abs(covered[k]-stock_weight)<0.005 for k in dimensions}
    grouped={k:dict(sorted(weights[k].items(),key=lambda x:-x[1]))
             for k in dimensions}
    result={
        "available":True,"stock_weight_pct":stock_weight,
        "coverage_pct":{k:100*covered[k]/stock_weight for k in dimensions},
        "complete":full,"breakdowns":grouped,
        "missing_or_conflicting_codes":[code for code,item in records.items()
            if code not in metadata or
               not _same_name(metadata[code]["security_name"],item["name"]) or
               (holdings_date and metadata[code]["as_of_date"]>holdings_date)],
        "name_conflicts":mismatched,
        "future_relative_to_holdings":out_of_period,
        "basis":"검증 가능한 ETF NAV 비중 중 주식 구성항목만 분류, 현금·채권은 섹터 비중에 미포함",
        "provenance":"사용자가 업로드한 URL·기준일 있는 산업 분류표를 적용했으며 출처는 독립 검증하지 않음",
        "source_date_range":(min(dated),max(dated)) if dated else None,
    }
    if full["sector"]:
        leading=max(grouped["sector"].values(),default=0)
        result["sector_grade"]="고집중" if leading>=70 else ("집중" if leading>=50 else "분산")
    else:result["sector_grade"]="자료부족"
    if full["country"]:
        domestic=sum(v for k,v in grouped["country"].items()
                     if k.replace(" ","").upper() in ("한국","대한민국","KR","KOREA","SOUTHKOREA"))
        foreign=stock_weight-domestic
        # Country classification is explicitly of the documented stock
        # portion, NOT all ETF assets including any cash/derivatives.
        result["country_grade"]="국내" if domestic/stock_weight>=.8 else (
            "해외" if foreign/stock_weight>=.8 else "혼합")
    else:result["country_grade"]="자료부족"
    if full["group"] and result["country_grade"]=="국내":
        # An unaffiliated company is not an entire conglomerate; a large
        # independent single holding belongs in single-stock concentration,
        # not in same-business-group concentration.
        real_groups={k:v for k,v in grouped["group"].items()
                     if not k.startswith("독립기업(")}
        leading=max(real_groups.values(),default=0)
        result["group_grade"]="고집중" if leading>=60 else (
            "집중" if leading>=40 else "분산")
    elif result["country_grade"] in ("해외","혼합"):
        result["group_grade"]="미적용(국내형 ETF 연구 기준)"
    else:result["group_grade"]="자료부족"
    return result


def assess_product_name(catalog_item,exposure):
    """Return a *provisional* 4-way name/content label, never an official verdict."""
    name=str(catalog_item.get("short_name") or catalog_item.get("name") or "")
    index=str(catalog_item.get("index_name") or "")
    def themes(text):
        text=text.casefold()
        return {sector for token,sector in TOPICS.items() if token in text}
    named=themes(name)
    indexed=themes(index)
    clarity="명확" if named else "모호"
    fallback={"grade":"자료부족","clarity":clarity,
              "reason":"상품명에서 검증 가능한 투자주제를 확인할 수 없거나, 전체 주식 편입종목의 산업 분류가 부족합니다.",
              "verification":"사용자 제출 분류근거 기준의 잠정 판정; 외부 원본 독립검증 전"}
    if not exposure.get("available") or not exposure.get("complete",{}).get("sector"):
        return fallback
    sector=exposure["breakdowns"]["sector"]
    denom=exposure["stock_weight_pct"]
    if denom<=0:return fallback
    names=named or indexed
    if not names:return fallback
    named_share=sum(v for k,v in sector.items() if k in names)/denom
    dominant=max(sector.values(),default=0)/denom
    if named_share>=.7:
        grade="명확·부합" if named else "모호·부합"
        reason=(f'해당 투자주제로 확인된 주식 편입비중이 주식 구성항목의 {named_share*100:.1f}%입니다.'
                +' 단, 분류표의 독립 인증 전 잠정 판정입니다.')
    elif named and named_share<.3 and dominant>=.7:
        grade="불일치"
        reason=f'상품명에 명시된 주제의 비중은 주식 구성항목 중 {named_share*100:.1f}%이며, 다른 산업이 70% 이상입니다. 잠정적인 불일치 신호입니다.'
    else:
        return {**fallback,"reason":f'주제 관련 비중 {named_share*100:.1f}%로 부합·불일치를 단정하기 어렵습니다.'}
    return {"grade":grade,"clarity":clarity,"reason":reason,
            "verification":"사용자 제출 분류근거 기준의 잠정 판정; 외부 원본 독립검증 전"}


def compare_labeled_portfolios(snapshot_a,snapshot_b,metadata):
    a=analyze_labeled_portfolio(snapshot_a,metadata)
    b=analyze_labeled_portfolio(snapshot_b,metadata)
    if not a["available"] or not b["available"]:
        return {"available":False,"reason":"ETF 실제 편입비중이 둘 다 유효해야 합니다."}
    sectors={}
    for dimension in ("sector","subsector"):
        if not (a["complete"][dimension] and b["complete"][dimension]):
            continue
        x=a["breakdowns"][dimension]
        y=b["breakdowns"][dimension]
        sectors[dimension]=[
            {"산업":label,"ETF A(%)":round(x.get(label,0),2),
             "ETF B(%)":round(y.get(label,0),2),
             "차이(%p)":round(x.get(label,0)-y.get(label,0),2)}
            for label in sorted(set(x)|set(y),
                                key=lambda k:-abs(x.get(k,0)-y.get(k,0)))
        ]
    if not sectors:
        return {"available":False,"reason":"비교할 두 ETF 모두에서 섹터 또는 세부산업 전체 분류 근거가 필요합니다."}
    date_a=snapshot_a.get("meta",{}).get("as_of_date")
    date_b=snapshot_b.get("meta",{}).get("as_of_date")
    dating_note=(f"편입 기준일이 서로 다름: {date_a} / {date_b}. 동일 시점의 산업 차이로 단정할 수 없습니다. "
                 if date_a!=date_b else "")
    return {"available":True,"comparisons":sectors,
            "provenance":"사용자가 제공한 분류표의 표기 기준으로 비교(독립 검증 전), ETF NAV 비중을 사용",
            "note":dating_note+"복합사업의 실제 사업별 매출 비중은 알 수 없으며, 한 기업의 비중을 여러 산업으로 임의 배분하지 않습니다."}


def excel_report_research(code,catalog,snapshots,metadata,source=None):
    """Excel report for only verified-coverage research fields, with provenance."""
    if code not in snapshots or code not in catalog:
        raise ValueError("ETF 편입비중과 기본정보가 모두 필요합니다.")
    result=analyze_labeled_portfolio(snapshots[code],metadata)
    verdict=assess_product_name(catalog[code],result)
    meta=snapshots[code]["meta"]
    rows=[
        ("ETF 코드",code),("ETF 상품명",catalog[code]["name"]),
        ("NAV 편입 기준일",meta.get("as_of_date") or "미확인"),
        ("이름·투자구조 잠정 판정",verdict["grade"]),
        ("상품명 명확성",verdict["clarity"]),
        ("판정 설명",verdict["reason"]),
        ("판정 검증 한계",verdict["verification"]),
        ("섹터 집중도",result.get("sector_grade","자료부족")),
        ("국가 구성(주식 기준)",result.get("country_grade","자료부족")),
        ("기업집단 집중도",result.get("group_grade","자료부족")),
        ("분류 출처 상태","업로드 출처 기록 / 독립 인증 전"),
        ("분류 파일명",(source or {}).get("source_file","없음")),
        ("분류 원본 SHA256",(source or {}).get("source_sha256","없음")),
    ]
    if result.get("available"):
        rows.extend((f"{dim} 분류 확인율 (%)",round(val,2))
                    for dim,val in result["coverage_pct"].items())
        rows.append(("분석 범위",result["basis"]))
        rows.append(("분류기준일 범위",str(result["source_date_range"])))
        rows.append(("분류 누락/불일치 코드",", ".join(result["missing_or_conflicting_codes"][:50])))
    def safe(x):
        return "'"+x if isinstance(x,str) and x.startswith(("=","+","-","@")) else x
    buf=BytesIO()
    with pd.ExcelWriter(buf,engine="xlsxwriter",
            engine_kwargs={"options":{"strings_to_formulas":False,"strings_to_urls":False}}) as writer:
        pd.DataFrame([(safe(a),safe(b)) for a,b in rows],
                     columns=["항목","확인된 결과"]).to_excel(
                         writer,index=False,sheet_name="검증요약")
        if result.get("available"):
            for dimension,title in (("sector","섹터"),("subsector","세부산업"),
                                    ("country","국가"),("group","기업집단")):
                entries=[{"분류":safe(k),"ETF NAV 비중(%)":v}
                         for k,v in result["breakdowns"][dimension].items()]
                pd.DataFrame(entries,columns=["분류","ETF NAV 비중(%)"]).to_excel(
                    writer,index=False,sheet_name=title)
        holding_codes=set(snapshots[code]["frame"]["security_id"].astype(str))
        proofs=[{"종목코드":k,"종목명":safe(v["security_name"]),
                 "섹터":safe(v["sector"]),"세부산업":safe(v["subsector"]),
                 "국가":safe(v["country"]),"기업집단":safe(v["group"]),
                 "근거URL":safe(v["source_url"]),"분류 기준일":v["as_of_date"]}
                for k,v in metadata.items() if k in holding_codes]
        pd.DataFrame(proofs,columns=["종목코드","종목명","섹터","세부산업",
                                    "국가","기업집단","근거URL","분류 기준일"]).to_excel(
                                        writer,index=False,sheet_name="근거기록")
        for name in writer.sheets:
            writer.sheets[name].freeze_panes(1,0)
            writer.sheets[name].set_column(0,0,28)
            writer.sheets[name].set_column(1,7,46)
    return buf.getvalue()
