"""Deterministic observations and clearly separated, testable hypotheses."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .ingest import load_evidence
from .structured_analysis import analyze_structured

_STATUS_PATTERN = re.compile(r"\b(?:http_status|status_code|status)\s*[=:]\s*([1-5][0-9]{2})\b", re.I)
MAX_FINDINGS_PER_KIND = 20
MAX_INTAKE_BYTES = 1024 * 1024


def _status(rec: dict[str, Any]) -> int | None:
    data = rec["data"]
    if data is not None:
        value: Any = None
        for key in ("status", "status_code", "http_status", "http.status_code"):
            if key in data:
                value = data[key]
                break
        if value is None and isinstance(data.get("http"), dict):
            value = data["http"].get("status_code")
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and 100 <= value <= 599:
            return value
        if isinstance(value, str) and re.fullmatch(r"[1-5][0-9]{2}", value):
            return int(value)
        return None
    match = _STATUS_PATTERN.search(rec["text"])
    return int(match.group(1)) if match else None


def _citations(rec: dict[str, Any]) -> list[str]:
    return [*rec.get("context_ids", []), rec["id"]]


def _intake(input_path: str | Path, warnings: list[str]) -> dict[str, Any] | None:
    """Read optional incident intake as metadata, never as evidence or instructions."""
    root = Path(input_path).expanduser()
    path = root / "incident.json"
    if not root.is_dir() or not path.is_file():
        return None
    try:
        if path.is_symlink() or path.stat().st_size > MAX_INTAKE_BYTES:
            raise ValueError("intake is a symlink or too large")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("incident_id"), str):
            raise ValueError("missing incident ID")
        qs = data.get("questions")
        if (not isinstance(qs, list) or len(qs) > 1000 or
                any(not isinstance(q, dict) or not isinstance(q.get("id"), str) or not q["id"].strip()
                    or not isinstance(q.get("question"), str) for q in qs) or
                len({q["id"] for q in qs}) != len(qs)):
            raise ValueError("invalid questions")
        return {"incident_id": data["incident_id"], "questions": qs}
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        warnings.append(f"Optional incident intake could not be read or validated: {exc}")
        return None


def investigate(input_path: str | Path, mode: str = "offline", *, llm_config: Any = None) -> dict[str, Any]:
    """Investigate a file or directory and return JSON-serializable structured data.

    Observations only describe supplied records. LLM content never goes into
    deterministic findings. Evidence and intake are untrusted. Failures in LLM
    mode are never silently converted to offline results.
    """
    if mode not in {"offline", "llm"}:
        raise ValueError("mode must be 'offline' or 'llm'")
    evidence, warnings = load_evidence(input_path)
    intake = _intake(input_path, warnings)
    analysis = analyze_structured(evidence, intake["questions"] if intake is not None else None)
    facts: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    insufficient: list[str] = [
        "The initiating root cause is unknown. Supplied records alone do not establish full customer impact or a causal relationship between events.",
        "Record content and timestamps are untrusted and have not been independently verified; missing records are not evidence of absence.",
    ]
    limitations: list[str] = [
        "These are observations of supplied files, not independently established facts about a real system.",
        "Temporal association alone cannot establish causation. No commands in evidence are executed.",
    ]
    if analysis["structured_records_seen"]:
        facts.extend(analysis["impact"])
        facts.extend(analysis["sampled_mechanisms"])
        hypotheses.extend(analysis["hypotheses"])
        limitations.extend([
            "Metric aggregates cover only each listed start-inclusive, end-exclusive window; they are not whole-incident totals.",
            "Individual checkout and gateway events are selected examples, not a complete or representative population.",
            "A flow can have an upstream 429 and still succeed after retry; 429 flow counts are not failed-flow counts.",
            "A later healthier observed window does not establish complete recovery or a causal intervention effect.",
        ])
        if analysis["invalid_metric_windows"]:
            warnings.append(f"Ignored {analysis['invalid_metric_windows']} invalid or incomplete structured metric window(s); raw lines remain evidence.")
    else:
        # Preserve the original simple log/CSV behavior for non-fixture inputs.
        limitations.append("For unstructured inputs only specified HTTP status fields or status= markers are recognized; no incident window or baseline is inferred.")
        error_records = [r for r in evidence if r["kind"] == "log" and (_status(r) or 0) >= 500]
        deployment_records = [r for r in evidence if r["kind"] == "deployment"]
        for rec in error_records[:MAX_FINDINGS_PER_KIND]:
            facts.append({"statement": f"The source line reports HTTP status {_status(rec)}.", "citations": _citations(rec)})
        for rec in deployment_records[:MAX_FINDINGS_PER_KIND]:
            facts.append({"statement": "The source line is classified as a deployment record by its path or record_type; its contents are not independently verified.", "citations": _citations(rec)})
        if error_records and deployment_records:
            hypotheses.append({"statement": "A deployment-related regression is a possible explanation for the reported 5xx status, not an established cause. Check event times, affected versions, and independent telemetry before concluding.",
                               "citations": list(dict.fromkeys(_citations(error_records[0]) + _citations(deployment_records[0])))})
        if not error_records:
            insufficient.append("No HTTP 5xx was detected using the supported patterns; this does not rule out failures or prove normal operation.")
        if not deployment_records:
            insufficient.append("No deployment-category record was identified, so deployment involvement cannot be assessed from these inputs.")
        if len(error_records) > MAX_FINDINGS_PER_KIND or len(deployment_records) > MAX_FINDINGS_PER_KIND:
            limitations.append(f"Findings are capped at {MAX_FINDINGS_PER_KIND} per category; the evidence list retains all ingested lines.")
    result: dict[str, Any] = {
        "case": Path(input_path).name,
        "incident_id": intake["incident_id"] if intake else None,
        "mode": mode,
        "evidence": evidence,
        "facts": facts,
        "hypotheses": hypotheses,
        "impact": analysis["impact"],
        "timeline": analysis["timeline"],
        "sampled_mechanisms": analysis["sampled_mechanisms"],
        "root_cause": analysis["root_cause"],
        "unknowns": analysis["unknowns"],
        "structured_records_seen": analysis["structured_records_seen"],
        "insufficient_evidence": insufficient,
        "limitations": limitations,
        "ingestion_warnings": warnings,
        "model_interpretations": [],
        "model_limitations": [],
        "model_metadata": None,
    }
    if mode == "llm":
        from .llm import request_interpretations
        model_result, metadata = request_interpretations(evidence, llm_config)
        result["model_interpretations"] = model_result["interpretations"]
        result["model_limitations"] = model_result["limitations"]
        result["model_metadata"] = metadata
        result["limitations"].append("Model interpretations are unverified, may be incorrect or prompt-injected, and require human review against the cited source lines.")
    return result
