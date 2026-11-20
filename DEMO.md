# Two-minute demo

[Watch the narrated walkthrough](demo/incident-investigator-demo.mp4). The video records real terminal commands against the included fictional fixtures. Its narration is a synthetic voice; captions are burned into the video. No LLM is called during the recording.

## Reproduce the walkthrough

From the repository root, after installing the test dependency as described in the README:

```bash
python3 -m demo.show sources
python3 -m incident_investigator --case fixtures/checkout_throttling --mode offline --output /tmp/evidence-demo-brief.md
python3 -m demo.show impact
python3 -m demo.show mechanism
python3 -m demo.show uncertainty
python3 -m pytest -v tests/test_investigation_contract.py \
  -k 'temporal_associations or missing_evidence_changes_claims or hostile_log_does_not_override'
```

`demo.show` prints selected fields from actual results returned by the investigator, including case-relative source paths and lines; it is a readable excerpt, not the complete report. Inspect the complete generated Markdown file for all observations, assessments and raw evidence. The final command selects three adversarial tests; `python3 -m pytest -q` runs the full suite.

## Narration transcript

**0:00 — The problem.** When a storefront incident follows a deploy, the tempting story is that the deploy caused it. But timing is not proof. This evidence-first investigator was built with AI assistance to make those assumptions visible.

**0:20 — The evidence.** The fictional case includes checkout metrics, deployment records, gateway logs, and explicit notes about missing coverage. These are invented records, not real customer data.

**0:40 — The investigation.** Here is the offline investigation. It links observations to the source records and separates what the records say from what remains a hypothesis. The local run does not require a model or a network connection.

**1:00 — Limited support.** In this scenario, the data show a sharp increase in failed checkout flows and linked payment gateway responses for selected requests. Those examples support a limited mechanism, not a proven initiating root cause.

**1:20 — Uncertainty.** The deployment and the later retry change are both worth checking. But the investigator does not promote either correlation into a proven cause. When essential telemetry is missing, it says insufficient evidence.

**1:40 — Tests and limits.** The tests cover missing evidence, misleading correlations, and instructions hidden inside a log. Optional model mode has no tools, and its output remains unverified. This is a starting point for human investigation, not an automatic incident commander.
