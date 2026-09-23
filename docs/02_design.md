# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: LoyaltyDisputeResolutionAgent (`Graph` in `src/graph/graph.py`)
- **L1 Base**: AgentBaseGraph (outer) + BaseGraph (inner `LoyaltyDisputeWorkflowGraph`)
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

### Node Configuration

| Node | Responsibility | Trust Level | Inherits |
|------|---------------|-------------|---------|
| `pre_process` | Dispute criteria validation, source allowlist enforcement | VERIFIED_EXTERNAL | FunctionNode |
| `main` (`LoyaltyDisputeGraphNode`) | Inner workflow orchestration and LLM/config propagation | VERIFIED_EXTERNAL | GraphNode |
| `evidence_retrieval` | Approved-source evidence fetch with provenance | ANONYMOUS | FunctionNode |
| `offer_rule_analysis` | Offer rule → applicability factor mapping | ANONYMOUS | FunctionNode |
| `exception_pattern` | Exception/prior-dispute pattern mapping | ANONYMOUS | FunctionNode |
| `response_draft` | HITL-gated draft composition | ANONYMOUS | FunctionNode |
| `post_process` | Traceable formatted output assembly | VERIFIED_EXTERNAL | FunctionNode |

### Data Flow

```
START → pre_process → main ─────────────────────────────────── → post_process → END
                       │                                         ↑
                       └→ [inner: LoyaltyDisputeWorkflowGraph]──┘
                            evidence_retrieval → offer_rule_analysis
                            → exception_pattern → response_draft [HITL interrupt]
                            (retrieval/analysis errors → END with ERROR status)
```

HITL flow (when `hitl_allowed=True` and `hitl_draft == ""`):
```
response_draft → interrupt() → [human reviewer] → resume with review_disposition
→ approved: SUCCESS + draft intact
→ corrected: SUCCESS + draft replaced by review_notes
→ rejected:  ERROR + error_log
```

### State Definition

| Field | Type | Owner Node | Purpose |
|-------|------|-----------|---------|
| `dispute_id` | str | PreProcessNode | Validated dispute reference |
| `customer_ref` | str | PreProcessNode | Customer reference (PII-minimized in audit) |
| `offer_id` | str | PreProcessNode | Offer being disputed |
| `dispute_period_start` | str | PreProcessNode | ISO-8601 date — period start |
| `dispute_period_end` | str | PreProcessNode | ISO-8601 date — period end |
| `operator_id` | str | PreProcessNode | Operator who submitted the request |
| `approved_source_ids` | str | PreProcessNode | JSON-encoded `list[str]` from allowlist |
| `normalized_input` | str | PreProcessNode | Validated JSON input |
| `offer_rules_json` | str | EvidenceRetrievalNode | JSON-encoded offer rule records |
| `loyalty_history_json` | str | EvidenceRetrievalNode | JSON-encoded loyalty activity records |
| `evidence_sources_json` | str | EvidenceRetrievalNode | JSON-encoded per-source provenance |
| `evidence_retrieved` | bool | EvidenceRetrievalNode | True when ≥1 source returned data |
| `retrieval_unavailable` | bool | EvidenceRetrievalNode | True when standalone execution has no connector credential |
| `applicability_factors_json` | str | OfferRuleAnalysisNode | JSON-encoded rule-to-factor mapping |
| `constraints_json` | str | OfferRuleAnalysisNode | JSON-encoded rule constraints |
| `evidence_gaps_json` | str | OfferRuleAnalysisNode | JSON-encoded missing evidence list |
| `analysis_complete` | bool | OfferRuleAnalysisNode | True when both rules + history present |
| `exception_factors_json` | str | ExceptionPatternNode | JSON-encoded exception pattern records |
| `prior_outcomes_json` | str | ExceptionPatternNode | JSON-encoded prior dispute outcomes |
| `exception_citations_json` | str | ExceptionPatternNode | JSON-encoded rule citation strings |
| `exception_analysis_complete` | bool | ExceptionPatternNode | Always True on SUCCESS |
| `response_draft` | str | ResponseDraftNode | Human-reviewed response text |
| `briefing_summary` | str | ResponseDraftNode | One-line dispute briefing |
| `hitl_draft` | str | ResponseDraftNode | Idempotency key for HITL interrupt |
| `review_disposition` | str | ResponseDraftNode | "approved" / "corrected" / "rejected" / "" |
| `review_notes` | str | ResponseDraftNode | Reviewer corrections or rejection reason |
| `formatted_output` | str | PostProcessNode | Final traceable operator output |
| `citations_json` | str | PostProcessNode | JSON-encoded full citation list |
| `provenance_json` | str | PostProcessNode | JSON-encoded provenance record |
| `partial_result` | bool | PostProcessNode | True when analysis or evidence incomplete |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext inside nodes via `InvocationContext.from_state(state)` only (not stored as an object in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)
- Structured data (lists, dicts) JSON-encoded as `str` via `to_json()`/`from_json()`

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, caller_trust_level, secrets)
- [x] SecurityViolationError (`_extra_security_gate_input` in PreProcessNode; `_extra_security_gate_output` in PostProcessNode)
- [x] S-2: `_extra_security_gate_input()` in PreProcessNode — rejects inputs > 8192 chars
- [x] S-3: `_extra_security_gate_output()` in PostProcessNode — rejects credential patterns in output
- [x] S-4: `emit_trace_event()` — domain event per `execute()` in all 5 business nodes
- [x] HITL: `interrupt()` from `langgraph.types` — D6 pattern in ResponseDraftNode
- [x] Optional LLM injection: server constructs the client once; `Graph` passes
  `self.config.get("llm")` to `LoyaltyDisputeGraphNode`, which passes the same object to
  `ResponseDraftNode`. Deterministic generation intentionally does not call it.

### Composition Pattern

- **Outer**: `AgentBaseGraph` subclass (`Graph`) with `pre_process → main → post_process`
- **Inner**: `BaseGraph` subclass (`LoyaltyDisputeWorkflowGraph`) registered in `main` slot via `LoyaltyDisputeGraphNode(GraphNode)`
- **Error propagation strategy**: `propagate` (inner errors surface to outer caller)
- **HITL propagation**: `propagate_hitl=True` on `LoyaltyDisputeGraphNode` (GraphInterrupt surfaces to outer caller)
- **Checkpointing**: the main wrapper lazily creates one inner graph and compiles it with a
  persistent `MemorySaver` while HITL is enabled. This preserves the inner thread across the
  outer interrupt/resume boundary.
- **Credential-unavailable behavior**: standalone keyless invocation returns a cited,
  explicitly incomplete draft for human review; it never fabricates retrieved evidence.

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework.*`, `shared.*`, `langgraph.*`, own `src.*` only

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Fixed pipeline; no autonomous loop needed |
| Composition pattern | Flat 3-node (Cat 1) | GraphNode inner (Cat 2) | GraphNode inner | 4 distinct business steps require inner orchestration |
| HITL placement | Post-analysis interrupt | No HITL | Post-draft interrupt | Dispute response requires human review before output |
| Partial failure | Fail all on any error | Allow partial evidence | Allow partial | Individual source failures should not block available evidence |
| Source allowlist | Runtime config | Hardcoded | Both: validated against `APPROVED_SOURCES` constant | Operator can request subset; server enforces against constant |
| Decision boundary | Agent decides eligibility | Decision-support only | Decision-support only | Mandatory: agent must not determine eligibility or mutate accounts |
| Generation path | LLM-generated draft | Deterministic evidence draft | Deterministic evidence draft | Manifest declares deterministic mode; injection remains compatible with the shared server pattern |

## EU AI Act Art.13 Design-Time Evidence

Not applicable because `docs/01_proposal.md` declares this intended purpose outside Annex III.
The operator-facing limitations, evidence gaps, citations, and HITL review are retained as
good transparency and oversight controls.
