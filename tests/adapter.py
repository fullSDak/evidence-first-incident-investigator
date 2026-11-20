"""Translate investigator results into the contract using the bundle's locator index.

The investigator performs all analysis. This adapter only validates intake and
translates content-addressed evidence citations to indexed physical locators.
"""
from __future__ import annotations

import json
from pathlib import Path

from incident_investigator.investigation import investigate as run_investigation


def investigate(bundle_dir: Path, incident_id: str) -> dict:
    bundle = Path(bundle_dir).resolve()
    intake = json.loads((bundle / "incident.json").read_text(encoding="utf-8"))
    if intake.get("incident_id") != incident_id:
        raise ValueError("Requested incident ID does not match intake")
    result = run_investigation(bundle, mode="offline")
    if result.get("incident_id") != incident_id:
        raise ValueError("Investigator did not accept matching intake")
    index = json.loads((bundle / "evidence_index.json").read_text(encoding="utf-8"))["records"]
    by_locator = {}
    for fixture_id, locator in index.items():
        relative, line = locator["path"], locator["line"]
        if (not isinstance(fixture_id, str) or not isinstance(relative, str) or Path(relative).is_absolute()
                or not (bundle / relative).resolve().is_relative_to(bundle)
                or type(line) is not int or line < 1 or (relative, line) in by_locator):
            raise ValueError("Invalid or duplicate indexed evidence locator")
        by_locator[(relative, line)] = fixture_id
    crosswalk = {}
    for rec in result["evidence"]:
        key = rec["source"], rec["line"]
        fixture_id = by_locator.get(key)
        if fixture_id is None or not isinstance(rec.get("data"), dict) or rec["data"].get("id") != fixture_id:
            raise ValueError(f"Evidence does not match index at {key!r}")
        crosswalk[rec["id"]] = {"evidence_id": fixture_id, "path": key[0], "line": key[1]}

    def citations(item):
        return [crosswalk[ident] for ident in item["citations"]]

    return {
        "incident_id": result["incident_id"],
        "impact": [{"statement": x["statement"], "citations": citations(x)} for x in result["impact"]],
        "timeline": [{"timestamp": x["timestamp"], "event": x["event"], "citations": citations(x)} for x in result["timeline"]],
        "hypotheses": [{"id": x["id"], "assessment": x["assessment"], "rationale": x["rationale"], "citations": citations(x)} for x in result["hypotheses"]],
        "root_cause": {"assessment": result["root_cause"]["assessment"], "statement": result["root_cause"]["statement"], "citations": citations(result["root_cause"])},
        "unknowns": [{"statement": x["statement"], "citations": citations(x)} for x in result["unknowns"]],
    }
