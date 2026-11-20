from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def adapter():
    location = os.environ.get("EVIDENCE_INVESTIGATOR_ADAPTER", str(ROOT / "tests" / "adapter.py"))
    if not location:
        pytest.skip("Set EVIDENCE_INVESTIGATOR_ADAPTER to an adapter module (see TEST_CONTRACT.md)")
    path = Path(location).expanduser().resolve()
    assert path.is_file(), f"Adapter module not found: {path}"
    spec = importlib.util.spec_from_file_location("_investigator_contract_adapter", path)
    assert spec is not None and spec.loader is not None, f"Cannot load adapter: {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "investigate", None)
    assert callable(fn), "Adapter must define investigate(bundle_dir: Path, incident_id: str)"
    return fn


@pytest.fixture(scope="session")
def main_case():
    return FIXTURES / "checkout_throttling"


@pytest.fixture(scope="session")
def missing_case():
    return FIXTURES / "missing_evidence"


@pytest.fixture(scope="session")
def main_report(adapter, main_case):
    return adapter(main_case, "INC-2025-0417-001")


@pytest.fixture(scope="session")
def missing_report(adapter, missing_case):
    return adapter(missing_case, "INC-2025-0417-002")
