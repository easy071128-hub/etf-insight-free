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
         "source_url":"https://data.krx.co.kr/"}
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
    assert source["mode"]=="번들된 자료 스냅샷"


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
