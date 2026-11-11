"""Stateless ETF Insight engine: adapted from the validated existing parsing engine.
No database, no server-side file storage, no speculative financial facts.
"""
from __future__ import annotations
"""Lossless file ingestion: explicit weight units, worksheet/header detection, identity guard."""
from datetime import date
from hashlib import sha256
from io import BytesIO,StringIO
from pathlib import Path
import csv,re
import pandas as pd

CODE_RE=re.compile(r'^[0-9A-Z]{6,12}$')
SYNONYMS={
 'security_id':['종목코드','단축코드','종목 코드','isin','isin코드','securitycode','ticker','stockcode','code','symbol','편입종목코드','주식코드'],
 'security_name':['종목명','종목 명','구성종목명','종목','name','securityname','stockname','종목명칭','종목명(영문)'],
 'weight_pct':['시가총액 구성비중','시가총액 구성비중(%)','시가총액기준 구성비중','시가총액기준구성비중','비중(%)','비중','비율(%)','구성비(%)','편입비중','편입비중(%)','비율','weight(%)','weight','weightpct','wgt','구성비','투자비중(%)','투자비중'],
 'asset_type':['자산유형','자산종류','자산구분','assettype','type','편입자산구분','주식/현금','구분'],
 'quantity':['수량','보유수량','quantity','shares','보유주식수','주식수','주식수(계약수)'],
 'etf_code':['etfcode','etf단축코드','etf종목코드','etf코드','펀드코드'],
 'etf_name':['etfname','etf명','etf상품명','펀드명'],
 'as_of_date':['기준일','편입기준일','pcf기준일','asofdate']}

def norm(s):return re.sub(r'[\s_\-\[\]{}()]','',str(s).strip().lower().replace('％','%'))
LOOKUP={norm(v):k for k,options in SYNONYMS.items() for v in options}

def _select_header(raw):
    best=None
    for i in range(min(len(raw),22)):
        cells=[str(v).strip() if pd.notna(v) else '' for v in raw.iloc[i].tolist()]
        found=[LOOKUP[norm(c)] for c in cells if norm(c) in LOOKUP]
        score=len(set(found))*3+int('weight_pct' in found)*5+int('security_name' in found)*3+int('security_id' in found)*3
        if best is None or score>best[0]:best=(score,i,found)
    return best

def _parse_candidates(content,file_name):
    ext=Path(file_name).suffix.lower()
    if ext not in ('.xls','.xlsx','.csv'):raise ValueError('지원되지 않는 확장자입니다 (.xls, .xlsx, .csv 지원)')
    if not content:raise ValueError('빈 파일입니다.')
    if len(content)>35*1024*1024:raise ValueError('파일 크기가 35MB를 초과합니다.')
    if ext=='.csv':
        enc=None
        for e in ('utf-8-sig','cp949','utf-16','utf-8'):
            try:decoded=content.decode(e);enc=e;break
            except UnicodeError:continue
        if enc is None:raise ValueError('CSV 문자 인코딩을 확인할 수 없습니다.')
        try:delimiter=csv.Sniffer().sniff(decoded[:12000],delimiters=',;\t|').delimiter
        except csv.Error:delimiter=','
        yield 'CSV',pd.read_csv(StringIO(decoded),header=None,sep=delimiter,dtype=str,keep_default_na=False)
    elif content.lstrip()[:20].lower().startswith((b'<html',b'<table',b'<!doctype')):
        try:
            html_text=None
            for encoding in ('utf-8-sig','cp949','euc-kr'):
                try:
                    html_text=content.decode(encoding)
                    break
                except UnicodeError:
                    continue
            if html_text is None:raise ValueError('HTML형 XLS 인코딩을 확인할 수 없습니다.')
            for i,table in enumerate(pd.read_html(StringIO(html_text),header=None)):
                # HTML <th> cells may be promoted to DataFrame column headers automatically.
                header=[str(x) for x in table.columns]
                if any(norm(x) in LOOKUP for x in header):
                    table=pd.concat([pd.DataFrame([header],columns=table.columns),table.reset_index(drop=True)],ignore_index=True)
                yield 'HTML표'+str(i+1),table.astype(str)
        except (ImportError,ValueError) as e:raise ValueError('HTML 형식 XLS를 읽을 수 없습니다. lxml을 설치하세요: '+str(e)) from e
    else:
        try:
            sheets=pd.read_excel(BytesIO(content),sheet_name=None,header=None,dtype=str,keep_default_na=False,
                    engine='xlrd' if ext=='.xls' else 'openpyxl')
        except ImportError as e:raise ValueError('Excel 형식 읽기 도구가 없습니다. pip install openpyxl xlrd: '+str(e)) from e
        except Exception as e:raise ValueError('Excel 읽기 실패: 확장자와 실제 파일 형식을 확인하세요. '+str(e)) from e
        for s,df in sheets.items():yield str(s),df

def _number(value):
    if pd.isna(value) or str(value).strip() in ('','-','—'):return None
    text=str(value).strip().replace(',','').replace('％','%').replace('−','-')
    pct='%' in text
    text=text.replace('%','')
    try:return float(text),pct
    except (ValueError,OverflowError):raise ValueError('비중이 숫자가 아닙니다: '+str(value))

def parse_upload(content:bytes,file_name:str,weight_unit='percent'):
    """Return normalized data and diagnostic dict. Never guess weight column from quantity/money.

    weight_unit=percent or fraction; original numeric string and selected sheet kept.
    """
    if weight_unit not in ('percent','fraction'):raise ValueError('비중 단위는 percent 또는 fraction이어야 합니다.')
    candidate=None;eligible_sheets=[]
    for sheet,raw in _parse_candidates(content,file_name):
        if raw is None or raw.empty:continue
        score,index,found=_select_header(raw)
        if candidate is None or score>candidate[0]:candidate=(score,sheet,index,raw)
        if score>=8 and 'weight_pct' in found and ('security_name' in found or 'security_id' in found):
            eligible_sheets.append(sheet)
    if len(eligible_sheets)>1:
        raise ValueError('구성종목과 비중이 있는 시트가 여러 개입니다. 서로 다른 ETF를 잘못 합치지 않도록 시트별 파일로 나눠 업로드해 주세요: '+', '.join(eligible_sheets[:6]))
    if candidate is None or candidate[0]<8:raise ValueError('구성종목명/코드와 비중(%) 열을 확인하지 못했습니다. 다른 시트·머리글을 확인하세요. 수량/평가금액을 비중으로 대체하지 않습니다.')
    score,sheet,header,raw=candidate
    original_head=[str(x).strip() for x in raw.iloc[header]]
    weight_headers=[name for name in original_head if LOOKUP.get(norm(name))=='weight_pct']
    if len(weight_headers)!=1:
        # If NAV weight and market-cap weight coexist, guessing the first is unsafe.
        raise ValueError('서로 다른 비중 열이 여러 개 있습니다. 사용할 비중의 종류를 원본에서 구분한 파일을 올려 주세요: '+', '.join(weight_headers[:4]))
    columns=[];present=set()
    for col in original_head:
        mapped=LOOKUP.get(norm(col),col.strip())
        if mapped in present:mapped='원본중복_'+col
        columns.append(mapped);present.add(mapped)
    df=raw.iloc[header+1:].copy();df.columns=columns
    if 'weight_pct' not in df or 'security_name' not in df and 'security_id' not in df:raise ValueError('확인된 비중 열과 종목 식별 열이 없습니다.')
    # Only rows with a holding identifier are retained (footer/sum rows excluded).
    for key in ['security_name','security_id']:
        if key not in df:df[key]=''
        df[key]=df[key].fillna('').astype(str).str.strip().str.replace(r'\.0$','',regex=True) if key=='security_id' else df[key].fillna('').astype(str).str.strip()
    if 'security_id' in df:
        # KRX often saves a domestic six-digit stock code as an Excel NUMBER:
        # 005930 -> 5930. Restore only purely numeric identifiers up to 6 digits;
        # leave 12-character ISINs and alphanumeric cash identifiers unchanged.
        df['security_id']=df['security_id'].map(lambda x:x.zfill(6) if x.isdecimal() and len(x)<=6 else x)
    df=df[(df.security_name!='') | (df.security_id!='')].copy()
    df=df[~df.security_name.str.match(r'^(합계|총계|total|subtotal|비중합계)$',case=False,na=False)].copy()
    if not len(df):raise ValueError('실제 구성종목 데이터 행이 없습니다.')
    missing_ids=df.security_id.eq('')
    if missing_ids.any():df.loc[missing_ids,'security_id']=['UNKNOWN_'+str(i) for i in df.index[missing_ids]]
    if 'asset_type' not in df:df['asset_type']='미확인'
    df.asset_type=df.asset_type.fillna('미확인').astype(str).str.strip().replace('', '미확인')
    def typ(x):
        x=str(x).strip().lower()
        if any(v in x for v in ('주식','equity','stock','보통주','common')):return '주식'
        if any(v in x for v in ('현금','cash','예수금','원화현금','외화현금')):return '현금'
        if any(v in x for v in ('채권','bond','fixed income')):return '채권'
        return '미확인' if x in ('','nan','none','미확인') else x
    df['asset_type']=df.asset_type.map(typ)
    vals=[];rawvals=[]
    for v in df.weight_pct:
        r=_number(v)
        if r is None:vals.append(None);rawvals.append(str(v));continue
        number,is_pct=r
        if not __import__('math').isfinite(number):raise ValueError('NaN/무한대 비중은 등록할 수 없습니다.')
        vals.append(number if is_pct or weight_unit=='percent' else number*100)
        rawvals.append(str(v))
    df['weight_original']=rawvals
    df['weight_pct']=vals
    if 'quantity' not in df:df['quantity']=''
    for k in ['etf_code','etf_name','as_of_date']:
        if k not in df:df[k]=''
    df['source_sheet']=sheet
    df['source_row']=[int(i+1) for i in df.index]
    df=df[['security_id','security_name','asset_type','weight_pct','weight_original','quantity','etf_code','etf_name','as_of_date','source_sheet','source_row']].reset_index(drop=True)
    weight_header=next((str(v).strip() for v in original_head if LOOKUP.get(norm(v))=='weight_pct'),'')
    weight_basis='시가총액 기준 비중' if '시가총액' in weight_header else 'ETF 편입비중(원본 표기)'
    return df,{'sheet':sheet,'header_row':header+1,'source_rows':len(raw)-header-1,'recognized_fields':found,
               'sha256':sha256(content).hexdigest(),'unit':weight_unit,'weight_header':weight_header,'weight_basis':weight_basis}

def validate_holdings(df):
    issues=[];warnings=[]
    if df is None or df.empty:return {'eligible':False,'issues':['구성종목이 없습니다.'],'warnings':[],'total_pct':0,'n':0,'stock_pct':0,'coverage':0}
    if 'security_id' not in df or 'security_name' not in df or 'weight_pct' not in df:
        return {'eligible':False,'issues':['필수 열 누락'],'warnings':[],'total_pct':0,'n':0,'stock_pct':0,'coverage':0}
    weights=pd.to_numeric(df.weight_pct,errors='coerce')
    if weights.isna().any():issues.append(f'비중 누락/비숫자 {int(weights.isna().sum())}행')
    if (~weights.isna() & (weights<0)).any():issues.append('음수 비중은 지원하지 않습니다.')
    if (df.security_name.fillna('').astype(str).str.strip()=='').any():warnings.append('종목명이 일부 없습니다: 출처에서 확인 필요')
    if df.security_id.astype(str).duplicated().any():warnings.append('동일 종목코드의 복수 행이 있습니다. 코드별 합산 분석으로 처리합니다.')
    if 'asset_type' in df and (df.assign(_code=df.security_id.astype(str)).groupby('_code')['asset_type'].nunique(dropna=False)>1).any():
        issues.append('동일 종목코드에 서로 다른 자산유형이 존재하여 합산할 수 없습니다.')
    if (df.assign(_code=df.security_id.astype(str),_name=df.security_name.fillna('').astype(str).str.strip())
          .groupby('_code')['_name'].nunique(dropna=False)>1).any():
        issues.append('동일 종목코드에 서로 다른 종목명이 존재하여 합산할 수 없습니다.')
    total=float(weights.sum())
    if total<=0:issues.append('비중 합계가 0%입니다. 올바른 시트·비중 열·단위를 확인하세요.')
    if abs(total-100)>0.05:issues.append(f'전체 비중 합계 {total:.4f}%: 100%±0.05%p 허용범위를 벗어났습니다.')
    if abs(total-100)<=0.05 and abs(total-100)>1e-6:warnings.append(f'반올림 합계 {total:.4f}% (원본 비중 보존; 분석시 전체 합계로 정규화)')
    if (weights>100.05).any():issues.append('개별 항목 비중이 100%를 초과합니다.')
    if df.security_id.astype(str).str.startswith('UNKNOWN_').any():warnings.append('일부 종목코드 미확인: 공통 종목 유사도 계산 불가')
    stock=df.get('asset_type',pd.Series(['미확인']*len(df))).astype(str).eq('주식')
    return {'eligible':not issues,'issues':issues,'warnings':warnings,'total_pct':total,'n':int(df.loc[stock,'security_id'].nunique()),
            'stock_pct':float(weights[stock].sum()),'coverage':float(weights.notna().sum()/len(df)),
            'row_count':len(df),'normalized_total_pct':100 if total>0 else None}

def validate_identity(df,etf_code,etf_name,as_of_date):
    code=str(etf_code).strip().upper()
    if not CODE_RE.fullmatch(code):raise ValueError('ETF 단축코드는 영문/숫자 6~12자여야 합니다.')
    if not str(etf_name).strip():raise ValueError('ETF 상품명이 없습니다.')
    try:d=date.fromisoformat(str(as_of_date))
    except Exception as e:raise ValueError('ETF 실제 PCF 기준일은 YYYY-MM-DD 형식이어야 합니다.') from e
    if d>date.today():raise ValueError('기준일이 미래입니다.')
    for col,val in [('etf_code',code),('etf_name',str(etf_name).strip()),('as_of_date',str(as_of_date))]:
        if col not in df:continue
        seen=set(df[col].dropna().astype(str).str.strip())-{''}
        if col=='etf_code':
            seen={x.upper().removesuffix('.0').zfill(6) for x in seen}
        elif col=='as_of_date':
            parsed={date_value(x) for x in seen}
            if None in parsed:raise ValueError('원본 파일에 인식할 수 없는 기준일이 있습니다.')
            seen=parsed
        if seen and seen!={val}:raise ValueError('원본 파일 '+col+' 값이 확인된 ETF 정보와 다릅니다: '+', '.join(sorted(seen)))
    return code

# Keep the original parser constants separate from the web parser constants.
from types import SimpleNamespace as _Namespace
ingest = _Namespace(
    _parse_candidates=_parse_candidates, parse_upload=parse_upload,
    SYNONYMS=SYNONYMS, CODE_RE=CODE_RE, validate_holdings=validate_holdings,
    validate_identity=validate_identity,
)

"""Strict KRX/manager workbook parser; unresolved identifiers are never invented."""
from io import BytesIO,StringIO
from pathlib import Path
from datetime import datetime,date
from hashlib import sha256
import csv,re,zipfile
import pandas as pd

MAX_FILE=15*1024*1024
CATALOG_CODE={'종목코드','단축코드','ETF코드','ETF종목코드','단축종목코드','종목번호','종목코드(단축)'}
CATALOG_NAME={'종목명','한글종목명','ETF명','ETF상품명','상품명','한글 종목명','한글종목약명'}
INDEX_NAMES={'기초지수','기초지수명','추적지수','기초지수명칭'}
MANAGER_NAMES={'운용사','자산운용사','집합투자업자'}
CATEGORY_NAMES={'분류','상품유형','연구분류','ETF유형','유형'}
SHORT_NAMES={'한글종목약명','종목약명','ETF약명'}
def normal(x):return re.sub(r'\s|[-_\[\]{}():]', '',str(x)).lower()
CODE_RE=re.compile(r'(?<!\d)(\d{6})(?!\d)')
DATE_RE=re.compile(r'(?<!\d)(20\d{2})[-./년 ]?(0?[1-9]|1[0-2])[-./월 ]?(0?[1-9]|[12]\d|3[01])(?:일)?(?!\d)')

def inspect_magic(content,filename):
    ext=Path(filename).suffix.lower()
    if ext not in ('.csv','.xls','.xlsx'):raise ValueError('XLS/XLSX/CSV 파일만 올릴 수 있습니다.')
    if len(content)>MAX_FILE:raise ValueError('파일 크기는 15MB 이하여야 합니다.')
    if not content:raise ValueError('빈 파일입니다.')
    if ext=='.xlsx':
        if not content.startswith(b'PK\x03\x04'):raise ValueError('XLSX 확장자와 실제 파일 형식이 다릅니다.')
        try:
            with zipfile.ZipFile(BytesIO(content)) as z:
                if len(z.infolist())>1200 or sum(i.file_size for i in z.infolist())>75*1024*1024:
                    raise ValueError('압축 내부 크기 제한을 초과했습니다.')
                if '[Content_Types].xml' not in z.namelist():raise ValueError('정상적인 XLSX 형식이 아닙니다.')
                for info in z.infolist():
                    if info.file_size>40*1024*1024:raise ValueError('비정상적으로 큰 시트가 포함되어 있습니다.')
        except zipfile.BadZipFile as e:raise ValueError('손상된 XLSX 파일입니다.') from e
    elif ext=='.xls':
        lower=content.lstrip()[:128].lower()
        if not (content.startswith(bytes.fromhex('D0CF11E0A1B11AE1')) or lower.startswith((b'<html',b'<table',b'<!doctype')) or b'<table' in lower):
            raise ValueError('XLS 확장자와 실제 형식이 다릅니다.')
    elif b'\x00' in content[:200] and not content.startswith((b'\xff\xfe',b'\xfe\xff')):
        raise ValueError('CSV에 허용되지 않는 바이너리 문자가 있습니다.')
    if b'<!entity' in content[:1024].lower():raise ValueError('외부 엔티티 포함 파일은 처리하지 않습니다.')
    return ext

def sheets(content, filename):
    inspect_magic(content,filename)
    yield from ingest._parse_candidates(content,filename)

def _contains_holdings_sheet(content,filename):
    """Check whether a catalog workbook also contains a separate holdings table."""
    for _,raw in sheets(content,filename):
        if raw.empty:continue
        for _,row in raw.head(28).iterrows():
            found={LOOKUP[norm(v)] for v in row.astype(str) if norm(v) in LOOKUP}
            if 'weight_pct' in found and ('security_id' in found or 'security_name' in found):
                return True
    return False


def parse_catalog(content,filename):
    """Recognize a catalog independent of holdings. Preserve users' uploaded metadata provenance."""
    results=[];used_sheet=None;seen=set();seen_names={}
    code_heads={normal(s) for s in CATALOG_CODE};name_heads={normal(s) for s in CATALOG_NAME}
    for sheet,raw in sheets(content,filename):
        for i in range(min(len(raw),28)):
            cells=[normal(v) for v in raw.iloc[i].tolist()]
            codeidx=next((k for k,s in enumerate(cells) if s in code_heads),None)
            nameidx=next((k for k,s in enumerate(cells) if s in name_heads),None)
            weight_present=any(c in {normal(x) for x in ingest.SYNONYMS['weight_pct']} for c in cells)
            if codeidx is None or nameidx is None or weight_present:continue
            if len(raw)-i-1<1:continue
            mapping={head:next((k for k,s in enumerate(cells) if s in {normal(x) for x in names}),None) for head,names in [('index',INDEX_NAMES),('manager',MANAGER_NAMES),('category',CATEGORY_NAMES),('short_name',SHORT_NAMES)]}
            for _,row in raw.iloc[i+1:].iterrows():
                code=str(row.iloc[codeidx]).strip().removesuffix('.0').upper().zfill(6)
                name=str(row.iloc[nameidx]).strip()
                if not re.fullmatch('[0-9A-Z]{6,12}',code) or not name or name.lower() in ('nan','none'):continue
                if code in seen:
                    if normal(seen_names[code])!=normal(name):
                        raise ValueError(f'동일 ETF 코드 {code}에 서로 다른 상품명이 있습니다. 기본정보 충돌을 확인하세요.')
                    continue
                seen.add(code);seen_names[code]=name
                out={'code':code,'name':name,'index_name':'','manager':'','category':'','short_name':'','source_file':filename,'source_sheet':sheet}
                for field,index in mapping.items():
                    if index is not None:out['index_name' if field=='index' else field]=str(row.iloc[index]).strip()
                results.append(out)
            if results:used_sheet=sheet;break
        if results:break
    if not results:raise ValueError('ETF 코드 및 ETF 상품명 열을 포함한 기본정보 목록을 찾지 못했습니다.')
    return results,{'kind':'catalog','sheet':used_sheet,'count':len(results),'sha256':sha256(content).hexdigest()}

def date_value(s):
    if not s:return None
    if isinstance(s,(datetime,date)):return s.date().isoformat() if isinstance(s,datetime) else s.isoformat()
    text=str(s).strip()
    try:
        dt=pd.to_datetime(text,errors='raise')
        if 2000<=dt.year and dt.date()<=date.today():return dt.strftime('%Y-%m-%d')
    except Exception:pass
    m=DATE_RE.search(text)
    if not m:return None
    try:
        result=date(*(int(g) for g in m.groups()))
        if result<=date.today():return result.isoformat()
    except ValueError:pass
    return None

def _meta_from_preamble(raw):
    found={}
    keys={'etf_code':('etf코드','etf종목코드','etf단축코드','펀드코드','etf code'),
          'etf_name':('etf명','etf상품명','펀드명','etf name','상품명'),
          'as_of_date':('기준일','구성기준일','편입기준일','pcf기준일','자산구성기준일','as of date')}
    for _,row in raw.head(24).iterrows():
        vals=[str(x).strip() if pd.notna(x) else '' for x in row.tolist()]
        for i,cell in enumerate(vals):
            if not cell:continue
            # Only labeled metadata, never generic numeric cells.
            for k,labels in keys.items():
                matches=any(normal(cell).startswith(normal(l)) for l in labels)
                if not matches:continue
                val=''
                if ':' in cell:val=cell.split(':',1)[1].strip()
                elif '：' in cell:val=cell.split('：',1)[1].strip()
                if not val:
                    for nxt in vals[i+1:]:
                        if nxt and nxt.lower() not in ('nan','none'):val=nxt;break
                if k=='etf_code':
                    # Alphanumeric six-character short codes are valid on KRX.
                    m=re.search(r'(?<![A-Z0-9])([A-Z0-9]{6})(?![A-Z0-9])',val.upper())
                    if m and any(char.isdigit() for char in m.group(1)):
                        found[k]=m.group(1)
                elif k=='as_of_date':
                    v=date_value(val)
                    if v:found[k]=v
                elif val and val!=cell and len(val)<250:found[k]=val
    return found

def parse_holdings_auto(content,filename,catalog_lookup=None):
    """Automatic percent/fraction choice only when arithmetic is decisive (sum ~=100 or ~=1)."""
    inspect_magic(content,filename)
    try:df,meta=ingest.parse_upload(content,filename,'percent')
    except ValueError as e:
        if '비중' in str(e):
            # Catalog handling is attempted by caller; propagate intact.
            raise
        raise
    values=pd.to_numeric(df.weight_pct,errors='coerce')
    if meta['weight_basis']=='시가총액 기준 비중':
        raise ValueError('시가총액 기준 구성비중은 ETF 순자산 대비 편입비중으로 확인되지 않아 집중도 분석에 사용할 수 없습니다.')
    if values.isna().any():
        raise ValueError(f'구성종목 {len(df)}개 항목 중 유효한 편입비중 {int(values.notna().sum())}개: 빈칸·- 또는 숫자가 아닌 비중이 있습니다. 집중도는 계산하지 않습니다.')
    raw_total=float(values.sum())
    marks=[('%' in str(v) or '％' in str(v)) for v in df.weight_original]
    if any(marks) and not all(marks):
        # Mixed explicit and implicit percent: cannot automatically infer reliable units.
        raise ValueError('비중 숫자와 %표시가 혼재합니다. 단위 확인이 필요합니다.')
    if abs(raw_total-100)<=.05:unit='percent'
    elif abs(raw_total-1)<=.0005 and not any(marks):
        df['weight_pct']=values*100;unit='fraction'
    else:
        raise ValueError(f'비중 합계가 {raw_total:.6g}입니다. 100% 또는 1.0(소수표현)으로 확인되지 않아 등록하지 않았습니다.')
    check=ingest.validate_holdings(df)
    if not check['eligible']:raise ValueError('; '.join(check['issues']))
    # Header metadata, rows, then labeled preamble. Never infer an ETF from an unlabeled cell.
    extracted={}
    for col in ('etf_code','etf_name','as_of_date'):
        vals={str(x).strip() for x in df[col] if str(x).strip() not in ('','nan','None')}
        if len(vals)>1:raise ValueError('파일에 서로 다른 '+col+' 값이 존재합니다.')
        if vals:
            extracted[col]=next(iter(vals))
    for sheet,raw in sheets(content,filename):
        if sheet==meta['sheet']:
            pre=_meta_from_preamble(raw.iloc[:max(0,min(len(raw),meta['header_row']-1))]);
            for k,v in pre.items():
                if k in extracted:
                    current=str(extracted[k]).strip()
                    if k=='etf_code':
                        conflict=current.upper().zfill(6)!=str(v).upper().zfill(6)
                    elif k=='as_of_date':
                        current_date=date_value(current)
                        preamble_date=date_value(v)
                        conflict=not current_date or not preamble_date or current_date!=preamble_date
                    else:
                        conflict=normal(current)!=normal(v)
                    if conflict:raise ValueError(f'원본 표와 머리말의 {k} 값이 충돌합니다.')
                else:
                    extracted[k]=v
            break
    code=str(extracted.get('etf_code','')).strip().upper().removesuffix('.0')
    if code and code.isdigit():code=code.zfill(6)
    lookup=catalog_lookup or {}
    # A filename is user-controlled and does not authenticate a portfolio.
    # Even if the filename happens to contain a known ETF code, never
    # attribute its holdings without an explicit in-file identifier.
    if not code:
        raise ValueError('원본 파일 내부에 ETF 코드가 없습니다. 파일명에 적힌 코드는 ETF 연결의 근거로 사용하지 않습니다. ETF 코드가 명시된 원본을 올려 주세요.')
    if not ingest.CODE_RE.fullmatch(code):raise ValueError('ETF 코드 형식 오류: '+code)
    known=lookup.get(code)
    name=extracted.get('etf_name') or (known['name'] if known else '')
    if not name:raise ValueError('ETF 상품명이 확인되지 않습니다. ETF 상품명과 코드를 포함한 기본정보 파일을 먼저 올려 주세요.')
    if known and extracted.get('etf_name') and normal(known['name'])!=normal(name):
        raise ValueError('기존 기본정보의 ETF 상품명과 원본 ETF 상품명이 불일치합니다. 자동 등록하지 않았습니다.')
    as_of=extracted.get('as_of_date')
    if not as_of:raise ValueError('편입 기준일을 원본에서 확인할 수 없습니다. 다운로드 날짜·파일명 날짜를 기준일로 대체하지 않았습니다.')
    as_of=date_value(as_of)
    if not as_of:raise ValueError('편입 기준일이 유효하지 않거나 미래입니다.')
    # Re-verify the provided values across all rows, not just the summary.
    ingest.validate_identity(df,code,name,as_of)
    meta.update(kind='holdings',etf_code=code,etf_name=name,as_of_date=as_of,unit=unit,verification='원본 구조 검증 / 출처 독립검증 미완료',validation=check)
    return df,meta


# Stateless free-hosting workflow. Everything lives in the visitor's Streamlit session.
from collections import Counter
from io import BytesIO as _BytesIO
import math as _math

_STOP={'kodex','tiger','plus','ace','sol','rise','etf','한국','국내','미국','지수','상장'}

def _evidence_of_etf_list(content,filename):
    """Use the *header*, not stray quantity fields such as catalog CU수량.

    KRX listing has 단축코드 / 한글종목명 / 기초지수명 / CU수량;
    KRX holdings has 종목코드 / 구성종목명 / 주식수(계약수).
    """
    code_heads={normal(s) for s in CATALOG_CODE}
    name_heads={normal(s) for s in CATALOG_NAME}
    context_heads={normal(s) for s in INDEX_NAMES|MANAGER_NAMES}
    holding_heads={normal(s) for s in ('구성종목명','주식수(계약수)','보유수량','편입비중','시가총액 구성비중')}
    for _,raw in sheets(content,filename):
        for _,row in raw.head(28).iterrows():
            header={normal(x) for x in row.astype(str) if str(x).strip()}
            if header & code_heads and header & name_heads and header & context_heads and not header & holding_heads:
                return True
    return False



def identify_krx_reference(frame,meta,content,filename,catalog_lookup=None):
    """Find a *reference label* only from explicitly marked ETF metadata.

    A reference label is NOT a NAV holding snapshot, a verified KRX document,
    or evidence that the table contains the entire ETF portfolio.
    """
    extracted={}
    origins={}
    for field in ('etf_code','etf_name','as_of_date'):
        if field not in frame:
            continue
        values={str(x).strip() for x in frame[field]
                if str(x).strip().lower() not in ('','nan','none','-','—')}
        if len(values)>1:
            return None, f'원본에 상충하는 {field} 값이 있습니다.'
        if values:
            extracted[field]=next(iter(values))
            origins[field]='원본 표의 명시적 ETF 정보 열'
    for sheet,raw in sheets(content,filename):
        if sheet != meta['sheet']:
            continue
        top=raw.iloc[:max(0,meta['header_row']-1)]
        pre=_meta_from_preamble(top)
        for key,value in pre.items():
            if key in extracted and normal(extracted[key]) != normal(value):
                return None, f'원본 표와 머리말의 {key} 값이 다릅니다.'
            if key not in extracted:
                extracted[key]=str(value).strip()
                origins[key]='원본 머리말의 명시적 ETF 정보'
        break
    raw_code=extracted.get('etf_code','').strip().upper().removesuffix('.0')
    if not raw_code:
        return None,'원본 파일에서 ETF 코드를 확인하지 못했습니다.'
    code=raw_code.zfill(6) if raw_code.isdecimal() else raw_code
    if not ingest.CODE_RE.fullmatch(code):
        return None,'원본 ETF 코드의 형식이 올바르지 않습니다.'
    raw_name=extracted.get('etf_name','').strip()
    lookup=catalog_lookup or {}
    known=lookup.get(code)
    if known and raw_name and normal(raw_name)!=normal(known.get('name','')):
        return None,'원본 ETF 이름이 등록된 기본정보 목록과 충돌합니다.'
    name=raw_name or (known.get('name','') if known else '')
    if not name:
        return None,'원본의 ETF 코드에 대응하는 상품명을 확인하지 못했습니다.'
    raw_date=extracted.get('as_of_date','').strip()
    as_of=date_value(raw_date) if raw_date else None
    if raw_date and not as_of:
        return None,'원본에 기록된 구성 기준일을 검증할 수 없습니다.'
    return {'etf_code':code,'etf_name':name,'as_of_date':as_of,
            'status':'원본 내부 표기(외부 인증 전)',
            'evidence':origins.get('etf_code','원본 내 명시적 ETF 코드'),
            'verified':False},''


def manual_krx_reference(report,catalog,code):
    """Attach a user-declared *display reference*, never NAV holdings."""
    if report.get('identity') is not None:
        raise ValueError('원본 내부의 ETF 식별정보가 이미 있으므로 수동으로 덮어쓸 수 없습니다.')
    if '충돌' in report.get('identity_issue','') or '상충' in report.get('identity_issue',''):
        raise ValueError('원본 ETF 식별정보가 충돌합니다. 정확한 KRX 원본을 다시 확인하세요.')
    if not report.get('_standalone_stats',{}).get('available'):
        raise ValueError('비중이 검증된 KRX 단독 분석 자료만 참고 연결할 수 있습니다.')
    if report.get('weight_basis')!='시가총액 기준 비중':
        raise ValueError('KRX 시가총액 기준 구성비중 자료만 참고 연결할 수 있습니다.')
    code=str(code).strip().upper()
    if code not in catalog:
        raise ValueError('등록된 ETF 기본정보에 없는 코드입니다.')
    name=str(catalog[code].get('name','')).strip()
    if not name:
        raise ValueError('선택한 ETF의 상품명이 없습니다.')
    return {'etf_code':code,'etf_name':name,'as_of_date':None,
            'status':'사용자 지정 참고 표시(원본 미확인)',
            'evidence':'사용자가 별도 확인 후 목록에서 수동 선택; 원본 파일 자체에는 식별자가 없음',
            'verified':False}

def _partial_holdings(content,filename,catalog_lookup=None):
    """Extract only the verifiable fields of an *unattached* holdings table.

    Deliberately excludes ambiguous instrument/ETF identity; never stores these
    rows as a portfolio snapshot or converts a missing weight into zero.
    """
    frame,meta=ingest.parse_upload(content,filename,'percent')
    if frame.empty:
        return None
    reference,identity_issue=identify_krx_reference(frame,meta,content,filename,catalog_lookup)
    weights=pd.to_numeric(frame.weight_pct,errors='coerce')
    valid=int(weights.notna().sum())
    if valid and meta['weight_basis']!='시가총액 기준 비중':
        # Preserve the original guard for genuine ETF NAV-weighted data:
        # missing name/date/identity is still an actionable error, not a
        # silently accepted standalone instrument portfolio.
        return None
    # A complete numeric table can be analysed *without* attributing it to an
    # ETF. The original basis remains explicit (market cap != fund NAV).
    standalone=krx_component_concentration(frame) if valid==len(frame) else {'available':False,'reason':'일부 구성종목의 비중이 누락되었습니다.'}
    # Do not expose raw malformed user inputs via exception text; show safe preview.
    names=[]
    for row in frame.head(100).itertuples():
        names.append({'종목코드':str(row.security_id),'구성종목명':str(row.security_name),
                      '주식수(계약수)':str(row.quantity),
                      '원본비중':str(row.weight_original) if str(row.weight_original).strip() not in ('','-','—') else '미제공'})
    return {'rows':len(frame),'valid_weights':valid,'sample':names,
            'weight_basis':meta['weight_basis'],'sheet':meta['sheet'],
            'frame':frame if standalone['available'] else None,
            'standalone_stats':standalone,'identity':reference,'identity_issue':identity_issue}


def parse_bundle(uploaded, catalog=None, snapshots=None, seen_hashes=None):
    """Return independent new state; never mutate input on failed uploads.

    uploaded: iterable of (filename, bytes). Catalog-only uploads never manufacture holdings.
    """
    catalog={k:dict(v) for k,v in (catalog or {}).items()}
    snapshots=dict(snapshots or {})
    seen=set(seen_hashes or ())
    results=[];tasks=[];queued_hashes=set()
    uploaded=list(uploaded)
    if len(uploaded)>12:
        return catalog,snapshots,seen,[{'file':'전체 파일','status':'확인 필요','category':'추가 정보 필요','message':'한 번에 12개 이하로 업로드하세요.'}]
    for filename,content in uploaded:
        filename=Path(str(filename)).name[:160]
        try:
            if Path(filename).suffix.lower()=='.pdf':
                results.append({'file':filename,'status':'확인 필요','category':'지원하지 않는 형식',
                                'kind':'PDF','message':'PDF는 표/비중의 의미와 전체 편입 범위를 안전하게 검증할 수 없어 업로드를 지원하지 않습니다. KRX에서 Excel 또는 CSV를 내려받아 올려 주세요.'})
                continue
            inspect_magic(content,filename)
            digest=sha256(content).hexdigest()
            if digest in seen or digest in queued_hashes:
                results.append({'file':filename,'status':'중복','category':'중복 업로드','message':'같은 파일이 이미 이 브라우저 세션에서 처리되었습니다.'})
                continue
            if _evidence_of_etf_list(content,filename):
                try:
                    rows,meta=parse_catalog(content,filename)
                    changed=0;conflicts=0
                    for row in rows:
                        old=catalog.get(row['code'])
                        if old and normal(old['name'])!=normal(row['name']):
                            conflicts+=1
                        elif not old:
                            catalog[row['code']]=row;changed+=1
                    seen.add(digest)
                    results.append({'file':filename,'status':'성공','category':'정상 등록' if conflicts==0 else '일부 정보만 등록',
                                    'kind':'ETF 기본정보','etf_count':len(rows),'new_count':changed,'holding_count':0,'weight_available':False,'analysis_available':False,
                                    'message':f'ETF 기본정보 {len(rows)}개 인식 · 신규 {changed}개 · 이름 충돌 {conflicts}개. 구성종목과 집중도는 별도로 확인해야 합니다.'})
                    if not _contains_holdings_sheet(content,filename):
                        continue
                    # A single workbook may have catalog + one holdings sheet.
                    # Preserve the catalog result and additionally analyze holdings;
                    # do not conflate them or drop the second sheet silently.
                except ValueError as e:
                    results.append({'file':filename,'status':'확인 필요','category':'기본정보 검증 실패',
                                    'kind':'ETF 기본정보','message':str(e)[:320]})
                    continue
            tasks.append((filename,content,digest))
            queued_hashes.add(digest)
        except (ValueError,UnicodeError) as e:
            category='지원하지 않는 형식' if 'XLS/XLSX/CSV 파일만' in str(e) else '잘못된 파일'
            results.append({'file':filename,'status':'확인 필요','category':category,'message':str(e)[:320]})
        except Exception:
            # Isolate unexpected parser failures to the affected upload.
            results.append({'file':filename,'status':'오류','category':'잘못된 파일',
                            'message':'파일 형식 판별 중 내부 오류가 발생했습니다. 다른 파일은 계속 처리합니다.'})
    for filename,content,digest in tasks:
        try:
            frame,meta=parse_holdings_auto(content,filename,catalog)
            code=meta['etf_code']; name=meta['etf_name']
            if code not in catalog:catalog[code]={'code':code,'name':name,'index_name':'','manager':'','category':''}
            old=snapshots.get(code)
            snapshot={'frame':frame,'meta':meta,'filename':filename,'sha256':digest}
            if old and old['meta']['as_of_date']==meta['as_of_date'] and old['sha256']!=digest:
                results.append({'file':filename,'status':'확인 필요','category':'추가 정보 필요','kind':'구성종목',
                                'message':f'{code}에 동일 기준일·서로 다른 데이터가 이미 있습니다. 기존 검증자료를 보호하기 위해 덮어쓰지 않았습니다. 새 분석 세션에서 확인해 주세요.'})
            elif old and old['meta']['as_of_date']>meta['as_of_date']:
                results.append({'file':filename,'status':'보류','category':'일부 정보만 등록','kind':'구성종목',
                                'message':f'기존 {code}의 {old["meta"]["as_of_date"]} 스냅샷이 더 최신입니다. 과거 자료는 현재 비교에서 제외합니다.'})
            else:
                snapshots[code]=snapshot
                stats=concentration(frame)
                results.append({'file':filename,'status':'성공','category':'정상 등록' if stats['available'] else '일부 정보만 등록','kind':'구성종목','holding_count':len(frame),
                                'etf_count':1,'weight_available':True,'analysis_available':stats['available'],
                                'message':f'{name} ({code}), {meta["as_of_date"]} 기준, {len(frame)}개 구성항목, 비중 {float(frame.weight_pct.sum()):.4f}% 자동 인식'})
            seen.add(digest)
        except (ValueError,UnicodeError) as e:
            try:
                part=_partial_holdings(content,filename,catalog)
            except (ValueError,UnicodeError):
                part=None
            if part is not None:
                can_analyze=part['standalone_stats']['available']
                if can_analyze:
                    message=(f'구성종목 {part["rows"]}개 · 유효 비중 {part["valid_weights"]}개 · '
                             f'원본 합계 {part["standalone_stats"]["raw_total_pct"]:.2f}%를 확인했습니다. '
                             f'{part["weight_basis"]}에 한해 집중도·HHI를 계산합니다. '
                             'ETF 순자산 편입자료로 연결하거나 ETF 간 NAV 유사도를 계산하지 않습니다.')
                else:
                    message=(f'구성종목 {part["rows"]}개 항목을 확인했지만 단독 집중도 분석은 불가능합니다: '
                             f'{part["standalone_stats"]["reason"]} '
                             '원본 ETF 식별정보는 별도로 확인해야 하며, 특정 ETF의 편입비중으로 연결하지 않습니다.')
                results.append({'file':filename,'status':'성공' if can_analyze else '확인 필요',
                                'category':'일부 정보만 등록' if can_analyze else '추가 정보 필요',
                                'kind':'구성비중 단독 분석(ETF 미연결)' if can_analyze else '미연결 구성종목',
                                'holding_count':part['rows'],'etf_count':0,'valid_weights':part['valid_weights'],
                                 'weight_available':part['valid_weights']==part['rows'],'analysis_available':can_analyze,
                                 'preview':part['sample'], 'source_sha256':digest,
                                 '_standalone_frame':part['frame'], '_standalone_stats':part['standalone_stats'],
                                 'weight_basis':part['weight_basis'],'identity':part['identity'],
                                 'identity_issue':part['identity_issue'],'message':message})
                seen.add(digest)
            else:
                results.append({'file':filename,'status':'확인 필요','category':'추가 정보 필요',
                                'message':str(e)[:320]})
        except Exception:

            results.append({'file':filename,'status':'오류','category':'잘못된 파일','message':'파일 읽기 중 내부 오류가 발생했습니다. 다른 원본 형식으로 다시 저장해 주세요.'})
    order={Path(str(name)).name[:160]:i for i,(name,_) in enumerate(uploaded)}
    results.sort(key=lambda item:order.get(item['file'],len(uploaded)))
    return catalog,snapshots,seen,results

def concentration(frame):
    """Same investment-weight calculation and thresholds as original core.analysis."""
    if frame is None or frame.empty:return {'available':False,'reason':'편입자료 없음'}
    w=pd.to_numeric(frame.weight_pct,errors='coerce')
    if w.isna().any() or (w<0).any() or (~w.map(_math.isfinite)).any():return {'available':False,'reason':'비중 누락·음수·비정상 값: 분석하지 않습니다.'}
    total=float(w.sum())
    if abs(total-100)>0.05:return {'available':False,'reason':'원본 비중 합계 검증 실패'}
    keys=frame.security_id.astype(str)
    if (frame.assign(_code=keys).groupby('_code')['asset_type'].nunique(dropna=False)>1).any():
        return {'available':False,'reason':'동일 종목코드에 서로 다른 자산유형이 있어 집중도를 계산할 수 없습니다.'}
    if keys.str.startswith('UNKNOWN_').any():return {'available':False,'reason':'편입종목 코드가 일부 없어 종목별 HHI를 검증할 수 없습니다.'}
    names=frame.security_name.fillna('').astype(str).str.strip()
    if (pd.DataFrame({'id':keys,'name':names}).groupby('id')['name'].nunique()>1).any():
        return {'available':False,'reason':'동일 종목코드에 서로 다른 종목명이 있어 종목별 집중도를 계산할 수 없습니다.'}
    normalized=w*100/total
    kinds=frame.asset_type.astype(str)
    if kinds.eq('미확인').any():
        grouped=pd.DataFrame({'id':keys,'w':normalized}).groupby('id').w.sum()
        hhi=float((grouped**2).sum())
        return {'available':False,'reason':'일부 구성자산의 주식/현금 등 자산유형이 확인되지 않아 주식 집중도를 산출할 수 없습니다. 구성자산 기준 HHI만 표시합니다.',
                'raw_total_pct':total,'hhi':hhi,'effective_n':10000/hhi if hhi else None}

    grouped=pd.DataFrame({'id':keys,'w':normalized}).groupby('id').w.sum()
    hhi=float((grouped**2).sum())
    stocks=frame.asset_type.astype(str).eq('주식')
    stock=pd.DataFrame({'id':keys[stocks],'w':normalized[stocks]}).groupby('id').w.sum().sort_values(ascending=False)
    response={'available':bool(len(stock)),'raw_total_pct':total,'hhi':hhi,'effective_n':10000/hhi if hhi else None,
              'stock_classification_pct':float(normalized[stocks].sum()),'unknown_id_count':int(keys.str.startswith('UNKNOWN_').sum())}
    if stock.empty:
        return {**response,'reason':'종목의 자산유형이 주식인지 확인되지 않아 상위 종목 집중도는 계산하지 않습니다.'}
    top1=float(stock.head(1).sum());top3=float(stock.head(3).sum());top5=float(stock.head(5).sum())
    grade='고집중' if top1>=20 or top5>=70 else ('집중' if top3>=40 else '분산')
    if top1>=20:grade_reason=f'상위 단일 주식 비중 {top1:.2f}%가 20% 이상입니다.'
    elif top5>=70:grade_reason=f'상위 5개 주식 비중 {top5:.2f}%가 70% 이상입니다.'
    elif top3>=40:grade_reason=f'상위 3개 주식 비중 {top3:.2f}%가 40% 이상입니다.'
    else:grade_reason='단일·상위 3개·상위 5개 주식의 집중 기준치를 모두 밑돌았습니다.'
    return {**response,'top1_pct':top1,'top3_pct':top3,'top5_pct':top5,'grade':grade,'grade_reason':grade_reason,'reason':''}


def krx_component_concentration(frame):
    """Standalone, basis-labelled KRX composition concentration.

    No ETF identity, NAV weighting, official holdings date, or asset type is
    inferred from a security name. Only *explicit* cash rows are excluded from
    the top-N instrument calculation; HHI includes those cash rows. A sum near
    100% validates the displayed table's arithmetic, NOT its completeness as
    an ETF portfolio.
    """
    fail=lambda reason:{'available':False,'reason':reason}
    if frame is None or frame.empty:return fail('구성종목이 없습니다.')
    required={'security_id','security_name','weight_pct'}
    if not required.issubset(frame):return fail('종목코드·종목명·비중 열이 필요합니다.')
    ids=frame.security_id.astype(str).str.strip()
    if ids.eq('').any() or ids.str.startswith('UNKNOWN_').any():
        return fail('일부 구성종목 코드가 없어 중복종목 여부를 판정할 수 없습니다.')
    if (pd.DataFrame({'id':ids,'name':frame.security_name.fillna('').astype(str).str.strip()})
          .groupby('id')['name'].nunique()>1).any():
        return fail('동일 종목코드에 서로 다른 종목명이 있어 구성비중을 합산할 수 없습니다.')
    w=pd.to_numeric(frame.weight_pct,errors='coerce')
    if w.isna().any():return fail('비중이 비어 있거나 숫자가 아닌 행이 있습니다.')
    if (~w.map(_math.isfinite)).any() or (w<0).any() or (w>100.05).any():
        return fail('비중에 음수·무한대 또는 100% 초과 값이 있습니다.')
    total=float(w.sum())
    if abs(total-100)>0.05:
        return fail(f'원본 비중 합계 {total:.4f}%가 100%±0.05%p를 벗어납니다. 부분자료일 수 있어 계산하지 않습니다.')
    if total<=0:return fail('비중 합계가 0%입니다.')
    names=frame.security_name.astype(str).str.replace(' ','',regex=False).str.lower()
    cash_names={'원화현금','외화현금','설정현금액','현금','예수금','cash','krwcash','usdcash'}
    is_cash=names.isin(cash_names) | frame.get('asset_type',pd.Series(['']*len(frame))).astype(str).eq('현금')
    normal=w*100/total
    # Include cash in all-component HHI, but not top-N "instrument" weights.
    by_code=pd.DataFrame({'security_id':ids,'w':normal}).groupby('security_id')['w'].sum()
    if (pd.DataFrame({'id':ids,'cash':is_cash}).groupby('id')['cash'].nunique()>1).any():
        return fail('동일 종목코드가 현금과 일반종목에 동시에 사용되었습니다.')
    hhi=float((by_code**2).sum())
    instruments=pd.DataFrame({'security_id':ids[~is_cash],'w':normal[~is_cash]}).groupby('security_id')['w'].sum().sort_values(ascending=False)
    if instruments.empty:return fail('비현금 구성종목이 없습니다.')
    top1=float(instruments.head(1).sum())
    top3=float(instruments.head(3).sum())
    top5=float(instruments.head(5).sum())
    grade='고집중' if top1>=20 or top5>=70 else ('집중' if top3>=40 else '분산')
    if top1>=20:grade_reason=f'상위 단일 구성종목 비중 {top1:.2f}%가 20% 이상입니다.'
    elif top5>=70:grade_reason=f'상위 5개 구성종목 비중 {top5:.2f}%가 70% 이상입니다.'
    elif top3>=40:grade_reason=f'상위 3개 구성종목 비중 {top3:.2f}%가 40% 이상입니다.'
    else:grade_reason='단일·상위 3개·상위 5개 구성종목의 집중 기준치를 모두 밑돌았습니다.'
    return {'available':True,'reason':'','grade':grade,'grade_reason':grade_reason,'top1_pct':top1,'top3_pct':top3,'top5_pct':top5,
            'hhi':hhi,'effective_n':10000/hhi if hhi else None,'raw_total_pct':total,
            'cash_rows':int(is_cash.sum()),'instrument_rows':int((~is_cash).sum()),
            'calculation':'원본 비중 합계를 100%로 정규화. 상위 종목 비중은 명시적 현금 항목 제외, HHI는 현금 포함.',
            'limitation':'시가총액 기준 비중은 ETF 순자산 편입비중이 아닙니다. 원본에 ETF 코드·구성 기준일이 없다면 특정 ETF 수치로 표시하지 않습니다.'}

def candidate_etfs(code,catalog,snapshots,limit=5):
    if code not in catalog:return []
    def words(s):
        txt=str(s).lower()
        for noise in ('증권상장지수투자신탁','주식-파생형','상장지수투자신탁','증권투자신탁','미래에셋','삼성자산운용'):
            txt=txt.replace(noise,' ')
        return set(re.findall('[가-힣]{2,}|[a-z]{2,}|[0-9]{2,}',txt))-_STOP
    a=catalog[code]
    terms=words((a.get('short_name') or a['name'])+' '+a.get('index_name',''))
    candidates=[]
    for other,row in catalog.items():
        if other==code:continue
        same=bool(a.get('category') and a.get('category')==row.get('category'))
        common=terms & words((row.get('short_name') or row['name'])+' '+row.get('index_name',''))
        if not same and not common:continue
        candidates.append({'코드':other,'ETF 이름':row.get('short_name') or row['name'],
                           '후보 근거':('동일 연구 분류' if same else '상품명·지수 공통 단어')+(': '+', '.join(sorted(common)[:4]) if common else ''),
                           '자료 상태':'편입자료 있음 · 정량 분석 별도' if other in snapshots else '자료 확보용 비교 후보',
                           '_rank':(int(same),len(common),int(other in snapshots))})
    return [{k:v for k,v in row.items() if k!='_rank'} for row in sorted(candidates,key=lambda x:x['_rank'],reverse=True)[:limit]]

def comparison(a,b):
    """Partial comparison does not fabricate an overall score."""
    da=a['frame'];db=b['frame']
    ca=concentration(da);cb=concentration(db)
    if not ca['available'] or not cb['available']:
        return {'overall':None,'overlap_pct':None,'top5_gap_pct':None,'common':[],'only_a':[],'only_b':[],
                'reason':'두 ETF의 완전하고 유효한 편입비중을 확인할 수 없어 공통 종목과 유사도를 판정하지 않습니다.'}
    ids_a=set(da.security_id.astype(str));ids_b=set(db.security_id.astype(str))
    named={str(r.security_id):str(r.security_name) for df in (da,db) for r in df.itertuples()}
    known=not any(v.startswith('UNKNOWN_') for v in ids_a|ids_b)
    overlap=None
    if known:
        wa=da.groupby('security_id').weight_pct.sum()*100/float(da.weight_pct.sum())
        wb=db.groupby('security_id').weight_pct.sum()*100/float(db.weight_pct.sum())
        overlap=round(sum(min(float(wa[k]),float(wb[k])) for k in ids_a&ids_b),4)
    top_difference=round(abs(ca['top5_pct']-cb['top5_pct']),4) if ca['available'] and cb['available'] else None
    return {'overall':None,'overlap_pct':overlap,'top5_gap_pct':top_difference,
            'common':[named[x] for x in sorted(ids_a&ids_b)],
            'only_a':[named[x] for x in sorted(ids_a-ids_b)],
            'only_b':[named[x] for x in sorted(ids_b-ids_a)],
            'reason':'세부 산업·국가·기업집단 공식 검증 데이터가 없으므로 5요소 종합 유사도 점수는 계산하지 않습니다.'}

def excel_report(code,catalog,snapshots):
    if code not in snapshots:raise ValueError('실제 편입자료가 없습니다.')
    snap=snapshots[code];frame=snap['frame'];meta=snap['meta'];stats=concentration(frame)
    fields=[('ETF 코드',code),('ETF 이름',catalog[code]['name']),('원본 파일',snap['filename']),
            ('편입 기준일',meta['as_of_date']),('원본 SHA256',snap['sha256']),
            ('출처 검증','업로드 구조 검증 / 원출처 독립 검증되지 않음'),
            ('비중 기준',meta.get('weight_basis','미확인')),('비중 단위',meta.get('unit','미확인')),
            ('데이터 상태','완전한 투자구조가 공식 검증된 것은 아님'),
            ('산업 분류','자료 미확인'),('국가 분류','자료 미확인'),('기업집단 분류','자료 미확인'),
            ('총 비중 (%)',stats.get('raw_total_pct')),
            ('상위1 (%)',stats.get('top1_pct')),('상위3 (%)',stats.get('top3_pct')),
            ('상위5 (%)',stats.get('top5_pct')),('HHI(전체 구성자산)',stats.get('hhi')),
            ('유효구성항목 수',stats.get('effective_n')),('종목집중도',stats.get('grade','산출 불가')),
            ('집중도 판정 근거',stats.get('grade_reason','미산출')),
            ('집중도 검증 사유',stats.get('reason') or '비중 검증 통과 / 산업·국가 검증 없음')]
    # Uploaded ETF names are untrusted spreadsheet strings, including summary values.
    fields=[(k,("'"+v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in fields]
    buf=_BytesIO()
    with pd.ExcelWriter(buf,engine='xlsxwriter',engine_kwargs={'options':{'strings_to_formulas':False,'strings_to_urls':False}}) as writer:
        pd.DataFrame(fields,columns=['항목','결과']).to_excel(writer,index=False,sheet_name='요약')
        display=frame[['security_id','security_name','asset_type','weight_pct','weight_original','quantity','source_sheet','source_row']].copy()
        display.columns=['편입종목코드','편입종목명','자산유형','비중(%)','원본비중표시','수량','원본시트','원본행']
        # Treat uploaded strings as literal values (prevent spreadsheet formula execution).
        for col in display.select_dtypes(include=['object','string']).columns:
            display[col]=display[col].map(lambda x:("'"+x) if isinstance(x,str) and x.startswith(('=','+','-','@')) else x)
        display.to_excel(writer,index=False,sheet_name='편입종목')
        writer.sheets['요약'].set_column(0,0,27);writer.sheets['요약'].set_column(1,1,55)
        writer.sheets['편입종목'].freeze_panes(1,0)
    return buf.getvalue()


def excel_report_unlinked_krx(outcome):
    """Safe export for standalone KRX composition, without invented ETF IDs."""
    frame=outcome.get('_standalone_frame')
    stats=outcome.get('_standalone_stats') or {}
    if frame is None or not stats.get('available'):
        raise ValueError('단독 분석 가능한 구성비중 자료가 없습니다.')
    reference=outcome.get('reference_identity') or outcome.get('identity') or {}
    fields=[('자료 구분','KRX 시가총액 구성비중 별도 분석 / ETF NAV 편입비중 아님'),
            ('원본 파일명',outcome['file']),('원본 SHA256',outcome.get('source_sha256','')),
            ('참고 ETF 코드',reference.get('etf_code') or '원본에서 미확인'),
            ('참고 ETF 이름',reference.get('etf_name') or '원본에서 미확인'),
            ('참고 정보의 출처',reference.get('status') or 'ETF 미연결'),
            ('참고 연결 근거',reference.get('evidence') or '원본에 식별자 없음'),
            ('구성 기준일',reference.get('as_of_date') or '원본에서 미확인'),
            ('참고 연결 한계','ETF 이름을 표시하더라도 시가총액 기준 구성비중을 ETF 순자산 편입비중으로 사용하지 않음'),
            ('비중 기준',outcome['weight_basis']),('비중 합계(원본, %)',stats['raw_total_pct']),
            ('상위1 (%, 정규화)',stats['top1_pct']),('상위3 (%, 정규화)',stats['top3_pct']),
            ('상위5 (%, 정규화)',stats['top5_pct']),('종목 집중도',stats['grade']),
            ('집중도 판정 근거',stats['grade_reason']),
            ('HHI (현금 포함, 정규화)',stats['hhi']),('유효 구성항목 수',stats['effective_n']),
            ('집계 원칙',stats['calculation']),('해석상 제한',stats['limitation']),
            ('검증 범위','업로드 데이터의 구조·비중 합계 검사. 출처·ETF 동일성 독립 검증 없음')]
    for index,ev in enumerate((outcome.get('evidence_candidates') or [])[:5],start=1):
        fields.extend([
            (f'PDF 교차대조 후보 {index}',f'{ev["etf_name"]} ({ev["etf_code"]})'),
            (f'교차대조 확인 종목 {index}',f'{ev["matched_rows"]}개 / 비중 합계 {ev["matched_weight_pct"]:.2f}%'),
            (f'교차대조 근거 문서 {index}',ev['reference_source']),
            (f'교차대조 원문 SHA256 {index}',ev['reference_sha256']),
            (f'교차대조 한계 {index}',ev['verification_status']+' / '+ev['warning']),
        ])
    safe=lambda v: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v
    fields=[(k,safe(v)) for k,v in fields]
    data=frame[['security_id','security_name','weight_pct','weight_original','quantity','source_sheet','source_row']].copy()
    data.columns=['구성종목코드','구성종목명','비중(%)','원본비중표시','수량','원본시트','원본행']
    for col in data.select_dtypes(include=['object','string']).columns:
        data[col]=data[col].map(safe)
    buf=_BytesIO()
    with pd.ExcelWriter(buf,engine='xlsxwriter',engine_kwargs={'options':{'strings_to_formulas':False,'strings_to_urls':False}}) as writer:
        pd.DataFrame(fields,columns=['항목','결과']).to_excel(writer,index=False,sheet_name='분석요약')
        data.to_excel(writer,index=False,sheet_name='원본구성비중')
        writer.sheets['분석요약'].set_column(0,0,28)
        writer.sheets['분석요약'].set_column(1,1,72)
        writer.sheets['원본구성비중'].set_column(0,0,19)
        writer.sheets['원본구성비중'].set_column(1,1,28)
        writer.sheets['원본구성비중'].freeze_panes(1,0)
    return buf.getvalue()
