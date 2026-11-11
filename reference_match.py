"""Read-only, provenance-labelled fingerprints from previously examined KRX documents.

This module offers *possible ETF identity evidence* for unlinked KRX market-cap
composition tables. It must NEVER transform those weights into ETF NAV holdings.
"""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path

import pandas as pd


REFERENCE_DIR = Path(__file__).resolve().parent / "reference_data"


@lru_cache(maxsize=1)
def load_reference_fingerprints():
    """Only load curated local reference records; no network calls or raw user uploads."""
    references = []
    for path in sorted(REFERENCE_DIR.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("weight_basis") != "시가총액 기준 비중":
            continue
        rows = record.get("holdings") or []
        if not 10 <= len(rows) <= 50:
            continue
        codes = [str(row.get("security_id", "")) for row in rows]
        weights = [row.get("weight_pct") for row in rows]
        if len(set(codes)) != len(codes) or not all(
            len(code) == 6 and code.isdigit() for code in codes
        ):
            continue
        if not all(
            isinstance(w, (int, float)) and math.isfinite(w) and 0 <= w <= 100
            for w in weights
        ):
            continue
        if weights != sorted(weights, reverse=True):
            continue
        references.append(record)
    return references


def _normalized_name(value):
    """Ignore whitespace and simple punctuation only, not meaningful company words."""
    return "".join(c.lower() for c in str(value) if c.isalnum())


def match_reference_candidates(frame, weight_basis, *, reference_data=None):
    """Match a FULL numeric KRX composition table against a PARTIAL PDF fingerprint.

    The table must independently total ~100%, and *all* recorded top-10 rows
    must match in descending order by security ID, weight (two decimals) and
    company name. Never infer the ETF's holdings date or its NAV weights.

    This is a comparison-based research hint, NOT authenticated ETF identity.
    """
    if weight_basis != "시가총액 기준 비중" or frame is None or frame.empty:
        return []
    required = {"security_id", "security_name", "weight_pct"}
    if not required.issubset(frame.columns):
        return []
    ids = frame["security_id"].astype(str).str.strip()
    if ids.eq("").any() or ids.str.startswith("UNKNOWN_").any():
        return []
    if ids.duplicated().any():
        # A duplicated security may need reconciliation: do not guess.
        return []
    weights = pd.to_numeric(frame["weight_pct"], errors="coerce")
    if weights.isna().any() or not all(math.isfinite(float(w)) for w in weights):
        return []
    if (weights < 0).any() or (weights > 100.05).any():
        return []
    if abs(float(weights.sum()) - 100) > 0.05:
        return []
    original = pd.DataFrame({
        "security_id": ids,
        "security_name": frame["security_name"].astype(str).str.strip(),
        "weight_pct": weights,
    }).sort_values(["weight_pct", "security_id"], ascending=[False, True])

    candidates = []
    for record in reference_data if reference_data is not None else load_reference_fingerprints():
        if record.get("weight_basis") != weight_basis:
            continue
        expected = record.get("holdings", [])
        if len(expected) < 10 or len(original) < len(expected):
            continue
        head = original.head(len(expected)).to_dict("records")
        rows_match = all(
            str(source["security_id"]) == str(target["security_id"])
            and round(float(source["weight_pct"]), 2) == round(float(target["weight_pct"]), 2)
            and _normalized_name(source["security_name"]) == _normalized_name(target["security_name"])
            for source, target in zip(head, expected)
        )
        if not rows_match:
            continue
        candidates.append({
            "etf_code": str(record["etf_code"]),
            "etf_name": str(record["etf_name"]),
            "reference_id": record["reference_id"],
            "reference_source": record["source_document"],
            "reference_sha256": record["source_sha256"],
            "reference_scope": record["data_scope"],
            "weight_basis": weight_basis,
            "matched_rows": len(expected),
            "matched_weight_pct": round(sum(float(x["weight_pct"]) for x in expected), 2),
            "total_rows": len(original),
            "holdings_as_of_date": record.get("holdings_as_of_date"),
            "match_method": "종목코드·이름·원본 비중(소수점 2자리) 및 상위 순서 모두 일치",
            "verification_status": "기존 PDF와 표의 내용 교차일치 (ETF 원본 식별자·편입 기준일은 미검증)",
            "warning": "상위종목 일치는 ETF 원본 인증이 아닙니다. 시가총액 비중을 ETF 순자산 편입비중으로 사용하지 않습니다.",
        })
    return candidates
