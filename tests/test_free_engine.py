import io
from pathlib import Path
import pandas as pd
import pytest
from etf_engine import parse_bundle,concentration,candidate_etfs,comparison,excel_report,parse_holdings_auto

WEIGHTS=[17.92,17.4,16.08,12.1,11.56,8.8,6,4,3.14,3]

def hold_csv(code='487230',weights=WEIGHTS,unit='percent',date='2026-11-10',with_type=True):
    h='종목코드,종목명,비중(%),자산유형,ETF코드,ETF상품명,기준일' if unit=='percent' else '종목코드,종목명,비중,자산유형,ETF코드,ETF상품명,기준일'
    a=[h]
    for i,w in enumerate(weights):
        v=w if unit=='percent' else w/100
        a.append(f'A{i:05d},연구용기업{i},{v},{"주식" if with_type else ""},{code},합성 연구 ETF {code},{date}')
    return ('\n'.join(a)+'\n').encode('utf-8-sig')

def list_csv():
    return '종목코드,종목명,운용사,기초지수\n487230,합성 연구 ETF 487230,가상운용,가상AI전력\n487231,합성 연구 ETF 487231,가상운용,가상AI전력\n'.encode('utf-8-sig')

def test_catalog_and_holdings_upload_one_batch():
    cat,sn,seen,result=parse_bundle([('portfolio.csv',hold_csv()),('KRX_list.csv',list_csv())]); assert len(cat)==2 and len(sn)==1
    assert all(r['status']=='성공' for r in result)
    metrics=concentration(sn['487230']['frame'])
    assert metrics['top1_pct']==pytest.approx(17.92)
    assert metrics['top3_pct']==pytest.approx(51.4)
    assert metrics['top5_pct']==pytest.approx(75.06)
    assert metrics['grade']=='고집중'
    assert metrics['hhi']==pytest.approx(1310.796,abs=.01)


def test_fraction_upload_is_scaled():
    df,m=parse_holdings_auto(hold_csv(unit='fraction'),'demo.csv')
    assert m['unit']=='fraction' and df.weight_pct.sum()==pytest.approx(100)


def test_rounded_100_02_accepted():
    df,m=parse_holdings_auto(hold_csv(weights=[50,50.02]),'demo.csv')
    assert df.weight_pct.sum()==pytest.approx(100.02)


def test_wrong_sum_rejected():
    c,s,seen,result=parse_bundle([('wrong.csv',hold_csv(weights=[50,45]))])
    assert len(s)==0 and result[0]['status']=='확인 필요'


def test_quantity_without_weights_not_registered_as_catalog():
    file='종목코드,종목명,수량,평가금액\n111111,A,2,500000\n222222,B,3,200000\n'.encode()
    c,s,seen,result=parse_bundle([('unknown.csv',file)])
    assert not c and not s and result[0]['status']=='확인 필요'


def test_missing_date_rejected():
    _,s,_,result=parse_bundle([('no_date.csv',hold_csv(date=''))])
    assert not s and '편입 기준일' in result[0]['message']


def test_invalid_extension_not_processed():
    c,s,_,r=parse_bundle([('attack.exe',b'abcd')])
    assert not c and not s and r[0]['status']=='확인 필요'


def test_duplicate_only_processed_once():
    one=[('sample.csv',hold_csv())]
    c,s,seen,r=parse_bundle(one)
    c2,s2,seen2,r2=parse_bundle(one,c,s,seen)
    assert r2[0]['status']=='중복' and len(s2)==1


def test_comparison_missing_overall_score():
    c,s,_,r=parse_bundle([('a.csv',hold_csv()),('b.csv',hold_csv(code='487231'))])
    result=comparison(s['487230'],s['487231'])
    assert result['overall'] is None and result['overlap_pct']==pytest.approx(100)
    assert result['top5_gap_pct']==pytest.approx(0)
    candidates=candidate_etfs('487230',c,s)
    assert candidates


def test_excel_report():
    c,s,_,r=parse_bundle([('data.csv',hold_csv())])
    report=excel_report('487230',c,s)
    assert report.startswith(b'PK')
    frame=pd.read_excel(io.BytesIO(report),sheet_name='요약')
    assert '원본 SHA256' in set(frame['항목'])


def test_xlsx_format(tmp_path):
    df=pd.read_csv(io.BytesIO(hold_csv()),encoding='utf-8-sig')
    buf=io.BytesIO()
    with pd.ExcelWriter(buf,engine='openpyxl') as w:df.to_excel(w,index=False,header=True,sheet_name='PCF')
    c,s,_,r=parse_bundle([('PCF.xlsx',buf.getvalue())])
    assert r[0]['status']=='성공' and '487230' in s


def test_html_xls_format():
    df=pd.read_csv(io.BytesIO(hold_csv()),encoding='utf-8-sig')
    html=('<html><meta charset="utf-8">'+df.to_html(index=False)+'</html>').encode('utf-8')
    c,s,_,r=parse_bundle([('PCF.xls',html)])
    assert r[0]['status']=='성공' and '487230' in s


def test_individual_failure_does_not_block_other():
    c,s,_,r=parse_bundle([('bad.csv',b'xxx\nzzz'),('good.csv',hold_csv())])
    assert '487230' in s and len(r)==2 and {x['status'] for x in r}=={'성공','확인 필요'}


def test_session_isolation_no_global_database():
    c1,s1,_,_=parse_bundle([('some.csv',hold_csv())])
    c2,s2,_,_=parse_bundle([])
    assert c1 and s1 and not c2 and not s2
