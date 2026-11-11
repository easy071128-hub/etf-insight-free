"""Build a versioned, reviewable ETF catalog for bundling in Streamlit.

Usage:
 python scripts/build_etf_catalog.py path/to/KRX_ETF_all.xlsx --as-of 2026-11-11 --rights-reviewed

Do not commit KRX-derived datasets into a public repository until the relevant
data redistribution conditions have been reviewed.
"""
import argparse
import csv
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from etf_engine import parse_catalog


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("input",type=Path)
    parser.add_argument("--as-of",required=True,help="Source market reference date YYYY-MM-DD")
    parser.add_argument("--source-url",default="https://data.krx.co.kr/")
    parser.add_argument("--output-dir",type=Path,default=Path("data"))
    parser.add_argument("--rights-reviewed",action="store_true",
                        help="Confirm that you checked KRX reuse/redistribution conditions")
    args=parser.parse_args()
    if not args.rights_reviewed:
        parser.error("Check applicable KRX licensing and pass --rights-reviewed before publishing.")
    try:
        as_of=date.fromisoformat(args.as_of)
    except ValueError:
        parser.error("--as-of requires YYYY-MM-DD")
    if as_of>date.today():
        parser.error("The source date cannot be in the future")
    if not args.source_url.startswith("https://"):
        parser.error("--source-url must use https")
    source=args.input.read_bytes()
    if len(source)>15_000_000:
        parser.error("Input exceeds 15MB")
    rows,_=parse_catalog(source,args.input.name)
    if not rows:
        parser.error("No valid ETF rows in original")
    root=args.output_dir
    root.mkdir(parents=True,exist_ok=True)
    target=root/"etf_catalog.csv"
    import io
    output=io.StringIO()
    writer=csv.writer(output,lineterminator="\n")
    writer.writerow(["단축코드","한글종목명","기초지수명","운용사","시장구분","단축명"])
    for row in sorted(rows,key=lambda x:x["code"]):
        writer.writerow([row["code"],row["name"],row["index_name"],
                         row["manager"],row["category"],row["short_name"]])
    data=output.getvalue().encode("utf-8-sig")
    target.write_bytes(data)
    manifest={
        "source_url":args.source_url,
        "as_of_date":as_of.isoformat(),
        "count":len(rows),
        "sha256":sha256(data).hexdigest(),
        "original_file_name":args.input.name,
        "original_sha256":sha256(source).hexdigest(),
        "data_basis":"KRX ETF 전종목 기본정보",
        "notes":"Snapshot of ETF metadata only; NAV composition and company classification are not included.",
    }
    (root/"etf_catalog_meta.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Created verified bundle: {len(rows)} ETF rows, as of {as_of}, SHA256 {manifest['sha256']}")
    print("Publication conditions must be reviewed separately; --rights-reviewed is an operator acknowledgment.")


if __name__=="__main__":
    main()
