"""Synthetic evidence-batch merging tests: no official filings asserted."""
import pytest

from research_analysis import merge_company_evidence_uploads


def csv(*lines):
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


HEADER = "종목코드,종목명,섹터,세부산업,국가,기업집단,근거URL,기준일"
A = "005930,가상회사A,반도체,메모리,한국,삼성,https://example.org/a,2026-11-10"
B = "000660,가상회사B,반도체,장비,한국,독립,https://example.org/b,2026-11-10"


def test_multiple_evidence_files_are_merged_without_loss():
    labels, source = merge_company_evidence_uploads([
        ("a.csv", csv(HEADER, A)),
        ("b.csv", csv(HEADER, B)),
    ])
    assert set(labels) == {"005930", "000660"}
    assert source["file_count"] == 2
    assert source["count"] == 2
    assert source["source_file"] == "a.csv, b.csv"
    assert len(source["source_sha256"]) == 64
    assert "독립 인증 전" in source["provenance"]


def test_identical_security_rows_in_two_files_are_deduplicated():
    labels, source = merge_company_evidence_uploads([
        ("a.csv", csv(HEADER, A)),
        ("a-copy.csv", csv(HEADER, A)),
    ])
    assert len(labels) == 1
    assert source["file_count"] == 2


def test_disagreeing_company_labels_across_files_are_rejected():
    with pytest.raises(ValueError, match="여러 파일에서 서로 다릅니다"):
        merge_company_evidence_uploads([
            ("first.csv", csv(HEADER, A)),
            ("second.csv", csv(HEADER, A.replace("메모리", "장비"))),
        ])


def test_conflicting_provenance_is_also_rejected():
    with pytest.raises(ValueError, match="종목코드 005930"):
        merge_company_evidence_uploads([
            ("first.csv", csv(HEADER, A)),
            ("second.csv", csv(HEADER, A.replace("example.org/a", "example.org/new"))),
        ])


def test_empty_or_excessive_batches_fail_safely():
    with pytest.raises(ValueError, match="1~12개"):
        merge_company_evidence_uploads([])
    with pytest.raises(ValueError, match="1~12개"):
        merge_company_evidence_uploads([("a.csv", csv(HEADER, A))] * 13)


def test_file_name_does_not_become_financial_evidence():
    labels, source = merge_company_evidence_uploads([
        ("folder\\corporate.csv", csv(HEADER, A)),
    ])
    assert source["sources"][0]["source_file"] == "corporate.csv"
    assert labels["005930"]["source_url"] == "https://example.org/a"
