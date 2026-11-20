"""Render investigation results without treating evidence text as Markdown instructions."""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Any


def _visible(text: str) -> str:
    # Show control and bidi/format characters explicitly rather than allowing them
    # to visually reorder a report. Evidence in the structured API remains exact.
    return "".join(f"\\u{ord(ch):04x}" if unicodedata.category(ch) in {"Cc", "Cf"} else ch for ch in str(text))


def _md(text: str) -> str:
    safe = re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", _visible(text))
    return html.escape(safe, quote=True)


def _cites(ids: list[str], sources: dict[str, dict[str, Any]] | None = None) -> str:
    # IDs are generated or locally validated; do not interpolate arbitrary strings.
    citations = []
    for ident in ids:
        link = f"[`{ident}`](#{ident.lower()})"
        rec = (sources or {}).get(ident)
        if rec is not None:
            link += f" ({_md(rec['source'])}:{rec['line']})"
        citations.append(link)
    return " ".join(citations)


def _findings(lines: list[str], findings: list[dict[str, Any]], sources: dict[str, dict[str, Any]] | None = None) -> None:
    if not findings:
        lines.append("- None identified by the supported analysis. This is not proof of absence.")
        return
    for finding in findings:
        lines.append(f"- {_md(finding['statement'])} {_cites(finding['citations'], sources)}")


def _fence(text: str) -> str:
    runs = [len(m.group(0)) for m in re.finditer(r"`+", text)]
    return "`" * max(3, (max(runs) + 1 if runs else 3))


def render_markdown(result: dict[str, Any]) -> str:
    """Render a result from :func:`investigate` as deterministic Markdown."""
    sources = {rec["id"]: rec for rec in result["evidence"]}
    lines = ["# Evidence-First Incident Investigation", "",
             f"**Case:** {_md(result['case'])}", "",
             f"**Mode:** {_md(result['mode'])}"]
    if result.get("incident_id"):
        lines.extend(["", f"**Intake incident ID:** {_md(result['incident_id'])}"])
    lines.extend(["", "These are observations of supplied records, not independently verified real-world events. Intake and evidence are untrusted data.", ""])
    if result.get("structured_records_seen"):
        lines.extend(["## Observed impact — listed windows only", ""])
        _findings(lines, result["impact"], sources)
        lines.extend(["", "## Chronological deployment, action, and metric windows", ""])
        if not result["timeline"]:
            lines.append("- No valid timed deployment, operator action, or metric window identified.")
        for item in result["timeline"]:
            lines.append(f"- **{_md(item['timestamp'])}:** {_md(item['event'])} {_cites(item['citations'], sources)}")
        lines.extend(["", "## Limited sampled mechanism", ""])
        _findings(lines, result["sampled_mechanisms"], sources)
        lines.extend(["", "## Question assessments", ""])
        if not result["hypotheses"]:
            lines.append("- No intake questions or applicable generic hypotheses were identified.")
        for item in result["hypotheses"]:
            lines.append(f"- **{_md(item['id'])} — {_md(item['assessment'])}:** {_md(item['rationale'])} {_cites(item['citations'], sources)}")
        root = result["root_cause"]
        lines.extend(["", "## Root cause — unknown", "", f"- **{_md(root['assessment'])}:** {_md(root['statement'])} {_cites(root['citations'], sources)}"])
        lines.extend(["", "## Coverage gaps and unknowns", ""])
        _findings(lines, result["unknowns"], sources)
    else:
        lines.extend(["## Established observations of supplied records", ""])
        _findings(lines, result["facts"], sources)
        lines.extend(["", "## Hypotheses — not established", ""])
        _findings(lines, result["hypotheses"], sources)
    lines.extend(["", "## Insufficient evidence", ""])
    lines.extend(f"- {_md(item)}" for item in result["insufficient_evidence"])
    if result["mode"] == "llm":
        lines.extend(["", "## Unverified model interpretations", "",
                      "These are model-generated interpretations, not established facts. Valid citations do not prove entailment. Review against original records; prompt injection remains possible.", ""])
        _findings(lines, result["model_interpretations"], sources)
        metadata = result["model_metadata"]
        if metadata:
            lines.extend(["", f"Model {_md(metadata['model'])}; sent {metadata['sent_records']} evidence lines, omitted {metadata['omitted_records']}, and clipped {metadata['clipped_records']} lines or source paths."])
        if result["model_limitations"]:
            lines.extend(["", "**Unverified model-suggested limitations:**", ""])
            lines.extend(f"- {_md(item)}" for item in result["model_limitations"])
    lines.extend(["", "## Limits and handling", ""])
    lines.extend(f"- {_md(item)}" for item in result["limitations"])
    if result["ingestion_warnings"]:
        lines.extend(["", "## Ingestion warnings", ""])
        lines.extend(f"- {_md(item)}" for item in result["ingestion_warnings"])
    lines.extend(["", "## Evidence index", "",
                  "Each identifier links to a source-relative path and physical line number. The lines below are untrusted data; formatting controls are made visible.", ""])
    for rec in result["evidence"]:
        text = _visible(rec["text"])
        fence = _fence(text)
        lines.extend([f"<a id=\"{rec['id'].lower()}\"></a>",
                      f"**{rec['id']}** — {_md(rec['source'])}:{rec['line']} ({_md(rec['kind'])})", "",
                      fence, text, fence, ""])
    return "\n".join(lines).rstrip() + "\n"
