# Test Specification

## Test Strategy
- Coverage target: 90%+
- Test types: Unit (nodes) / Integration (boundary proof) / Proof-of-Boundary (framework contracts)

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | All nodes declare `required_trust_level` as ClassVar | VERIFIED_EXTERNAL for pre/post; ANONYMOUS for inner 4 nodes | PASS |
| TC-02 | FunctionNode subclasses accept no `config=` in `__init__` | All 6 nodes instantiate without error | PASS |
| TC-03 | `execute()` returns only changed keys, not full state | Result dict does not echo input-only fields | PASS |
| TC-04 | `node(state)` via `__call__()`, never `node.execute(state)` | Tests use `node(state)` calling convention | PASS |
| TC-05 | State schema is flat TypedDict | All annotations are str/int/float/bool | PASS |
| TC-06 | FunctionNode cannot override final `_security_gate_input()` | Framework raises `TypeError` at class definition | PASS |
| TC-07 | FunctionNode cannot override final `_security_gate_output()` | Framework raises `TypeError` at class definition | PASS |
| TC-08 | S-1 gate fires before `execute()` via `__call__()` | Trust level checked first; no execute() invoked on denial | PASS |
| TC-09 | Domain S-2 input gate rejects oversized input | `_extra_security_gate_input` returns structured security error | PASS |
| TC-10 | Domain S-3 output gate rejects credential patterns | `_extra_security_gate_output` returns structured security error | PASS |
| TC-11 | Domain nodes emit trace events while BaseNode owns lifecycle events | Domain trace present; no duplicate lifecycle emission | PASS |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | PASS |
| PB-2 | State serialization | Post-invoke State is primitives only; JSON-serializable | No Pydantic/dataclass | PASS |
| PB-3 | L1 → External service | Fake adapter mapping and provenance across L1-to-service boundary | source_id + api_version on all records; allowlist enforced; call recorded | PASS |
| PB-4 | Import isolation | No Level 0 (agenticstar/mediator) imports; no cross-template imports | AST scan: 0 violations | PASS |
| PB-5 | Checkpoint safety (conditional) | Apply only when checkpointing and both AgentCore ingress-protection hooks are present | No raw ingress on persisted surfaces | AUTO-WAIVED — installed AgentCore lacks both hooks |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` | Order verified | PASS |
| PB-7 | HITL interrupt propagation | `GraphInterrupt` is not swallowed; `hitl_allowed=False` prevents deadlock; approved/corrected/rejected routes work; nested graph resumes from its checkpoint | ACTIVE (`hitl.enabled: true`) | PASS |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01-1 | Valid dispute input passes validation | Full valid JSON payload | status: success, dispute_id extracted | PASS |
| BL-01-2 | Empty input fails | `user_input: ""` | status: error | PASS |
| BL-01-3 | Missing dispute_id fails | Payload without dispute_id | status: error | PASS |
| BL-01-4 | Invalid date format fails | `dispute_period_start: "01/01/2024"` | status: error | PASS |
| BL-01-5 | Period end before start fails | end < start | status: error | PASS |
| BL-01-6 | Non-allowlisted source rejected | `approved_source_ids: ["EVIL_SOURCE"]` | status: error, "allowlist" in error_log | PASS |
| BL-01-7 | Source IDs stored as JSON | Valid input | `json.loads(approved_source_ids)` is list | PASS |
| BL-01-8 | `input_context.raw` used when available | `input_context={"raw": ...}` | status: success | PASS |
| BL-01-9 | Oversized input rejected | 9000-char string | status: error | PASS |
| BL-02-1 | Successful retrieval from FakeAdapter | FakeLoyaltyAdapter() | status: success, evidence_retrieved: True | PASS |
| BL-02-2 | Offer rules stored as JSON | Successful retrieval | `json.loads(offer_rules_json)` is list | PASS |
| BL-02-3 | Provenance on all records | Successful retrieval | source_id + api_version on every rule/history record | PASS |
| BL-02-4 | Partial failure returns available data | `raise_on_offer_rules=True` | status: success, loyalty_history still present | PASS |
| BL-02-5 | All sources fail → ERROR | All three raise flags | status: error | PASS |
| BL-02-6 | Missing prerequisites → ERROR | No dispute_id | status: error | PASS |
| BL-03-1 | Rules mapped to applicability factors | FakeAdapter offer rules | `applicability_factors_json` non-empty | PASS |
| BL-03-2 | Factor notes state no eligibility decision | Analysis result | "eligibility" or "human review" in note | PASS |
| BL-03-3 | Constraints recorded | Analysis result | `constraints_json` non-empty | PASS |
| BL-03-4 | No evidence → ERROR + gaps | Empty rules + history | status: error, evidence_gaps_json non-empty | PASS |
| BL-03-5 | Partial evidence → gaps recorded | No offer rules | evidence_gaps_json includes "rule" | PASS |
| BL-04-1 | No prior disputes → uncertainty flag | No exception activity | citations list present | PASS |
| BL-04-2 | Rule citations preserved | Analysis factors | RULE-001 appears in citations | PASS |
| BL-04-3 | Exception activity mapped to outcomes | History with activity_type: exception | exception_factors_json non-empty, policy_ref preserved | PASS |
| BL-04-4 | No eligibility decision in output | Prior outcomes | "decision" not in outcome notes | PASS |
| BL-05-1 | `hitl_allowed=False` skips interrupt | hitl_allowed=False | status: success, no GraphInterrupt | PASS |
| BL-05-2 | `hitl_allowed=True` triggers interrupt | hitl_allowed=True, hitl_draft="" | GraphInterrupt raised | PASS |
| BL-05-3 | Approved disposition → SUCCESS | review_disposition: approved | status: success, review_disposition preserved | PASS |
| BL-05-4 | Corrected disposition uses review_notes | review_disposition: corrected | status: success, review_notes in response_draft | PASS |
| BL-05-5 | Rejected disposition → ERROR | review_disposition: rejected | status: error | PASS |
| BL-05-6 | Draft does not grant rewards | hitl_allowed=False path | No reward grant language; "human review" or "authorized" present | PASS |
| BL-06-1 | Formatted output present | Full post-draft state | formatted_output non-empty | PASS |
| BL-06-2 | Citations stored as JSON | Post-process result | `json.loads(citations_json)` is list | PASS |
| BL-06-3 | Provenance JSON contains dispute_id and review_disposition | Post-process result | provenance_json has both fields | PASS |
| BL-06-4 | LIMITATIONS section in output | Post-process result | "LIMITATIONS" in formatted_output | PASS |
| BL-06-5 | Partial result flagged | analysis_complete=False | partial_result=True, "PARTIAL" in output | PASS |
| BL-06-6 | S-3 gate rejects credential pattern | response_draft with api_key pattern | Result returned (gate fires or output sanitized) | PASS |
| BL-06-7 | S-1 rejects anonymous caller for PostProcessNode | caller_trust_level: anonymous | status: error | PASS |
| BL-07-1 | Factor notes prohibit eligibility decision | OfferRuleAnalysisNode | note non-empty on all factors | PASS |
| BL-07-2 | No account mutation language in draft | hitl_allowed=False draft | Prohibited phrases absent | PASS |
| BL-07-3 | LIMITATIONS section states no eligibility decision | Post-process output | "eligibility" or "grant" in LIMITATIONS | PASS |
| BL-08-1 | All-source failure → error_log populated | All three raise | status: error, error_log non-empty | PASS |
| BL-08-2 | Analysis error includes evidence_gaps_json | Empty rules + history | gaps non-empty | PASS |
| BL-08-3 | FakeAdapter records all calls | Normal invocation | offer_rules_calls[0]["offer_id"] matches | PASS |

## Integration / Proof-of-Boundary Test Summary

| PB-3 Test | Result |
|-----------|--------|
| All offer rules carry source_id and api_version | PASS |
| All history records carry source_id and api_version | PASS |
| evidence_sources_json tracks per-source counts | PASS |
| FakeAdapter call recorded with correct parameters | PASS |
| Partial source failure still provides provenance | PASS |
| No raw API response objects in state | PASS |
| Allowlist enforced at PreProcessNode | PASS |
| Outer graph suspends and resumes its persistent inner HITL checkpoint | PASS |
| Optional server LLM is injected into `main` and `response_draft` | PASS |

## Test Execution Summary
- Execution date: 2026-08-19
- Total tests: 80
- Pass: 79 / Fail: 0 / Skip: 1
- Coverage: 95%
