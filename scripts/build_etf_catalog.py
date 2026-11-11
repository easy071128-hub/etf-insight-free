"""Prepare a provenance-labelled KRX ETF master bundle.

Private-only by default. A public Streamlit catalog requires separately
documented KRX redistribution permission, not just a downloaded spreadsheet.

Private example:
 python scripts/build_etf_catalog.py KRX.xlsx --observed-on 2026-11-11
Public *only with written permission*:
 python scripts/build_etf_catalog.py KRX.xlsx --observed-on 2026-11-11 \
   --output-dir data --authorize-publication \
   --permission-reference 'KRX permission letter / agreement reference'
"""
import argparse
import csv
from datetime import date
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from etf_engine import norm,parse_catalog,sheets


def normalize_code(raw):
    code=str(raw).strip().upper().removesuffix(".0")
    return code.zfill(6) if code.isdecimal() else code


def extract_original_columns(content,filename,catalog):
    """Preserve all original KRX columns rather than dropping key asset fields."""
    possible=[]
    for sheet,raw in sheets(content,filename):
        for row_index in range(min(28,len(raw))):
            headers=[str(v).strip() for v in raw.iloc[row_index].tolist()]
            normalized=[norm(v) for v in headers]
            if not {"단축코드","한글종목명","기초지수명"}.issubset(normalized):
                continue
            idx=normalized.index("단축코드")
            entries=[]
            for values in raw.iloc[row_index+1:].itertuples(index=False,name=None):
                code=normalize_code(values[idx])
                if code not in catalog:continue
                row=["" if v is None or str(v).lower()=="nan" else str(v).strip()
                     for v in values]
                row[idx]=code
                entries.append(row)
            if len(entries)==len(catalog):
                possible.append((headers,entries))
    if len(possible)!=1:
        raise ValueError("정확히 하나의 ETF 전종목 목록 시트에서 전체 종목을 확인해야 합니다.")
    headers,entries=possible[0]
    if len(set(row[headers.index("단축코드")] for row in entries))!=len(catalog):
        raise ValueError("ETF 코드 중복이 있습니다.")
    return headers,entries


def prepare(input_file,output_dir,observed_on,source_url,
            permission_reference=None,authorize_publication=False):
    if observed_on>date.today():
        raise ValueError("기록한 파일 다운로드일이 미래입니다.")
    if not str(source_url).startswith("https://"):
        raise ValueError("공식 자료 출처는 HTTPS URL이어야 합니다.")
    if authorize_publication and not str(permission_reference or "").strip():
        raise ValueError("공개 배포에는 구체적인 KRX 재배포 허가 문서/계약 참조가 필요합니다.")
    source=input_file.read_bytes()
    if len(source)>15_000_000:
        raise ValueError("원본 파일 크기가 15MB를 초과합니다.")
    catalog_rows,_=parse_catalog(source,input_file.name)
    catalog={entry["code"]:entry for entry in catalog_rows}
    headers,records=extract_original_columns(source,input_file.name,catalog)
    if not records or len(records)!=len(catalog):
        raise ValueError("원본 ETF 종목 수를 검증하지 못했습니다.")
    output=io.StringIO(newline="")
    writer=csv.writer(output,lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(records)
    data=output.getvalue().encode("utf-8-sig")
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    (out/"etf_catalog.csv").write_bytes(data)
    meta={
        "source_url":source_url,
        "as_of_date":observed_on.isoformat(),
        "date_status":"기록된 파일 다운로드/수집일, 공식 시장 기준일은 독립 검증되지 않음",
        "count":len(records),
        "sha256":sha256(data).hexdigest(),
        "original_file_name":input_file.name,
        "original_sha256":sha256(source).hexdigest(),
        "original_columns":headers,
        "data_basis":"KRX ETF 전종목 기본정보, 원본 열 보존",
        "distribution_status":("authorized_for_public_redistribution" if authorize_publication
                               else "private_only_pending_krx_redistribution_permission"),
        "permission_reference":permission_reference if authorize_publication else None,
        "warning":"KRX 홈페이지 이용약관 제12조의 공개 재배포 조건을 준수해야 합니다.",
    }
    (out/"etf_catalog_meta.json").write_text(
        json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return meta


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("input",type=Path)
    parser.add_argument("--observed-on",required=True,
                        help="File collection date in YYYY-MM-DD, not assumed official market date")
    parser.add_argument("--source-url",default="https://data.krx.co.kr/")
    parser.add_argument("--output-dir",type=Path,default=Path("private_data"))
    parser.add_argument("--authorize-publication",action="store_true",
                        help="Only after written permission to redistribute KRX master data")
    parser.add_argument("--permission-reference",default=None,
                        help="Written redistribution permission identifier, not a placeholder")
    args=parser.parse_args()
    try:
        observed_on=date.fromisoformat(args.observed_on)
        meta=prepare(args.input,args.output_dir,observed_on,args.source_url,
                     args.permission_reference,args.authorize_publication)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Validated {meta['count']} ETFs; CSV SHA256={meta['sha256']}")
    print(f"Distribution: {meta['distribution_status']}")
    if not args.authorize_publication:
        print("PRIVATE-ONLY: Do not commit the generated CSV to a public repository.")


if __name__=="__main__":
    main()
