"""Readable excerpts from the real investigator for the recorded walkthrough."""
from pathlib import Path
import sys
import textwrap

from incident_investigator import investigate

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "fixtures" / "checkout_throttling"


def paragraph(text):
    print(textwrap.fill(str(text), width=60, subsequent_indent="  "))


def citations(result, item):
    by_id = {r["id"]: r for r in result["evidence"]}
    for ident in item["citations"][:2]:
        record = by_id[ident]
        print(f"  -> {ident}  {record['source']}:{record['line']}")


result = investigate(CASE)
section = sys.argv[1]
if section == "sources":
    by_record_id = {r["data"].get("id"): r for r in result["evidence"] if isinstance(r["data"], dict)}
    for ident in ("DEP-01", "MET-03", "COV-01"):
        rec = by_record_id[ident]
        d = rec["data"]
        print(f"\n{ident}  {rec['source']}:{rec['line']}")
        if d["kind"] == "deployment":
            paragraph(f"{d['event_time']}: {d['service']} release {d['status']}")
        elif d["kind"] == "metric_window":
            paragraph(f"{d['window_start']}: {d['failed_checkout_flows']} of {d['total_checkout_flows']} checkout flows failed")
        else:
            paragraph(f"Coverage: {d['source']} is {d['availability']}")
elif section == "impact":
    item = next(x for x in result["impact"] if "rose from 2 of 120" in x["statement"] and "58 of 120" in x["statement"])
    print("OBSERVED IMPACT (listed windows only)\n")
    paragraph(item["statement"])
    citations(result, item)
elif section == "mechanism":
    item = result["sampled_mechanisms"][0]
    print("LIMITED SAMPLED MECHANISM\n")
    paragraph(item["statement"])
    citations(result, item)
elif section == "uncertainty":
    print("HYPOTHESES AND MISSING EVIDENCE\n")
    for item in result["hypotheses"]:
        print(f"{item['id']}: {item['assessment']}")
    print(f"Root cause: {result['root_cause']['assessment']}\n")
    missing = investigate(ROOT / "fixtures" / "missing_evidence")
    item = next(x for x in missing["hypotheses"] if x["id"] == "gateway_429_contributed")
    print("Second case, missing gateway traces:")
    paragraph(item["rationale"])
    citations(missing, item)
else:
    raise SystemExit("expected sources, impact, mechanism, or uncertainty")
