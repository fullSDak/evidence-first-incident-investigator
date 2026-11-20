# Evidence-First Incident Investigator

**A small, inspectable investigator for a fictional online store.** It reads invented logs, metrics and deployment records; produces a source-linked investigation brief; separates observations from hypotheses; and says **insufficient evidence** instead of guessing a root cause.

[Watch the two-minute demo](demo/incident-investigator-demo.mp4) · [Read the example brief](examples/checkout-brief.md) · [Explore the synthetic evidence](fixtures/checkout_throttling/evidence/) · [Run the tests](#tests)

> HarborCart and MarblePay are fictional. Every incident record in this repository is invented. This is a prototype for human investigation, not an automated production incident responder.

## The case

A storefront deployment preceded a checkout failure spike. In one listed minute, the synthetic metrics report **2 failed checkout flows out of 120**; in the next, **58 out of 120** ([baseline](fixtures/checkout_throttling/evidence/metrics.jsonl#L2), [spike](fixtures/checkout_throttling/evidence/metrics.jsonl#L3)). Selected checkout and payment-gateway records share trace IDs and report upstream 429s. Those linked examples support a limited contribution to the sampled failures; they do **not** establish the initiating cause across the incident.

The deployment and a later retry-setting change are worth investigating, but their timing alone proves neither caused the incident or recovery. Provider quota information and complete traces are missing. The second case withholds gateway traces altogether and demonstrates that missing evidence is not a zero count.

## Run locally

Requires Python **3.10+**. The investigator itself has no third-party runtime dependencies. After cloning, the investigation runs offline and does not require an API key:

```bash
git clone https://github.com/fullSDak/evidence-first-incident-investigator.git
cd evidence-first-incident-investigator
python3 -m incident_investigator --case fixtures/checkout_throttling --mode offline --output investigation.md
```

Open `investigation.md` and follow a cited evidence ID to its source line in the report's evidence index. Each entry identifies the case-relative source file and its physical line number. Run the evidence-poor case with:

```bash
python3 -m incident_investigator --case fixtures/missing_evidence --mode offline --output missing-evidence.md
```

Omit `--output` to print the brief. `--input` is an alias for `--case`; either accepts a file or a directory. Do not overwrite source records. See [DEMO.md](DEMO.md) for the walkthrough and narration.

## How it works

1. **Collect evidence.** The loader reads supported `.jsonl`, `.ndjson`, `.log`, `.txt` and single-line `.csv` files from a local case. It keeps physical line numbers and exact line text, rejects symlinks and bounds input sizes. The optional `incident.json` contains untrusted questions, not independent evidence.
2. **Analyze conservatively.** Recognized structured records yield per-window counts, a timeline, limited trace-pair observations, explicit coverage gaps and question assessments. Other supported log formats use a simpler status/deployment analysis. The structured analyzer is deliberately narrow, not a general observability platform.
3. **Link claims to records.** Evidence IDs are derived from a source-relative path, physical line and exact text; the brief links each cited ID to the evidence index. A citation lets a reader inspect the record—it does not prove that the record is accurate or that it entails the claim.
4. **Keep uncertainties visible.** Reported metrics are limited to the listed windows; selected traces are not a complete population. Temporal proximity is not treated as causal proof. Coverage gaps and a root cause of `not_established` remain explicit.
5. **Optionally consult a model.** Model output is separate, unverified and never promoted to an established observation. Humans must check it against the actual sources.

For the fixture schema and integration-test contract, see [TEST_CONTRACT.md](TEST_CONTRACT.md). The fixtures can be regenerated with `python3 build_fixtures.py`; this overwrites the named synthetic fixture files.

## Tests

Install the pinned test dependency, then run the suite:

```bash
python3 -m pip install -r requirements-test.txt
python3 -m pytest -q
```

The suite checks missing evidence, misleading deployment/recovery correlations, an instruction hidden in an attacker-controlled log field, evidence locations and deterministic output. It also uses a local mock provider to test malformed model responses, forged or unsent citations, and the absence of model tools. GitHub Actions runs the suite on Python 3.10 and 3.12.

These tests show behavior on specific cases. They do **not** prove that an LLM is immune to prompt injection or that a valid citation actually supports a model's statement. The raw hostile log remains visible as untrusted evidence in the report's index.

## Optional LLM mode

The model client uses an OpenAI-compatible Chat Completions endpoint. Supply your own provider credentials and model, and explicitly opt in:

```bash
export OPENAI_API_KEY='YOUR_PROVIDER_KEY'
export OPENAI_MODEL='YOUR_CHAT_MODEL'
# Optional; defaults to https://api.openai.com/v1
export OPENAI_BASE_URL='https://api.openai.com/v1'
python3 -m incident_investigator --case fixtures/checkout_throttling --mode llm --output investigation-llm.md
```

`OPENAI_API_BASE` is also accepted if `OPENAI_BASE_URL` is unset. Provider support and charges vary. The client sends selected raw evidence to the configured provider, so use synthetic data unless you have authorization and have reviewed the provider's privacy and retention terms. Never commit credentials. Model runs are nondeterministic and may fail validation; failures do not silently fall back to offline mode.

The model receives no tools. Local validation checks the response schema and that citations refer to evidence actually sent; it does not verify semantic support, prevent all prompt injection, or make untrusted evidence safe. Do not execute instructions from evidence or use the output for automatic remediation.

## Build provenance

This project was developed with Manus AI agents from a human-defined product brief, with an independent adversarial test pass and human-reviewable source files. The optional model integration is OpenAI-compatible; the project does not claim to have been built with Claude Code.
