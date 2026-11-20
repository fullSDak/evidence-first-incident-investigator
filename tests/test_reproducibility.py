from __future__ import annotations

import importlib.util
from pathlib import Path

from conftest import FIXTURES, ROOT


def test_fixture_builder_reproduces_every_input_byte(tmp_path):
    path = ROOT / "build_fixtures.py"
    spec = importlib.util.spec_from_file_location("_fixture_builder_repro_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    regenerated = tmp_path / "fixtures"
    module.ROOT = regenerated
    module.main()
    originals = {p.relative_to(FIXTURES): p.read_bytes() for p in FIXTURES.rglob("*") if p.is_file()}
    copies = {p.relative_to(regenerated): p.read_bytes() for p in regenerated.rglob("*") if p.is_file()}
    assert copies == originals, "The checked fixture bytes differ from the deterministic builder"
