"""Deterministic analysis of structured event records, never instructions in records.

Citations are the ingestion layer's content-addressed IDs.  No fixture IDs or
index metadata are used to derive observations or conclusions.
"""
from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _text(value: Any, default: str = "unspecified", limit: int = 300) -> str:
    """Keep data as bounded, single-line text; rendering still escapes it."""
    if not isinstance(value, str) or not value.strip():
        return default
    return " ".join(value.split())[:limit]


def _scalar(value: Any) -> str:
    if value is None or isinstance(value, (bool, int, float, str)):
        return _text(json.dumps(value, ensure_ascii=False), "unknown", 100)
    return "[non-scalar value]"


def _cites(*records: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(ident for rec in records for ident in (*rec.get("context_ids", []), rec["id"])))


def _metric(rec: dict[str, Any]) -> dict[str, Any] | None:
    d = rec["data"]
    start, end = _time(d.get("window_start")), _time(d.get("window_end"))
    counts = [d.get(k) for k in ("total_checkout_flows", "successful_checkout_flows", "failed_checkout_flows")]
    gateway = d.get("flows_with_gateway_429")
    if (start is None or end is None or start >= end or
            not all(type(v) is int and v >= 0 for v in counts) or
            counts[1] + counts[2] != counts[0] or
            (gateway is not None and (type(gateway) is not int or not 0 <= gateway <= counts[0]))):
        return None
    return {"record": rec, "start": start, "end": end,
            "service": _text(d.get("service")), "total": counts[0], "success": counts[1],
            "failed": counts[2], "gateway": gateway,
            "rate": counts[2] / counts[0] if counts[0] else None}


def _metric_sentence(m: dict[str, Any]) -> str:
    d = m["record"]["data"]
    rate = "rate unavailable (zero total)" if m["rate"] is None else f"{100 * m['rate']:.2f}% failed"
    gateway = ("the number of flows with gateway 429 is unavailable" if m["gateway"] is None
               else f"{m['gateway']} of {m['total']} flows had a gateway 429")
    return (f"{m['service']} window {d['window_start']} to {d['window_end']} (start inclusive, end exclusive): "
            f"{m['failed']} of {m['total']} checkout flows failed ({rate}); "
            f"{m['success']} succeeded; {gateway}. A flow with a 429 can succeed after retry, "
            "so 429 counts are not failed-flow counts.")


def _valid_event(rec: dict[str, Any]) -> bool:
    return _time(rec["data"].get("event_time")) is not None


def _timed(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((r for r in records if _valid_event(r)), key=lambda r: (_time(r["data"]["event_time"]), r["source"], r["line"]))


def _topic(question: dict[str, Any]) -> str:
    # Intake is untrusted text. It is used only as a literal topic selector, never as instructions.
    text = f"{question.get('id', '')} {question.get('question', '')}".lower()
    if re.search(r"deploy|release", text):
        return "deployment"
    if re.search(r"retry|mitigat|intervention|operator.action|setting.change", text):
        return "action"
    if re.search(r"429|gateway|upstream|throttl", text):
        return "gateway"
    return "other"


def _partial_gateway_question(q: dict[str, Any]) -> bool:
    text = f"{q.get('id', '')} {q.get('question', '')}".lower()
    # A limited contribution question is not the same as an incident-wide cause question.
    return bool(re.search(r"contribut", text)) and not bool(re.search(r"root.cause|entire.incident|whole.incident|sole.cause", text))


def analyze_structured(evidence: list[dict[str, Any]], questions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Analyze valid recognized records and answer intake questions conservatively.

    This does not infer source completeness, event causation, or unobserved windows.
    Invalid/incomplete typed records are retained by ingestion, but not interpreted.
    """
    typed: dict[str, list[dict[str, Any]]] = {}
    for rec in evidence:
        data = rec.get("data")
        if isinstance(data, dict) and isinstance(data.get("kind"), str):
            typed.setdefault(data["kind"], []).append(rec)
    metrics = [m for r in typed.get("metric_window", []) if (m := _metric(r)) is not None]
    metrics.sort(key=lambda m: (m["start"], m["end"], m["record"]["source"], m["record"]["line"]))
    deployments = _timed(typed.get("deployment", []))
    actions = _timed(typed.get("operator_action", []))
    checkouts = _timed(typed.get("checkout_event", []))
    gateways = _timed(typed.get("gateway_event", []))
    coverage = [r for r in typed.get("coverage", []) if isinstance(r["data"].get("availability"), str)
                and r["data"]["availability"] in {"not_supplied", "partial"}
                and _time(r["data"].get("window_start")) is not None and _time(r["data"].get("window_end")) is not None
                and _time(r["data"]["window_start"]) < _time(r["data"]["window_end"])]
    fallback = evidence[:1]

    impact = [{"statement": _metric_sentence(m), "citations": _cites(m["record"])} for m in metrics]
    # Compare adjacent observed, non-overlapping windows of the same service. Do not
    # fill intervening missing minutes or infer a complete incident timeline.
    previous: dict[str, dict[str, Any]] = {}
    first_increase: dict[str, Any] | None = None
    for m in metrics:
        prev = previous.get(m["service"])
        if (prev and prev["end"] <= m["start"] and prev["rate"] is not None and m["rate"] is not None
                and m["rate"] > prev["rate"]):
            if first_increase is None:
                first_increase = m
            impact.append({"statement": (f"In the listed {m['service']} windows, failures rose from "
                f"{prev['failed']} of {prev['total']} ({100*prev['rate']:.2f}%) to "
                f"{m['failed']} of {m['total']} ({100*m['rate']:.2f}%). "
                "This comparison covers only these windows, not the whole incident."),
                "citations": _cites(prev["record"], m["record"])})
        previous[m["service"]] = m
    if not impact and fallback:
        impact.append({"statement": "No valid structured checkout metric window was available; impact cannot be quantified from the recognized fields.", "citations": _cites(*fallback)})

    timeline: list[dict[str, Any]] = []
    for rec in deployments:
        d = rec["data"]
        scope = d.get("change_scope")
        scope_text = ", ".join(_text(x, limit=100) for x in scope[:20]) if isinstance(scope, list) else "not specified"
        timeline.append({"timestamp": d["event_time"], "event": (f"Deployment record: {_text(d.get('service'))}, version {_text(d.get('version'))}, "
            f"status {_text(d.get('status'))}; declared change scope: {scope_text or 'not specified'}. "
            "Declared scope does not establish downstream effects."), "citations": _cites(rec)})
    for rec in actions:
        d = rec["data"]
        timeline.append({"timestamp": d["event_time"], "event": (f"Operator action {_text(d.get('action'))} on {_text(d.get('service'))}: "
            f"{_text(d.get('setting'))} changed from {_scalar(d.get('before'))} to {_scalar(d.get('after'))}. "
            "The record alone does not establish its effect."), "citations": _cites(rec)})
    for m in metrics:
        timeline.append({"timestamp": m["record"]["data"]["window_start"], "event": _metric_sentence(m), "citations": _cites(m["record"])})
    # Compare only observed windows for the same service; do not assert that the
    # intervention caused the change or that the system fully recovered.
    for action in actions:
        d = action["data"]
        action_time = _time(d["event_time"])
        service = _text(d.get("service"))
        before = [m for m in metrics if m["service"] == service and m["end"] <= action_time and m["rate"] is not None]
        after = [m for m in metrics if m["service"] == service and m["start"] >= action_time and m["rate"] is not None]
        if before and after:
            peak = max(before, key=lambda m: m["rate"])
            improved = next((m for m in after if m["rate"] < peak["rate"]), None)
            if improved:
                pd, nd = peak["record"]["data"], improved["record"]["data"]
                timeline.append({"timestamp": nd["window_start"], "event": (
                    f"The listed window {nd['window_start']} to {nd['window_end']} after the action was healthier than "
                    f"the earlier listed window {pd['window_start']} to {pd['window_end']}: "
                    f"{improved['failed']} of {improved['total']} failed ({100*improved['rate']:.2f}%) versus "
                    f"{peak['failed']} of {peak['total']} ({100*peak['rate']:.2f}%). "
                    "This observation does not establish complete recovery or that the action caused the improvement."),
                    "citations": _cites(action, peak["record"], improved["record"])})
    timeline.sort(key=lambda entry: _time(entry["timestamp"]))

    # A failed checkout and an upstream 429 on the same trace are selected
    # examples, not a representative population. Require a throttling error and
    # a preceding or simultaneous gateway event to support even this limited link.
    indexed_gateway: dict[str, list[dict[str, Any]]] = {}
    for rec in gateways:
        d = rec["data"]
        trace = d.get("trace_id")
        if isinstance(trace, str) and trace.strip() and type(d.get("upstream_http_status")) is int and d["upstream_http_status"] == 429:
            indexed_gateway.setdefault(trace, []).append(rec)
    linked: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for checkout in checkouts:
        d = checkout["data"]
        trace, error = d.get("trace_id"), d.get("error_code")
        if not (isinstance(trace, str) and trace.strip() and isinstance(error, str)
                and re.search(r"throttl|rate.?limit|429", error, re.I)
                and isinstance(d.get("outcome"), str) and d["outcome"].lower() in {"failed", "failure", "error"}):
            continue
        candidates = [g for g in indexed_gateway.get(trace, []) if _time(g["data"]["event_time"]) <= _time(d["event_time"])]
        if candidates:
            linked.append((checkout, candidates[-1]))
    sampled = []
    for checkout, gateway in linked:
        cd, gd = checkout["data"], gateway["data"]
        sampled.append({"statement": (f"Selected trace {_text(cd.get('trace_id'))}: a failed checkout with a throttling error "
            f"and an earlier or simultaneous upstream HTTP 429 from {_text(gd.get('upstream'))} share a trace ID. "
            "This supports a 429 contribution to this sampled request only; it does not establish why the provider returned 429 or an incident-wide initiating cause."),
            "citations": _cites(checkout, gateway)})

    unknowns = []
    for rec in coverage:
        d = rec["data"]
        unknowns.append({"statement": (f"Coverage gap for {_text(d.get('source'))} during {_text(d.get('window_start'))} to {_text(d.get('window_end'))}: "
            f"{_text(d.get('availability'))}. {_text(d.get('detail'), 'No further detail supplied.')} "
            "Missing or partial evidence is not evidence that an event did not occur."), "citations": _cites(rec)})
    if not unknowns and fallback:
        unknowns.append({"statement": "Source coverage and completeness are not established; missing information cannot be treated as absence.", "citations": _cites(*fallback)})

    root_records = coverage or deployments or [m["record"] for m in metrics] or fallback
    root = {"assessment": "not_established", "statement": ("The initiating root cause is unknown and not established. "
        "Timing and selected request correlations cannot establish why the incident began or what caused it; "
        "source coverage, independent comparisons and provider/configuration evidence may be incomplete."),
        "citations": _cites(*root_records)}

    assessments = []
    if questions is None:
        questions = []
        if deployments:
            questions.append({"id": "deployment", "question": "Did the deployment cause the incident?"})
        if gateways or coverage:
            questions.append({"id": "gateway_contribution", "question": "Did upstream 429 responses contribute to failed requests?"})
        if actions:
            questions.append({"id": "action", "question": "Did the operator action cause recovery?"})
    for q in questions:
        topic = _topic(q)
        assessment = "not_established"
        relevant: list[dict[str, Any]] = []
        if topic == "deployment":
            relevant.extend(deployments)
            # The first metric starting after the release that is worse than a
            # prior nonoverlapping same-service window is a useful observed comparison.
            later = []
            if deployments:
                deploy_time = _time(deployments[-1]["data"]["event_time"])
                later = [m for m in metrics if m["start"] >= deploy_time]
            if first_increase and first_increase in later:
                relevant.append(first_increase["record"])
            elif later:
                relevant.append(later[0]["record"])
            relevant.extend(coverage)
            rationale = ("Deployment causation is not established: release and changing failure counts may be temporally associated, "
                         "but declared scope and timing alone do not determine downstream effects. "
                         "Independent change validation, comparison cohorts, and other source coverage may be missing.")
        elif topic == "action":
            relevant.extend(actions)
            if actions:
                action_time = _time(actions[-1]["data"]["event_time"])
                later = [m for m in metrics if m["start"] >= action_time]
                if later:
                    relevant.extend(m["record"] for m in later)
            relevant.extend(coverage)
            rationale = ("An action's causal effect on recovery is not established. Later listed windows may improve, "
                         "but temporal order does not isolate the intervention from other causes or establish complete recovery.")
        elif topic == "gateway":
            if linked and _partial_gateway_question(q):
                assessment = "supported"
                relevant.extend(r for pair in linked for r in pair)
                rationale = ("Supported only for the selected linked failed requests: each cited pair shares a trace, "
                             "with an upstream 429 and a checkout throttling error. This is not proof of an incident-wide "
                             "initiating root cause or why the upstream returned 429.")
            else:
                relevant.extend(coverage)
                rationale = ("A 429 contribution or incident-wide cause is not established from the available evidence; "
                             "missing gateway or checkout traces cannot be treated as zero responses. "
                             "Even linked samples would not establish an incident-wide initiating cause.")
        else:
            relevant.extend(coverage)
            rationale = "The answer is not established by the recognized evidence; further independent investigation is needed."
        relevant = relevant or fallback
        assessments.append({"id": str(q.get("id", "")), "assessment": assessment, "rationale": rationale,
                            "statement": rationale, "citations": _cites(*relevant)})

    return {"impact": impact, "timeline": timeline, "sampled_mechanisms": sampled,
            "hypotheses": assessments, "root_cause": root, "unknowns": unknowns,
            "structured_records_seen": any(k in typed for k in ("metric_window", "deployment", "checkout_event", "gateway_event", "operator_action", "coverage")),
            "invalid_metric_windows": len(typed.get("metric_window", [])) - len(metrics)}
