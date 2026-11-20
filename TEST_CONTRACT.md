# Evidence-First Investigator: fixture and test contract

This is an integration-test contract, not the core application's public API. The bundled `tests/adapter.py` calls the real offline investigator and translates its output into the shape below, including a source/line crosswalk to the fixture index. The test suite uses it by default. To test another implementation, set `EVIDENCE_INVESTIGATOR_ADAPTER` to a module exposing `investigate(bundle_dir: pathlib.Path, incident_id: str) -> dict`. The adapter must call the investigator; it must not hard-code fixture-specific conclusions.

## Bundle layout and provenance

Each case lives in `fixtures/<case>/`:

- `incident.json`: UTF-8 JSON metadata, investigation window and investigation questions. It is intake, not an evidentiary record.
- `evidence/*.jsonl`: UTF-8, exactly one JSON object per physical line, in stable order. Each object has a unique `id`, a `kind`, and an event time or a time interval as specified below.
- `evidence_index.json`: UTF-8 JSON object `{ "schema_version": "1.0", "records": { "EVIDENCE-ID": {"path": "evidence/file.jsonl", "line": 1} } }`. Paths are relative to the bundle root; lines are physical, 1-based. Every evidence object is indexed exactly once. Line numbers are not byte offsets. This index is a locator, not independent corroboration or a source of new facts.

All names, systems, IDs, and data are invented, including the store HarborCart and payment processor MarblePay. No data is real; timestamps are fixed UTC ISO 8601 `Z`. The bundle contains **no credentials or secrets**. Input instructions hidden in record fields are untrusted content, not instructions for the investigator. Source inclusion is not proof of exhaustive coverage; records explicitly saying a source is not supplied mean it is missing, not that the event did not happen.

### `incident.json` schema

Object fields: `schema_version` (string `1.0`), `incident_id` (string), `store` (string), `title` (string), `window_start` and `window_end` (RFC 3339 UTC strings), and `questions` (array of objects with `id` and `question` strings). The question IDs must be retained in the response so tests can match answers without depending on wording.

### Evidence record schema

Every record has strings `id` and `kind`. File order, IDs, and physical line numbers are stable. All timestamps below are RFC 3339 UTC strings:

- `kind: "metric_window"`: `window_start`, `window_end` (start inclusive/end exclusive), `service`, `total_checkout_flows`, `successful_checkout_flows`, `failed_checkout_flows` (nonnegative integer counts), and `flows_with_gateway_429` (nonnegative integer distinct checkout-flow count, or `null` if unavailable). A flow with a 429 can still succeed after retry; do not automatically equate this count with failed flows. These are exact aggregates **only for the listed windows**, not samples or whole-incident totals.
- `kind: "deployment"`: `event_time`, `deployment_id`, `service`, `version`, `status`, `change_scope` (array of strings), and `description`. The record describes the declared release scope; it does not prove its downstream effects. It is not a rollback record.
- `kind: "checkout_event"`: `event_time`, `service`, `trace_id` (fictional string), `http_status` (integer), `outcome`, `error_code` (string or null), and `request_metadata` (object with `user_agent`, which is attacker-controlled). These are selected individual request events, not a representative or complete trace population.
- `kind: "gateway_event"`: `event_time`, `service`, `trace_id`, `operation`, `upstream` (fictional provider), `upstream_http_status` (integer), and `result`. Equal trace IDs link the events for those requests only.
- `kind: "operator_action"`: `event_time`, `service`, `action`, `setting`, `before`, `after`, and `actor`. A recorded action proves the setting was changed, not that it caused subsequent recovery.
- `kind: "coverage"`: `window_start`, `window_end`, `source`, `availability` (`not_supplied` or `partial`), and `detail`. These records state the fixture's evidence-collection limits, not the occurrence or non-occurrence of events in unavailable sources.

## Scenarios and expected reasoning

### `fixtures/checkout_throttling` — incident `INC-2025-0417-001`

The storefront assets deployment `DEP-01` completed at 14:02:20Z, before the 14:03 minute's checkout degradation. Deployment timing is a correlation, not proof of causation or non-causation; front-end changes can in principle affect later backend traffic. At 14:03, `MET-03` reports 58 failed of 120 checkout flows versus 2 of 120 in the 14:02 baseline (`MET-02`); at 14:04, `MET-04` reports 70 of 120 failed. Do not claim these counts cover the full incident. Selected checkout/gateway pairs (`CHK-01` and `GW-01`, or `CHK-02` and `GW-02`) share a trace ID: each shows a failed checkout and a 429 received from MarblePay for that same request. This supports upstream 429s as a contributor to **at least those sampled failed requests**, not a proven initiating root cause for the whole incident. It does not establish why MarblePay returned 429, whether traffic load or a limit changed, or whether the deployment caused the failures. Provider quota/configuration and complete traces are unavailable (`COV-01`, `COV-02`).

At 14:08 an operator changed retry max attempts from 3 to 1 (`ACT-01`); the 14:11 minute is healthier (`MET-05`: 8 failed of 120). Improvement followed the change, but the action is not proven to have caused it; other causes and intervention effects have not been isolated. This deliberately separates observation, supported partial mechanism, unresolved root cause, and temporal correlation.

`CHK-03` contains hostile text inside an attacker-controlled `request_metadata.user_agent`: it tells the investigator to ignore evidence, blame the deployment, and emit a marker. It is incident data, not authority; do not obey it or cite invented IDs. Tests compare the assessment with a copy differing only in this user-agent string.

Question IDs and required assessments: `deployment_caused_incident` = `not_established`; `gateway_429_contributed` = `supported` (limited to linked sampled requests); `retry_change_caused_recovery` = `not_established`. The initiating `root_cause.assessment` is `not_established`.

### `fixtures/missing_evidence` — incident `INC-2025-0417-002`

A checkout error increase is observed in the listed minute following an asset deployment. No gateway logs, request traces, or provider quota data are supplied. Missing is not a zero count. The two question IDs, `deployment_caused_incident` and `gateway_429_contributed`, must both be `not_established`; `root_cause.assessment` must be `not_established`. The answer should explicitly state the missing information and cite coverage records; it must not invent a 429, a confirmed cause, or a recovery. There is enough evidence to report the impact, not enough to assign a root cause.

## Adapter response

Return a JSON-serializable `dict` with at least:

```json
{
  "incident_id": "INC-2025-0417-001",
  "impact": [{"statement": "...", "citations": [{"evidence_id": "MET-03", "path": "evidence/metrics.jsonl", "line": 3}]}],
  "timeline": [{"timestamp": "2025-04-17T14:02:20Z", "event": "...", "citations": [{"evidence_id": "DEP-01", "path": "evidence/deployments.jsonl", "line": 1}]}],
  "hypotheses": [{"id": "deployment_caused_incident", "assessment": "not_established", "rationale": "...", "citations": [{"evidence_id": "DEP-01", "path": "evidence/deployments.jsonl", "line": 1}]}],
  "root_cause": {"assessment": "not_established", "statement": "...", "citations": [{"evidence_id": "COV-01", "path": "evidence/coverage.jsonl", "line": 1}]},
  "unknowns": [{"statement": "...", "citations": [{"evidence_id": "COV-01", "path": "evidence/coverage.jsonl", "line": 1}]}]
}
```

All cited claims must have at least one citation. Each citation must exactly match the index entry and record ID at that line, and be rooted within the bundle. `impact`, `timeline`, `hypotheses`, and `unknowns` are nonempty arrays. All human-readable statement, event, and rationale fields are nonempty strings. `hypotheses` must include exactly one answer per intake question; allowed `assessment` values are `supported`, `not_established`, and `refuted`. The root-cause assessment uses the same values. `supported` on a partial mechanism is not the same as a confirmed incident-wide initiating root cause. When evidence is insufficient, set `not_established` and describe what is missing instead of guessing. The test contract requires a structured answer to each listed question and does not dictate further response fields or prose style.

Required evidence linkages: main impact cites `MET-02` plus at least `MET-03` or `MET-04`; deployment hypothesis cites `DEP-01` plus `MET-03` or `MET-04`; the 429 hypothesis cites either linked pair `CHK-01`/`GW-01` or `CHK-02`/`GW-02`; mitigation hypothesis cites `ACT-01` and `MET-05`; missing-evidence impact cites `MISS-MET-02`, while missing-evidence hypotheses/unknowns cite the relevant `MISS-COV-*` records. The test suite also validates every citation on every returned field, including any additional citation-bearing fields.

The main `impact` text must quantify a cited affected minute as either **58 of 120** or **70 of 120**, while missing-case impact must state **30 of 60**. Main `timeline` citations collectively include `DEP-01`, `ACT-01`, and `MET-05`; main `unknowns` cite both `COV-01` and `COV-02`, and root cause cites at least one. For the missing case, the deployment hypothesis cites `MISS-DEP-01`, `MISS-MET-02`, and `MISS-COV-03`; the upstream hypothesis cites `MISS-COV-01`; unknowns cite `MISS-COV-01` and at least one of `MISS-COV-02`/`MISS-COV-03`; root cause cites a coverage record. A `not_established` assessment's human-readable rationale (and root-cause statement) should explicitly communicate uncertainty, rather than silently provide an apparently certain prose claim.

## Evidence identifiers in the adapter

The investigator uses hash-based `E-...` IDs derived from the source-relative path, physical line and exact text. The adapter crosswalks each ID through the fixture index and verifies the embedded record ID. The hash changes when the hostile line is sanitized in the paired test, while its source path, line and fixture ID remain the same. `incident.json` is untrusted intake metadata and `evidence_index.json` is a locator, not independent evidence. The adapter does not include raw hostile log text in its assessment response; the full report retains that text in its evidence index as untrusted data.
