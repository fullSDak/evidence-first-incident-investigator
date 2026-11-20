"""Self-tests for the citation validator; no investigator or adapter is required."""
from __future__ import annotations

import pytest

from conftest import load_json
from test_investigation_contract import recursively_validate_citations


def test_valid_citation_resolves_to_the_exact_id(main_case):
    index = load_json(main_case / "evidence_index.json")["records"]
    data = {"nested": [{"citations": [{"evidence_id": "MET-03", "path": "evidence/metrics.jsonl", "line": 3}]}]}
    assert recursively_validate_citations(data, main_case, index) == 1


@pytest.mark.parametrize("citation", [
    {"evidence_id": "EV-FORGED-999", "path": "evidence/metrics.jsonl", "line": 3},
    {"evidence_id": "MET-03", "path": "evidence/metrics.jsonl", "line": 2},
    {"evidence_id": "MET-03", "path": "evidence/checkout.jsonl", "line": 3},
    {"evidence_id": "MET-03", "path": "../evidence/metrics.jsonl", "line": 3},
    {"evidence_id": "DEP-01", "path": "evidence/deployments.jsonl", "line": True},
])
def test_invalid_or_forged_citations_are_rejected(main_case, citation):
    index = load_json(main_case / "evidence_index.json")["records"]
    with pytest.raises(AssertionError):
        recursively_validate_citations({"citations": [citation]}, main_case, index)


def test_claim_with_empty_citations_is_rejected(main_case):
    index = load_json(main_case / "evidence_index.json")["records"]
    with pytest.raises(AssertionError):
        recursively_validate_citations({"citations": []}, main_case, index)
