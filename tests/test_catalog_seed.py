"""Bundled KRX ETF metadata must be source-checked, not mistaken for holdings."""
from hashlib import sha256
import json
from datetime import date
from pathlib import Path

import pytest
from catalog_seed import load_bundled_catalog
from etf_engine import parse_catalog


def _make_catalog(folder, *,bad_count=False,bad_hash=False,future=False):
    folder.mkdir(parents=True,exist_ok=True)
    content=("단축코드,한글종목명,기초지수명,운용사\n"
             "091230,TIGER 반도체,KRX 반도체,미래에셋자산운용\n"
             "487230,KODEX 반도체,KRX 반도체,삼성자산운용\n").encode("utf-8-sig")
    (folder/"etf_catalog.csv").write_bytes(content)
    obj={"sha256":("a"*64 if bad_hash else sha256(content).hexdigest()),
         "count":3 if bad_count else 2,
         "as_of_date":"2099-12-31" if future else "2026-11-11",
         "source_url":"https://data.krx.co.kr/",
         "distribution_status":"authorized_for_public_redistribution",
         "permission_reference":"synthetic test fixture; not a real KRX authorization"}
    (folder/"etf_catalog_meta.json").write_text(
        json.dumps(obj,ensure_ascii=False),encoding="utf-8")
    return folder


def test_missing_master_catalog_safe_fallback(tmp_path):
    catalog,provenance=load_bundled_catalog(tmp_path)
    assert catalog=={}
    assert provenance is None


def test_source_verified_etf_master_is_loaded_without_upload(tmp_path):
    folder=_make_catalog(tmp_path)
    catalog,source=load_bundled_catalog(folder)
    assert len(catalog)==2
    assert catalog["091230"]["name"]=="TIGER 반도체"
    assert catalog["487230"]["index_name"]=="KRX 반도체"
    assert source["as_of_date"]=="2026-11-11"
    assert source["count"]==2
    assert source["mode"]=="공개 재배포 허가 근거 기록된 스냅샷"


@pytest.mark.parametrize("flag",["bad_count","bad_hash","future"])
def test_incorrect_catalog_manifest_is_never_loaded(tmp_path,flag):
    folder=_make_catalog(tmp_path,**{flag:True})
    catalog,source=load_bundled_catalog(folder)
    assert catalog=={}
    assert "error" in source


def test_missing_manifest_rejected(tmp_path):
    folder=_make_catalog(tmp_path)
    (folder/"etf_catalog_meta.json").unlink()
    catalog,source=load_bundled_catalog(folder)
    assert not catalog
    assert "error" in source


def test_code_with_leading_zero_stays_string(tmp_path):
    folder=_make_catalog(tmp_path)
    catalog,_=load_bundled_catalog(folder)
    assert "091230" in catalog
    assert "91230" not in catalog


def test_master_source_is_not_a_portfolio(tmp_path):
    folder=_make_catalog(tmp_path)
    catalog,manifest=load_bundled_catalog(folder)
    assert "holdings" not in catalog["091230"]
    assert "weight_pct" not in catalog["091230"]
    assert manifest["source_url"]=="https://data.krx.co.kr/"


def test_private_only_bundle_is_not_loaded_on_public_site(tmp_path):
    folder=_make_catalog(tmp_path)
    path=folder/"etf_catalog_meta.json"
    meta=json.loads(path.read_text(encoding="utf-8"))
    meta["distribution_status"]="private_only_pending_krx_redistribution_permission"
    meta["permission_reference"]=None
    path.write_text(json.dumps(meta),encoding="utf-8")
    result,source=load_bundled_catalog(folder)
    assert not result
    assert "재배포 허가" in source["error"]


def test_missing_permission_reference_blocks_public_bundle(tmp_path):
    folder=_make_catalog(tmp_path)
    path=folder/"etf_catalog_meta.json"
    meta=json.loads(path.read_text(encoding="utf-8"))
    meta.pop("permission_reference",None)
    path.write_text(json.dumps(meta),encoding="utf-8")
    result,source=load_bundled_catalog(folder)
    assert not result
    assert "재배포 허가" in source["error"]


def test_krx_original_metadata_fields_preserved_when_available():
    import csv
    import io
    from etf_engine import parse_catalog
    records=[
        ["표준코드","단축코드","한글종목명","한글종목약명","상장일",
         "기초지수명","기초시장분류","기초자산분류","운용사","총보수"],
        ["KR7091230003","091230","미래에셋 TIGER 반도체","TIGER 반도체",
         "2006/06/27","KRX 반도체","국내","주식","미래에셋자산운용","0.45"],
    ]
    buff=io.StringIO()
    csv.writer(buff,lineterminator="\n").writerows(records)
    out,meta=parse_catalog(buff.getvalue().encode("utf-8-sig"),"krx.csv")
    assert len(out)==1
    row=out[0]
    assert row["short_name"]=="TIGER 반도체"
    assert row["asset_market"]=="국내"
    assert row["asset_class"]=="주식"
    assert row["listing_date"]=="2006/06/27"
    assert row["total_fee_source"]=="0.45"


def test_private_bundle_builder_preserves_original_krx_columns(tmp_path):
    from datetime import date
    from scripts.build_etf_catalog import prepare
    original=("표준코드,단축코드,한글종목명,한글종목약명,기초지수명,"
              "기초시장분류,기초자산분류,운용사,총보수\n"
              "KR7091230003,091230,미래에셋 TIGER 반도체,TIGER 반도체,KRX 반도체,"
              "국내,주식,미래에셋자산운용,0.45\n").encode("utf-8-sig")
    source=tmp_path/"KRX.csv"
    source.write_bytes(original)
    output=tmp_path/"private"
    metadata=prepare(source,output,date(2026,11,11),"https://data.krx.co.kr/")
    assert metadata["count"]==1
    assert metadata["distribution_status"].startswith("private_only")
    raw=(output/"etf_catalog.csv").read_bytes().decode("utf-8-sig")
    assert "기초시장분류" in raw
    assert "KRX 반도체" in raw
    assert "0.45" in raw
    cat,error=load_bundled_catalog(output)
    assert not cat
    assert "재배포 허가" in error["error"]
