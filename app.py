"""ETF Insight — no-cost, session-only public Streamlit frontend."""
from __future__ import annotations
from hashlib import sha256
import streamlit as st
import pandas as pd
from etf_engine import parse_bundle, concentration, candidate_etfs, comparison, excel_report

st.set_page_config(page_title='ETF Insight | 무료 ETF 분석',page_icon='📊',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>
.block-container{max-width:1150px;padding-top:2rem}
h1{font-size:2.25rem!important;font-weight:800}
[data-testid="stMetricValue"]{font-size:1.5rem}
@media(max-width:600px){.block-container{padding-top:1rem}}
</style>''',unsafe_allow_html=True)

for key,init in [('catalog',{}),('snapshots',{}),('processed',set()),('last_upload_signature',None),('upload_results',[]),('uploader_version',0)]:
    if key not in st.session_state:st.session_state[key]=init

st.title('ETF Insight')
st.caption('무료 ETF 실질구조 분석 · KRX/운용사 Excel·CSV 업로드 · 금융학술제 연구용')
st.info('이 버전은 무료 공개 실험용입니다. 업로드 파일을 영구 DB에 저장하지 않으며, 세션 종료·서버 재시작 시 분석자료가 사라질 수 있습니다. 민감하거나 비공개인 파일은 업로드하지 마세요.')

st.subheader('KRX 파일을 올리면 자동으로 분석합니다')
files=st.file_uploader('ETF 기본정보 목록 또는 ETF별 구성종목 파일 (최대 12개, 개별 15MB)',type=['xls','xlsx','csv'],accept_multiple_files=True,key=f"files_{st.session_state.uploader_version}",help='ETF 기본정보와 구성종목 파일을 함께 넣어도 됩니다. 개별 파일 실패로 다른 파일이 중단되지는 않습니다.')
if files:
    signature=tuple((f.name,sha256(f.getvalue()).hexdigest()) for f in files)
    if signature!=st.session_state.last_upload_signature:
        with st.spinner('파일 형식 확인 → ETF 식별 → 비중 검증 → 자동 계산 중...'):
            cat,snaps,seen,reports=parse_bundle([(f.name,f.getvalue()) for f in files],st.session_state.catalog,st.session_state.snapshots,st.session_state.processed)
            st.session_state.catalog=cat;st.session_state.snapshots=snaps
            st.session_state.processed=seen;st.session_state.upload_results=reports
            st.session_state.last_upload_signature=signature

for outcome in st.session_state.upload_results:
    message=f"{outcome['file']} — {outcome['message']}"
    if outcome['status']=='성공':st.success(message)
    elif outcome['status']=='중복':st.caption(message)
    else:st.warning(message)

catalog=st.session_state.catalog
snapshots=st.session_state.snapshots
c1,c2,c3=st.columns(3)
c1.metric('ETF 기본정보',f'{len(catalog):,}개')
c2.metric('구성종목 확보',f'{len(snapshots):,}개 ETF')
c3.metric('이번 세션 처리한 파일',f'{len(st.session_state.processed):,}개')

if st.button('새 분석 시작 (현재 세션 자료 삭제)',help='현재 브라우저 세션에 올린 목록·구성종목 데이터를 초기화합니다.'):
    for key,value in [('catalog',{}),('snapshots',{}),('processed',set()),('last_upload_signature',None),('upload_results',[])]:
        st.session_state[key]=value
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
            rows.append({'ETF 코드':code,'ETF 상품명':row['name'],'기초지수':row.get('index_name',''),'운용사':row.get('manager',''),
                         '구성종목': '확보' if code in snapshots else '기본정보만'})
        st.caption(f'검색 결과 {len(rows):,}개 / 화면에는 최대 100개 표시')
        st.dataframe(pd.DataFrame(rows[:100]),hide_index=True,use_container_width=True)

with analysis_tab:
    st.subheader('실제 편입비중을 기준으로 집중도 계산')
    if not snapshots:
        st.info('ETF별 구성종목 파일을 먼저 올려 주세요. 기본정보 목록만으로는 집중도를 계산할 수 없습니다.')
    else:
        code=st.selectbox('분석할 ETF',sorted(snapshots),format_func=lambda x:f'{catalog[x]["name"]} ({x})',key='analysis_etf')
        snap=snapshots[code];frame=snap['frame'];meta=snap['meta'];stat=concentration(frame)
        st.caption(f'기준일: {meta["as_of_date"]} · 원본: {snap["filename"]} · 검증: 파일 구조 및 합계 확인, 발행기관 독립검증 미완료')
        if stat['available']:
            c1,c2,c3,c4=st.columns(4)
            c1.metric('상위 1종목',f'{stat["top1_pct"]:.2f}%');c2.metric('상위 3종목',f'{stat["top3_pct"]:.2f}%')
            c3.metric('상위 5종목',f'{stat["top5_pct"]:.2f}%');c4.metric('집중도',stat['grade'])
            st.caption(f'HHI {stat["hhi"]:,.1f} · 유효 구성항목 수 {stat["effective_n"]:.2f} · 원본 비중 합계 {stat["raw_total_pct"]:.4f}%')
        else:
            st.warning(stat['reason'])
            if stat.get('hhi') is not None:st.metric('구성자산 기준 HHI',f'{stat["hhi"]:,.1f}')
        st.warning('산업·국가·기업집단 공식 분류 자료가 연결되지 않았습니다. 해당 집중도와 검증 커버리지는 산출하지 않습니다.')
        display=frame[['security_id','security_name','asset_type','weight_pct']].sort_values('weight_pct',ascending=False).copy()
        display.columns=['편입종목코드','편입종목명','자산 유형','비중(%)']
        st.dataframe(display,hide_index=True,use_container_width=True)

with similar_tab:
    st.subheader('ETF 유사 후보 및 구성종목 비교')
    if not catalog:st.info('ETF 기본정보 목록을 업로드해 주세요.')
    else:
        base=st.selectbox('기준 ETF',sorted(catalog),format_func=lambda x:f'{catalog[x]["name"]} ({x})',key='candidate_base')
        matches=candidate_etfs(base,catalog,snapshots)
        if matches:
            st.dataframe(pd.DataFrame(matches),hide_index=True,use_container_width=True)
            st.caption('같은 단어 또는 연구 유형은 비교 후보를 찾는 단서일 뿐, 실제 편입 구조의 유사도 증거가 아닙니다.')
        else:st.info('현재 업로드한 목록에서 비교 후보를 찾지 못했습니다. 더 많은 ETF 기본정보 파일을 넣어 주세요.')
        other_options=[c for c in snapshots if c!=base]
        if base not in snapshots:st.info('기준 ETF의 실제 편입종목이 없으므로 정량 비교를 할 수 없습니다.')
        elif not other_options:st.info('구성종목을 가진 다른 ETF를 추가로 업로드해야 실제 편입 차이를 비교할 수 있습니다.')
        else:
            target=st.selectbox('구성종목 비교 대상 (실제 자료 보유 ETF)',sorted(other_options),format_func=lambda x:f'{catalog[x]["name"]} ({x})',key='comparison_target')
            diff=comparison(snapshots[base],snapshots[target]);st.warning(diff['reason'])
            m1,m2=st.columns(2)
            m1.metric('편입종목 중복 비중',f'{diff["overlap_pct"]:.2f}%' if diff['overlap_pct'] is not None else '미산출')
            m2.metric('상위5 비중 격차',f'{diff["top5_gap_pct"]:.2f}%p' if diff['top5_gap_pct'] is not None else '미산출')
            st.write('공통 편입종목:',', '.join(diff['common'][:30]) or '확인된 공통 종목 없음')
            with st.expander('각 ETF에만 있는 구성종목'):
                st.write('기준 ETF만:',', '.join(diff['only_a'][:60]) or '없음')
                st.write('비교 ETF만:',', '.join(diff['only_b'][:60]) or '없음')

with report_tab:
    st.subheader('분석 결과를 Excel로 저장')
    if not snapshots:st.info('구성종목 자료를 올린 다음 다운로드할 수 있습니다.')
    else:
        selected=st.selectbox('보고서를 만들 ETF',sorted(snapshots),format_func=lambda x:f'{catalog[x]["name"]} ({x})',key='report_etf')
        data=excel_report(selected,catalog,snapshots)
        st.download_button('Excel 분석 보고서 다운로드',data=data,file_name=f'ETF_Insight_{selected}_{snapshots[selected]["meta"]["as_of_date"]}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',type='primary')
        st.caption('요약·원본 편입종목·검증 상태를 담습니다. 공식 검증이 없는 정보를 사실로 채우지 않습니다.')

with method_tab:
    st.subheader('어떻게 계산하나요?')
    st.markdown('''**종목 집중도:** 단일 주식 20% 이상 또는 상위 5주식 70% 이상은 고집중, 그 외 상위 3주식 40% 이상은 집중, 나머지는 분산으로 표시합니다.

**HHI:** 구성항목별 비중(%)을 제곱해 합산합니다. **유효 구성항목 수:** 10,000 / HHI입니다.

**유사도:** 편입종목 코드의 중복비중과 상위 5주식 비중 차이는 일부 계산할 수 있으나, 검증된 세부 산업·국가·기업집단 정보가 없으면 종합 유사도 점수를 만들지 않습니다.

**검증 한계:** 이 무료 버전은 원본 파일 형식·ETF 식별자·기준일·비중 합계를 검사합니다. 인터넷 기업정보 API 연결, 분류 근거 검증, 서버 영구저장, 사용자 계정, 업로드 이력은 제공하지 않습니다. 투자 추천이 아닙니다.''')

st.divider()
st.caption('ETF Insight · 금융학술제 연구 데모 · 자료의 저작권과 제공기관 이용약관을 준수해 주세요. 무료 호스팅의 자원 제한으로 대량 업로드는 처리되지 않을 수 있습니다.')
