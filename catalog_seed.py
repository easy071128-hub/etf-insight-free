"""Load a validated ETF master catalog bundled with the public app.

This file never downloads data or claims that a KRX dataset may be republished.
KRX licensing and the snapshot's accuracy must be checked separately.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from pathlib import Path

from etf_engine import parse_catalog


def load_bundled_catalog(data_dir=None):
    root=Path(data_dir) if data_dir is not None else Path(__file__).resolve().parent/"data"
    file=root/"etf_catalog.csv"
    manifest=root/"etf_catalog_meta.json"
    if not file.exists() and not manifest.exists():
        return {},None
    if not file.is_file() or not manifest.is_file():
        return {},{"error":"기본 ETF 목록과 출처 기록 중 하나가 없습니다."}
    if file.stat().st_size>5_000_000:
        return {},{"error":"기본 ETF 목록 파일이 5MB를 초과합니다."}
    try:
        info=json.loads(manifest.read_text(encoding="utf-8"))
        raw=file.read_bytes()
        digest=sha256(raw).hexdigest()
        if digest!=info.get("sha256"):
            raise ValueError("기본 ETF 목록 파일의 SHA256이 기록과 다릅니다.")
        if not info.get("source_url") or not str(info["source_url"]).startswith("https://"):
            raise ValueError("기본 ETF 목록의 공식 자료 출처가 유효하지 않습니다.")
        as_of=date.fromisoformat(str(info["as_of_date"]))
        if as_of>date.today():
            raise ValueError("기본 ETF 목록의 기준일이 미래입니다.")
        entries,_=parse_catalog(raw,file.name)
        if len(entries)!=info.get("count"):
            raise ValueError("기본 ETF 목록의 종목 수가 출처 기록과 다릅니다.")
        if len(entries)!=len({row["code"] for row in entries}):
            raise ValueError("기본 ETF 목록에 종목코드 중복이 있습니다.")
        if not entries:
            raise ValueError("기본 ETF 목록이 비어 있습니다.")
        catalog={entry["code"]:entry for entry in entries}
        provenance={
            "as_of_date":as_of.isoformat(),"source_url":info["source_url"],
            "count":len(catalog),"sha256":digest,"mode":"번들된 자료 스냅샷",
            "license_notice":"공개 재사용·재배포 허용 범위는 데이터 제공자의 이용조건을 별도로 확인해야 합니다.",
        }
        return catalog,provenance
    except (ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
        return {},{"error":"기본 ETF 목록 검증 실패: "+str(exc)[:180]}
