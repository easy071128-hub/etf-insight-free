"""ETF Insight — no-cost, session-only public Streamlit frontend."""
from __future__ import annotations
from hashlib import sha256
import streamlit as st
import pandas as pd
from etf_engine import parse_bundle, concentration, candidate_etfs, comparison, excel_report, excel_report_unlinked_krx, manual_krx_reference, compare_krx_component_tables, excel_report_krx_comparison
from reference_match import match_reference_candidates
from catalog_seed import load_bundled_catalog
from research_analysis import (
    TEMPLATE, parse_company_evidence, analyze_labeled_portfolio,
    assess_product_name, compare_labeled_portfolios, excel_report_research,
)
from structure_similarity import (
    score_pair, research_candidates, holdings_differences, explain_pair,
    excel_comparison_report,
)
from industry_taxonomy import taxonomy_rows

st.set_page_config(page_title='ETF Insight | 무료 ETF 분석',page_icon='📊',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>
.block-container{max-width:1150px;padding-top:2rem}
h1{font-size:2.25rem!important;font-weight:800}
[data-testid="stMetricValue"]{font-size:1.5rem}
@media(max-width:600px){.block-container{padding-top:1rem}}
</style>''',unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def _bundled_etfs():
    return load_bundled_catalog()


bundled_catalog,bundled_provenance=_bundled_etfs()
for key,init in [('catalog',dict(bundled_catalog)),('snapshots',{}),('processed',set()),('last_upload_signature',None),('upload_results',[]),('unlinked_reports',{}),('reference_links',{}),('uploader_version',0),('research_meta',{}),('research_source',None),('research_signature',None)]:
    if key not in st.session_state:st.session_state[key]=init

st.title('ETF Insight')
st.caption('무료 ETF 실질구조 분석 · KRX/운용사 Excel·CSV 업로드 · 금융학술제 연구용')
st.info('이 버전은 무료 공개 실험용입니다. 업로드 파일을 영구 DB에 저장하지 않으며, 세션 종료·서버 재시작 시 분석자료가 사라질 수 있습니다. 민감하거나 비공개인 파일은 업로드하지 마세요.')

if bundled_provenance and bundled_provenance.get("error"):
    st.warning("기본 ETF 목록 자동 탑재 오류: "+bundled_provenance["error"])
elif bundled_provenance:
    st.caption(f'사이트 기본 ETF 목록 {bundled_provenance["count"]:,}개 · 자료 수집일 기록 {bundled_provenance["as_of_date"]} · {bundled_provenance.get("date_status","공식 시장 기준일 미검증")} · 정기 갱신 전에는 현재 상장 현황과 다를 수 있습니다.')

st.subheader('KRX 구성종목 파일을 올리면 분석합니다')
files=st.file_uploader('ETF별 구성종목 파일 또는 추가 ETF 기본정보 목록 (최대 12개, 개별 15MB)',type=['xls','xlsx','csv','pdf'],accept_multiple_files=True,key=f"files_{st.session_state.uploader_version}",help='XLSX·CSV·XLS를 인식합니다. PDF는 안전한 표 검증이 어려워 제외하며 업로드 시 안내합니다. 개별 파일 실패로 다른 파일이 중단되지는 않습니다.')
if files:
    signature=tuple((f.name,sha256(f.getvalue()).hexdigest()) for f in files)
    if signature!=st.session_state.last_upload_signature:
        with st.spinner('파일 형식 확인 → ETF 식별 → 비중 검증 → 자동 계산 중...'):
            cat,snaps,seen,reports=parse_bundle([(f.name,f.getvalue()) for f in files],st.session_state.catalog,st.session_state.snapshots,st.session_state.processed)
            st.session_state.catalog=cat;st.session_state.snapshots=snaps
            st.session_state.processed=seen;st.session_state.upload_results=reports
            st.session_state.last_upload_signature=signature
            for report in reports:
                if report.get('analysis_available') and report.get('_standalone_frame') is not None:
                    st.session_state.unlinked_reports[report['source_sha256']]=report

for outcome in st.session_state.upload_results:
    category=outcome.get('category',outcome['status'])
    message=f"{outcome['file']} [{category}] — {outcome['message']}"
    if outcome['status']=='성공':st.success(message)
    elif outcome['status']=='중복':st.caption(message)
    else:st.warning(message)
    if outcome.get('kind'):
        st.caption(f'인식 종류: {outcome["kind"]} · ETF {outcome.get("etf_count",0):,}개 · 구성항목 {outcome.get("holding_count",0):,}개 · 유효 비중: {"확보" if outcome.get("weight_available") else "미확보"} · {"미연결 단독 분석 가능" if outcome.get("_standalone_frame") is not None else ("집중도 분석 가능" if outcome.get("analysis_available") else "집중도 분석 불가")}')
    if outcome.get('preview'):
        with st.expander(f'{outcome["file"]} — 확인된 미연결 구성종목 미리보기 (어떤 ETF에도 연결하지 않음)'):
            st.dataframe(pd.DataFrame(outcome['preview']),hide_index=True,width='stretch')
            st.caption('미리보기는 이 브라우저 세션에서만 유지되며 실제 ETF 포트폴리오·비교 자료로 등록되지 않습니다.')

catalog=st.session_state.catalog
snapshots=st.session_state.snapshots
c1,c2,c3=st.columns(3)
c1.metric('ETF 기본정보',f'{len(catalog):,}개')
c2.metric('비중 포함 자료 확보',f'{len(snapshots):,}개 ETF')
c3.metric('이번 세션 처리한 파일',f'{len(st.session_state.processed):,}개')

if st.button('새 분석 시작 (현재 세션 자료 삭제)',help='현재 브라우저 세션에 올린 목록·구성종목 데이터를 초기화합니다.'):
    for key,value in [('catalog',dict(bundled_catalog)),('snapshots',{}),('processed',set()),('last_upload_signature',None),('upload_results',[]),('unlinked_reports',{}),('reference_links',{}),('research_meta',{}),('research_source',None),('research_signature',None)]:
        st.session_state[key]=value
    # Also clear per-file reference widgets: their keys are deterministic hashes,
    # so uploading the same file again must not reuse an old confirmation.
    for key in list(st.session_state.keys()):
        if key.startswith(('ref_code_', 'ref_confirm_')):
            del st.session_state[key]
    st.session_state.uploader_version += 1
    st.rerun()

search_tab,analysis_tab,similar_tab,report_tab,method_tab=st.tabs(['ETF 검색','실질분석','유사 ETF 비교','Excel 다운로드','검증 방법'])

with search_tab:
    st.subheader('ETF 이름 또는 코드로 검색')
    if not catalog:
        st.info('KRX ETF 기본정보 목록 또는 구성종목 자료를 업로드하면 검색할 수 있습니다.')
    else:
        q=st.text_input('상품명 · 코드 · 기초지수 · 운용사',placeholder='예: 반도체, KODEX, 487230')
        rows=[]
        for code,row in catalog.items():
            if q and q.casefold() not in ' '.join(str(v) for v in row.values()).casefold():continue
            rows.append({'ETF 코드':code,'ETF 상품명':row.get('short_name') or row['name'],'전체 상품명':row['name'],
                         '기초지수':row.get('index_name',''),'운용사':row.get('manager',''),
                         '기초시장':row.get('asset_market',''),'기초자산':row.get('asset_class',''),
                         '상장일':row.get('listing_date',''),'총보수(원본)':row.get('total_fee_source',''),
                         '검증 상태':'집중도 계산 가능' if code in snapshots and concentration(snapshots[code]['frame'])['available'] else ('구성자료 일부 확인' if code in snapshots else '기본정보만')})
        st.caption(f'검색 결과 {len(rows):,}개 / 화면에는 최대 100개 표시')
        st.dataframe(pd.DataFrame(rows[:100]),hide_index=True,width='stretch')

with analysis_tab:
    unlinked=list(st.session_state.unlinked_reports.values())
    if unlinked:
        st.subheader('KRX 시가총액 구성비중 별도 분석')
        st.caption('원본 구성비중을 분석합니다. ETF 참고 이름·교차대조 후보는 실제 ETF 편입비중의 독립 인증이 아닙니다.')
        selected_unlinked=st.selectbox('구성비중 파일',range(len(unlinked)),
            format_func=lambda i:f'{unlinked[i]["file"]} ({unlinked[i]["weight_basis"]})',key='unlinked_analysis')
        r=unlinked[selected_unlinked];stat=r['_standalone_stats'];frame=r['_standalone_frame']
        source_id=r['source_sha256']
        reference=r.get('identity') or st.session_state.reference_links.get(source_id)
        evidence_matches=match_reference_candidates(frame,r['weight_basis'])
        if evidence_matches:
            st.subheader('기존 KRX PDF와 교차대조한 ETF 후보')
            for ev in evidence_matches:
                st.success(f'상위 {ev["matched_rows"]}종목 일치: {ev["etf_name"]} ({ev["etf_code"]}) · 합계 {ev["matched_weight_pct"]:.2f}%')
            if reference and not any(ev['etf_code']==reference['etf_code'] for ev in evidence_matches):
                st.error('직접 연결한 ETF와 PDF 교차대조 후보가 다릅니다. 원본을 다시 확인하거나 연결을 해제하세요.')
        if reference:
            st.success(f'참고용 ETF 표시: {reference["etf_name"]} ({reference["etf_code"]})')
            st.caption(f'참고 근거: {reference["status"]} · {reference["evidence"]} · 구성 기준일: {reference.get("as_of_date") or "원본에서 미확인"}')
            st.caption('참고 표시이며 실제 편입자료로 등록되지 않습니다.')
            if reference['status'].startswith('사용자 지정'):
                if st.button('참고용 ETF 표시 연결 해제',key=f'unlink_{source_id}'):
                    st.session_state.reference_links.pop(source_id,None)
                    st.rerun()
        elif catalog and not any(term in r.get('identity_issue','') for term in ('충돌','상충')):
            with st.expander('참고용 ETF 이름 연결하기 (선택 사항)'):
                st.write('원본 Excel에 ETF 코드가 없어 자동 식별은 불가능합니다. KRX 원본 화면에서 해당 ETF를 직접 확인했을 때만 아래에서 선택하세요.')
                st.caption('연결하지 않아도 단독 분석은 가능합니다. 원본 KRX 화면에서 코드와 이름을 확인했을 때만 입력하세요.')
                entered_code=st.text_input('원본 KRX 페이지에서 확인한 ETF 단축코드 직접 입력',
                    value='',placeholder='예: 091230',max_chars=12,key=f'ref_code_{source_id}')
                selected_code=entered_code.strip().upper()
                selected_item=catalog.get(selected_code) if selected_code else None
                if selected_code and selected_item is None:
                    st.error('입력한 ETF 코드를 업로드한 기본정보 목록에서 찾지 못했습니다. 코드를 다시 확인하세요.')
                if selected_item:
                    st.info(f'코드 {selected_code} → {selected_item.get("short_name") or selected_item["name"]}')
                    st.caption('이 상품명이 원본 KRX 화면에 표시된 상품명과 일치해야 합니다. 종목 구성이 비슷하다는 이유로 연결하지 마세요.')
                confirmed=False
                if selected_item:
                    confirmed=st.checkbox('원본 KRX 페이지의 ETF 코드와 상품명을 모두 대조했고 일치함을 확인했습니다.',
                        value=False,key=f'ref_confirm_{source_id}_{selected_code}')
                if st.button('참고용 ETF 표시 연결',key=f'link_{source_id}',
                             disabled=not (selected_item and confirmed)):
                    try:
                        st.session_state.reference_links[source_id]=manual_krx_reference(r,catalog,selected_code)
                        st.rerun()
                    except ValueError as err:
                        st.warning(str(err))
        elif r.get('identity_issue') and any(term in r.get('identity_issue','') for term in ('충돌','상충')):
            st.error('원본 ETF 식별정보가 서로 충돌합니다. 잘못된 연결을 막기 위해 참고용 연결도 제한합니다.')
        if evidence_matches:
            st.info('검증 범위: 구성종목 비중 계산과 기존 PDF 상위종목 교차대조까지 일치합니다. 실제 ETF 편입비중·동일 기준일은 미확인입니다.')
        else:
            st.info('검증 범위: 구성종목의 시가총액 비중만 계산했습니다. PDF 교차대조 일치 근거 및 ETF 실제 편입비중은 확인되지 않았습니다.')
        with st.expander('검증 근거·분석 한계 자세히 보기'):
            st.write('원본 비중은 시가총액 구성비중이며, ETF 순자산 대비 편입비중이 아닙니다.')
            st.write('ETF 식별자:',reference.get('status') if reference else '원본에서 미확인')
            st.write('ETF 구성 기준일:',reference.get('as_of_date') if reference and reference.get('as_of_date') else '원본에서 미확인')
            for ev in evidence_matches:
                st.write(f'교차대조 후보: {ev["etf_name"]} ({ev["etf_code"]})')
                st.write(f'근거: {ev["reference_source"]} · {ev["match_method"]} · {ev["matched_rows"]}종목 · {ev["matched_weight_pct"]:.2f}%')
                st.write('검증 한계:',ev['verification_status'],ev['warning'])
            st.write('계산:',stat['calculation'])
            st.write('범위:',stat['limitation'])
        st.caption(f'비중 기준: {r["weight_basis"]} · 구성항목 {len(frame)}개 · 원본 비중 합계 {stat["raw_total_pct"]:.2f}%')
        v1,v2,v3,v4=st.columns(4)
        v1.metric('상위 1종목',f'{stat["top1_pct"]:.2f}%')
        v2.metric('상위 3종목',f'{stat["top3_pct"]:.2f}%')
        v3.metric('상위 5종목',f'{stat["top5_pct"]:.2f}%')
        v4.metric('구성종목 집중도',stat['grade'])
        st.caption(f'HHI(현금 포함) {stat["hhi"]:,.2f} · 유효 구성항목 수 {stat["effective_n"]:.2f} · 비현금 종목 {stat["instrument_rows"]}개 · 명시적 현금 {stat["cash_rows"]}개')
        st.write(f'쉽게 설명하면: {stat.get("grade_reason") or "업로드한 구성종목의 비중을 기준으로 집중도를 분류했습니다."} **{stat["grade"]}**으로 분류됩니다.')
        st.caption('이 계산은 업로드한 표의 구성비중에 대한 분석이며, ETF 전체 포트폴리오의 완전성을 보증하지 않습니다.')
        shown=frame[['security_id','security_name','weight_pct']].sort_values('weight_pct',ascending=False).copy()
        shown.columns=['구성종목코드','구성종목명',f'{r["weight_basis"]}(%)']
        st.dataframe(shown,hide_index=True,width='stretch')
        st.download_button('이 KRX 구성비중 분석을 Excel로 저장',data=excel_report_unlinked_krx({**r,'reference_identity':reference,'evidence_candidates':evidence_matches}),
            file_name=f'ETF_Insight_KRX_구성비중_{r["source_sha256"][:12]}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='unlinked_download')
        st.divider()
    st.subheader('세부 산업·국가·기업집단 분류 자료 (선택)')
    st.caption('종목코드별 산업·국가·기업집단에 대한 출처URL과 기준일을 담은 별도 자료가 있을 때만 분석합니다. 기업명이 아닌 실제 공시 근거를 사용하며 복합사업은 비중을 임의로 나누지 않습니다.')
    with st.expander('반도체·2차전지 산업 가치사슬 분류 기준'):
        st.dataframe(pd.DataFrame(taxonomy_rows()),hide_index=True,width='stretch')
        st.caption('위 목록은 분류 참고표이며 기업별로 실제로 해당 사업에 투자한다는 증거가 아닙니다. 삼성전자 등 복합사업 회사는 근거 없는 DRAM·HBM 비중 배분을 하지 않습니다.')
    with st.expander('분류 근거 파일 업로드 및 양식 다운로드'):
        st.download_button('종목별 분류 근거 CSV 양식',data=TEMPLATE,
            file_name='ETF_Insight_기업분류_근거양식.csv',mime='text/csv',key='evidence_template')
        evidence_file=st.file_uploader('섹터·세부산업·국가·기업집단 분류 근거표',
            type=['csv','xls','xlsx'],key=f'research_{st.session_state.uploader_version}')
        if evidence_file is not None:
            payload=evidence_file.getvalue()
            signature=sha256(payload).hexdigest()
            if signature!=st.session_state.research_signature:
                try:
                    metadata,provenance=parse_company_evidence(payload,evidence_file.name)
                    st.session_state.research_meta=metadata
                    st.session_state.research_source=provenance
                except (ValueError,UnicodeError) as err:
                    st.session_state.research_meta={}
                    st.session_state.research_source=None
                    st.error('분류표 등록 실패: '+str(err)[:220])
                except Exception:
                    st.session_state.research_meta={}
                    st.session_state.research_source=None
                    st.error('분류표 형식을 확인할 수 없습니다. 컬럼과 파일을 점검하세요.')
                st.session_state.research_signature=signature
        elif st.session_state.research_signature is not None:
            # Removing the file must also remove its sector/country/group
            # labels; otherwise the UI would silently apply stale evidence.
            st.session_state.research_meta={}
            st.session_state.research_source=None
            st.session_state.research_signature=None
    if st.session_state.research_source:
        st.caption(f'출처 기록된 기업 분류 {len(st.session_state.research_meta)}개 · 파일 {st.session_state.research_source["source_file"]} · 분류 근거는 사용자 제공이며 외부 독립 인증 전')

    st.subheader('실제 편입비중을 기준으로 집중도 계산')
    if not snapshots:
        st.info('ETF별 구성종목 파일을 먼저 올려 주세요. 기본정보 목록만으로는 집중도를 계산할 수 없습니다.')
    else:
        code=st.selectbox('분석할 ETF',sorted(snapshots),format_func=lambda x:f'{catalog[x].get("short_name") or catalog[x]["name"]} ({x})',key='analysis_etf')
        snap=snapshots[code];frame=snap['frame'];meta=snap['meta'];stat=concentration(frame)
        st.caption(f'기준일: {meta["as_of_date"]} · 원본: {snap["filename"]} · 비중 구분: {meta.get("weight_basis","미확인")} · 검증: 파일 구조 및 합계 확인, 발행기관 독립검증 미완료')
        if stat['available']:
            c1,c2,c3,c4=st.columns(4)
            c1.metric('상위 1종목',f'{stat["top1_pct"]:.2f}%');c2.metric('상위 3종목',f'{stat["top3_pct"]:.2f}%')
            c3.metric('상위 5종목',f'{stat["top5_pct"]:.2f}%');c4.metric('집중도',stat['grade'])
            st.caption(f'HHI {stat["hhi"]:,.1f} · 유효 구성항목 수 {stat["effective_n"]:.2f} · 원본 비중 합계 {stat["raw_total_pct"]:.4f}%')
        else:
            st.warning(stat['reason'])
            if stat.get('hhi') is not None:st.metric('구성자산 기준 HHI',f'{stat["hhi"]:,.1f}')
        if not st.session_state.research_meta:
            st.info('기업별 산업·국가·기업집단 분류표가 아직 없습니다. 편입 비중은 분석하지만 산업별 비중은 자료 확보 전까지 미산출합니다.')
        if stat.get('single_stock_flag'):
            st.caption('단일종목 주의: '+stat['single_stock_note'])
        if stat.get('available'):
            st.caption(f'주식 편입종목 {stat["stock_count"]}개 · 현금 {stat["cash_pct"]:.2f}% · 연구 기준: 상위 5개 70% 이상 고집중 / 그 외 상위 3개 40% 이상 집중')
        display=frame[['security_id','security_name','asset_type','weight_pct']].sort_values('weight_pct',ascending=False).copy()
        display.columns=['편입종목코드','편입종목명','자산 유형','비중(%)']
        st.dataframe(display,hide_index=True,width='stretch')
        nav_ready=bool(meta.get('nav_basis_claimed') and not meta.get('pcf_context_detected'))
        labeled=(analyze_labeled_portfolio(snap,st.session_state.research_meta)
                 if nav_ready else {
                     'available':False,
                     'reason':'비중 열에 ETF NAV·순자산 기준이 명시되지 않았거나 PCF 바스켓 자료입니다. 종목 집중도는 원본 기준으로 참고할 수 있지만 NAV 산업비중은 미산출합니다.'
                 })
        verdict=assess_product_name(catalog[code],labeled)
        st.subheader('상품명과 투자구조의 일치 여부')
        st.write(f'**{verdict["grade"]}** · 상품명 명확성: {verdict["clarity"]}')
        st.caption(verdict['reason'])
        st.caption(verdict['verification'])
        st.subheader('세부 산업·국가·기업집단')
        if not labeled.get('available'):
            st.info(labeled.get('reason','분류 검증 자료가 부족합니다.'))
        else:
            cols=st.columns(3)
            cols[0].metric('섹터 집중도',labeled['sector_grade'])
            cols[1].metric('국가 구성(주식 기준)',labeled['country_grade'])
            cols[2].metric('기업집단 집중도',labeled['group_grade'])
            coverage=labeled['coverage_pct']
            st.caption('분류 확인율: '+', '.join(f'{k} {v:.1f}%' for k,v in coverage.items())
                +' · 확인율이 100% 미만이면 해당 항목 판정을 보류합니다.')
            with st.expander('섹터·세부산업별 근거 비중 보기'):
                for kind,title in [('sector','섹터'),('subsector','세부산업'),
                                   ('country','국가'),('group','기업집단')]:
                    values=labeled['breakdowns'][kind]
                    st.write(f'**{title}** · '+('전체 주식 분류 확보' if labeled['complete'][kind] else '일부 종목 미확인'))
                    if values:
                        st.dataframe(pd.DataFrame([{'분류':k,'ETF NAV 비중(%)':round(v,2)}
                            for k,v in values.items()]),hide_index=True,width='stretch')
                st.caption(labeled['basis']+' · '+labeled['provenance'])
                if labeled['name_conflicts']:
                    st.warning('종목명 불일치로 분류에서 제외: '+', '.join(labeled['name_conflicts'][:12]))
                if labeled['future_relative_to_holdings']:
                    st.caption('편입 기준일 이후에 작성된 분류는 검증되지 않아 제외: '+', '.join(labeled['future_relative_to_holdings'][:12]))

with similar_tab:
    st.subheader('ETF 유사 후보 및 구성종목 비교')
    if not catalog:st.info('ETF 기본정보 목록을 업로드해 주세요.')
    else:
        base=st.selectbox('기준 ETF',sorted(catalog),format_func=lambda x:f'{catalog[x].get("short_name") or catalog[x]["name"]} ({x})',key='candidate_base')
        matches=research_candidates(base,catalog,snapshots,st.session_state.research_meta)
        if matches:
            st.dataframe(pd.DataFrame(matches),hide_index=True,width='stretch')
            st.caption('후보는 실제 NAV 편입종목 및 사용자 제출 산업 분류 근거를 우선하고, 자료가 없으면 기초지수·투자주제·단어 기반 검색 후보로 분리합니다. 5요소 점수는 양쪽 편입 기준일과 분류 근거가 모두 충족된 경우에만 표시합니다.')
            with st.expander('후보 근거와 신뢰도 해석'):
                st.markdown('**실제 편입종목 중복:** 동일 종목코드별 두 ETF의 최소 NAV 비중을 합산합니다. **세부 산업:** 기업별 근거가 모두 있을 때 분류 비중의 차이를 비교합니다. **기초지수 동일:** 목록의 지수명이 같습니다. **투자주제·단어 공통:** 실제 종목 유사도가 아닌 검색 단서입니다. 전략(레버리지·인버스·커버드콜·선물)이 다르면 별도 주의 문구를 표시합니다.')
        else:st.info('현재 업로드한 목록에서 비교 후보를 찾지 못했습니다. 더 많은 ETF 기본정보 파일을 넣어 주세요.')
        other_options=[c for c in snapshots if c!=base]
        if base not in snapshots:st.info('기준 ETF의 실제 편입종목이 없으므로 정량 비교를 할 수 없습니다.')
        elif not other_options:st.info('구성종목을 가진 다른 ETF를 추가로 업로드해야 실제 편입 차이를 비교할 수 있습니다.')
        else:
            target=st.selectbox('구성종목 비교 대상 (실제 자료 보유 ETF)',sorted(other_options),format_func=lambda x:f'{catalog[x].get("short_name") or catalog[x]["name"]} ({x})',key='comparison_target')
            pair=score_pair(snapshots[base],snapshots[target],st.session_state.research_meta)
            diff=comparison(snapshots[base],snapshots[target])
            if not pair['basis_supported']:
                diff={'overlap_pct':None,'top5_gap_pct':None,'common':[],
                      'only_a':[],'only_b':[],
                      'reason':'ETF NAV 비중이라는 원본 명시가 없는 구성비중표 또는 PCF 바스켓은 NAV 중복비중 비교에서 제외합니다.'}
            st.caption(diff['reason'])
            differences=holdings_differences(snapshots[base],snapshots[target])
            m1,m2=st.columns(2)
            m1.metric('편입종목 중복 비중',f'{diff["overlap_pct"]:.2f}%' if diff['overlap_pct'] is not None else '미산출')
            m2.metric('상위5 비중 격차',f'{diff["top5_gap_pct"]:.2f}%p' if diff['top5_gap_pct'] is not None else '미산출')
            st.write('공통 편입종목:',(', '.join(diff['common'][:30]) or '확인된 공통 종목 없음') if diff['overlap_pct'] is not None else '확인 가능한 편입종목 데이터 부족')
            with st.expander('각 ETF에만 있는 구성종목'):
                st.write('기준 ETF만:',(', '.join(diff['only_a'][:60]) or '없음') if diff['overlap_pct'] is not None else '검증 불가')
                st.write('비교 ETF만:',(', '.join(diff['only_b'][:60]) or '없음') if diff['overlap_pct'] is not None else '검증 불가')
            with st.expander('공통·단독 구성종목의 비중과 차이(%p) 자세히'):
                if differences:
                    st.dataframe(pd.DataFrame(differences),hide_index=True,width='stretch')
                else:
                    st.caption('양쪽 ETF의 유효한 NAV 편입 비중이 확보되어야 종목별 비중 차이를 계산할 수 있습니다.')
            st.subheader('5요소 ETF 유사도 · 연구용 모델')
            if pair['overall_score'] is not None:
                st.metric('종합 유사도 (제출 근거 기준)',f'{pair["overall_score"]:.2f} / 100')
            else:
                st.info('종합 유사도는 미산출입니다. 없는 데이터를 0점으로 처리하거나 점수 가중치를 재배분하지 않습니다.')
            if pair['components']:
                st.dataframe(pd.DataFrame([
                    {'평가 항목':name,'연구 가중치(%)':weight,
                     '확인된 부분 유사도(점)':pair['components'].get(name),
                     '종합 점수에 사용':pair['overall_score'] is not None}
                    for name,weight in pair['weights'].items()
                ]),hide_index=True,width='stretch')
            with st.expander('유사도 수학적 기준·자료 부족 항목'):
                st.write('종목 중복 = 동일 종목별 최소 NAV 비중 합. 산업·국가·그룹 = 100 − 두 ETF 구성비중 벡터의 절댓값 차이 합÷2. 집중도 = 100 − 상위5 비중 격차(%p). 전체 5요소가 확보되고 기준일이 같을 때만 40·25·15·10·10%를 적용합니다.')
                st.write(pair['source_note'])
                st.write('ETF 편입 기준일:',pair['date_a'],'/ ',pair['date_b'])
                for issue in pair['missing']:
                    st.write('미확인: '+issue)
            detailed=(compare_labeled_portfolios(snapshots[base],snapshots[target],st.session_state.research_meta)
                      if pair['basis_supported'] else
                      {'available':False,'reason':'ETF NAV 비중 종류가 확인된 두 원본이 필요합니다. 일반 구성비중표나 PCF는 산업별 NAV 점수에 사용할 수 없습니다.'})
            st.subheader('세부 산업 구성 비교')
            if detailed['available']:
                st.caption(detailed['provenance']+' · '+detailed['note'])
                for kind,rows in detailed['comparisons'].items():
                    st.write('**'+('섹터' if kind=='sector' else '세부산업')+' 구성 차이**')
                    st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
            else:
                st.info(detailed['reason'])
            st.subheader('초보자에게 쉽게 설명하면')
            st.write(explain_pair(pair,differences,detailed))


    st.divider()
    st.subheader('KRX 구성비중표 2개 직접 비교 (ETF 편입비중 아님)')
    st.caption('ETF 코드가 없어도 시가총액 구성비중표끼리 비교할 수 있습니다. 이것은 파일 간 구성 차이이며, ETF NAV 유사도 계산이 아닙니다.')
    unlinked_reports=list(st.session_state.unlinked_reports.values())
    if len(unlinked_reports)<2:
        st.caption('서로 다른 KRX 시가총액 구성비중 Excel/CSV 파일을 2개 이상 올리면 비교할 수 있습니다.')
    else:
        col_a,col_b=st.columns(2)
        choice_a=col_a.selectbox('자료 A',range(len(unlinked_reports)),
            format_func=lambda i:unlinked_reports[i]['file'],key='krx_compare_a')
        choice_b=col_b.selectbox('자료 B',range(len(unlinked_reports)),index=1,
            format_func=lambda i:unlinked_reports[i]['file'],key='krx_compare_b')
        compared=compare_krx_component_tables(unlinked_reports[choice_a],unlinked_reports[choice_b])
        if not compared['available']:
            st.info(compared['reason'])
        else:
            st.info('확인 범위: 두 개의 시가총액 기준 구성비중표를 직접 비교했습니다. ETF 실제 편입비중이나 ETF의 공식 유사도로 해석하지 마세요.')
            x1,x2,x3=st.columns(3)
            x1.metric('공통 비현금 구성비중',f'{compared["overlap_non_cash_pct"]:.2f}%')
            x2.metric('공통 비현금 종목',f'{compared["common_count"]}개')
            x3.metric('상위3종목 격차',f'{compared["top3_gap_pct"]:.2f}%p')
            st.caption(f'A 집중도: {compared["grade_a"]} · B 집중도: {compared["grade_b"]} · '
                f'A HHI: {compared["hhi_a"]:.2f} · B HHI: {compared["hhi_b"]:.2f}')
            st.dataframe(pd.DataFrame(compared['rows']),hide_index=True,width='stretch')
            with st.expander('두 구성비중표 비교의 검증 한계'):
                st.write(compared['basis'])
                st.write(compared['reason'])
                st.write('두 자료의 ETF 편입 기준일:',compared['source_dates'])
            st.download_button('KRX 구성비중 비교 Excel 다운로드',
                data=excel_report_krx_comparison(compared),
                file_name='ETF_Insight_KRX_구성비중표_비교.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key='krx_comparison_export')

with report_tab:
    st.subheader('분석 결과를 Excel로 저장')
    if not snapshots:st.info('구성종목 자료를 올린 다음 다운로드할 수 있습니다.')
    else:
        selected=st.selectbox('보고서를 만들 ETF',sorted(snapshots),format_func=lambda x:f'{catalog[x].get("short_name") or catalog[x]["name"]} ({x})',key='report_etf')
        data=excel_report(selected,catalog,snapshots)
        st.download_button('Excel 분석 보고서 다운로드',data=data,file_name=f'ETF_Insight_{selected}_{snapshots[selected]["meta"]["as_of_date"]}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',type='primary')
        st.caption('요약·원본 편입종목·검증 상태를 담습니다. 공식 검증이 없는 정보를 사실로 채우지 않습니다.')
        report_meta=snapshots[selected]['meta']
        usable_meta=(st.session_state.research_meta
                     if report_meta.get('nav_basis_claimed') and not report_meta.get('pcf_context_detected')
                     else {})
        research_data=excel_report_research(selected,catalog,snapshots,
            usable_meta,st.session_state.research_source)
        st.download_button('실질 투자구조·기업별 분류 근거 보고서 다운로드',
            data=research_data,file_name=f'ETF_Insight_구조분석_{selected}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            key='research_report_download')
        if not st.session_state.research_meta:
            st.caption('기업별 분류 근거가 없으므로 두 번째 보고서에는 자료부족 판정만 표시됩니다.')
        compare_options=[c for c in snapshots if c!=selected]
        if compare_options:
            st.subheader('ETF A/B 상세 비교 보고서')
            peer=st.selectbox('비교할 다른 ETF',sorted(compare_options),
                format_func=lambda x:f'{catalog[x].get("short_name") or catalog[x]["name"]} ({x})',
                key='report_compare_target')
            report_pair=excel_comparison_report(selected,peer,catalog,snapshots,
                st.session_state.research_meta)
            st.download_button('두 ETF 구성종목·산업·5요소 근거 비교 Excel 다운로드',
                data=report_pair,file_name=f'ETF_Insight_비교_{selected}_{peer}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                key='pair_excel_download')
            st.caption('종합점수가 산출되지 않아도 부족한 항목과 근거·기준일을 Excel에 기록합니다.')

with method_tab:
    st.subheader('어떻게 계산하나요?')
    st.markdown('''**종목 집중도:** 상위 5종목 70% 이상은 고집중, 그 외 상위 3종목 40% 이상은 집중, 나머지는 분산입니다. 단일 종목 20% 이상은 등급과 별도의 주의 표시입니다. 연구자가 설정한 임계값입니다.

**KRX 시가총액 구성비중:** KRX 자료에 그 이름으로 표시된 숫자를 이용해 별도의 **구성종목 집중도**를 계산합니다. 명시된 현금 항목만 상위 종목 계산에서 제외하고, HHI에는 포함합니다. 원본 합계가 99.95~100.05%이면 계산 시 100%로 정규화합니다. **이는 ETF 순자산 대비 편입비중의 대체값이 아닙니다.** 미연결 구성비중의 상위 10개 구성종목·비중이 검토된 KRX PDF 연구자료와 모두 일치하면 참고 ETF 후보만 표시합니다. 동일한 공식 기준일·ETF 편입비중 또는 인증된 ETF 동일성이 확인되었다고 보지 않습니다. 원본 식별자가 없을 때 사용자가 직접 연결해도 ETF 편입비중이나 종합 유사도 계산에는 사용하지 않습니다.

**HHI:** 구성항목별 비중(%)을 제곱해 합산합니다. **유효 구성항목 수:** 10,000 / HHI입니다.

**KRX 구성비중표 직접 비교:** ETF 코드가 없는 두 파일이라도, 각각 검증된 시가총액 구성비중표라면 공통 비현금 종목의 최소비중 합과 구성비중 차이를 비교합니다. 이는 두 시가총액 표의 차이이며 ETF NAV 편입 유사도가 아닙니다.

**유사 ETF 후보 선정:** 단순 비중 열이나 PCF 표를 ETF NAV로 가정하지 않습니다. 원본 비중 열에 NAV·순자산 기준이 명시된 두 자료가 있으면 중복비중 50% 이상을 우선 후보로 찾습니다. 검증 범위 내 세부 산업 유사도 80점 이상도 별도 후보로 찾습니다. 나머지는 동일 기초지수, 투자주제, 단어 공통 순으로 탐색하고 검색 후보라는 사실을 밝힙니다. 50%와 80점은 연구용 탐색 임계값입니다. 완전한 실제 비중과 업로드한 세부 산업·국가·기업집단 근거, 동일 편입 기준일이 모두 있을 때만 유사도 5요소(40·25·15·10·10%) 점수를 계산하며, 그렇지 않으면 종합점수를 미산출합니다. 기업 분류표의 원출처는 별도로 인증하지 않습니다.

**섹터·기업집단·국가:** 종목별 출처 URL과 기준일이 포함된 별도 분류표를 올린 경우에만 분석합니다. 회사 이름이나 종목코드만으로 산업·국가·사업별 매출비중을 추정하지 않습니다. 기업집단 집중도 판정은 국내형 주식 구성 기준에만 적용하며, 전체 주식 분류가 누락되면 자료부족으로 표시합니다.

**PDF 처리:** KRX PDF에 표시된 상위 10종목은 전체 편입자료가 아닐 수 있으며 시가총액 기준 비중과 ETF 순자산 대비 비중이 다를 수 있어 현재 자동 분석에서 제외합니다. Excel/CSV 원본을 사용하세요.

**검증 한계:** 이 무료 버전은 원본 파일 형식·ETF 식별자·기준일·비중 합계를 검사합니다. 인터넷 기업정보 API 연결, 분류 근거 검증, 서버 영구저장, 사용자 계정, 업로드 이력은 제공하지 않습니다. 투자 추천이 아닙니다.''')

st.divider()
st.caption('ETF Insight · 금융학술제 연구 데모 · 자료의 저작권과 제공기관 이용약관을 준수해 주세요. 무료 호스팅의 자원 제한으로 대량 업로드는 처리되지 않을 수 있습니다.')
