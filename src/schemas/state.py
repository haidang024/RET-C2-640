"""State schema — flat TypedDict for RET-C2-640 LoyaltyDisputeResolutionAgent."""

from __future__ import annotations

# ADR-005: State must be a flat TypedDict (msgpack-safe).
# All fields must be str / int / float / bool.
# Structured data is JSON-encoded as str (use to_json/from_json helpers).
# Do NOT add credentials, clients, Pydantic models, or dataclasses.

import json
from typing import Any

from framework.schemas.agent_state import AgentState


def to_json(obj: Any) -> str:
    """Encode a dict/list to a JSON string for msgpack-safe state storage."""
    return json.dumps(obj, ensure_ascii=False)


def from_json(value: str, *, default: Any = None) -> Any:
    """Decode a JSON string from state; return default on empty/invalid."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


class State(AgentState):
    """Flat state for RET-C2-640 Loyalty Dispute Resolution Agent.

    Field ownership:
      PreProcessNode          -> dispute_id, customer_ref, offer_id, dispute_period_start,
                                 dispute_period_end, approved_source_ids, operator_id,
                                 normalized_input
      EvidenceRetrievalNode   -> offer_rules_json, loyalty_history_json,
                                 evidence_sources_json, evidence_retrieved
      OfferRuleAnalysisNode   -> applicability_factors_json, constraints_json,
                                 evidence_gaps_json, analysis_complete
      ExceptionPatternNode    -> exception_factors_json, prior_outcomes_json,
                                 exception_citations_json, exception_analysis_complete
      ResponseDraftNode       -> response_draft, briefing_summary, hitl_draft,
                                 review_disposition, review_notes
      PostProcessNode         -> formatted_output, citations_json,
                                 provenance_json, partial_result
    """

    # Input / dispute criteria (set by PreProcessNode)
    dispute_id: str
    customer_ref: str  # anonymized customer reference (no PII in state)
    offer_id: str
    dispute_period_start: str  # ISO-8601 date string
    dispute_period_end: str  # ISO-8601 date string
    approved_source_ids: str  # JSON-encoded list[str] -- allowlisted source IDs
    operator_id: str  # authorized operator who submitted the dispute
    normalized_input: str  # sanitized/normalized input text

    # Evidence retrieval (set by EvidenceRetrievalNode)
    offer_rules_json: str  # JSON-encoded list[dict] -- normalized offer rules
    loyalty_history_json: str  # JSON-encoded list[dict] -- customer activity records
    evidence_sources_json: str  # JSON-encoded list[dict] -- provenance per source
    evidence_retrieved: bool  # True when at least one source returned data
    retrieval_unavailable: bool  # True only when the connector credential is unavailable

    # Offer rule / eligibility-evidence analysis (set by OfferRuleAnalysisNode)
    applicability_factors_json: str  # JSON-encoded list[dict] -- cited factor/rule pairs
    constraints_json: str  # JSON-encoded list[dict] -- constraint records
    evidence_gaps_json: str  # JSON-encoded list[str] -- missing/ambiguous items
    analysis_complete: bool

    # Exception pattern analysis (set by ExceptionPatternNode)
    exception_factors_json: str  # JSON-encoded list[dict] -- pattern-matched factors
    prior_outcomes_json: str  # JSON-encoded list[dict] -- relevant prior outcomes
    exception_citations_json: str  # JSON-encoded list[str] -- doc/policy references
    exception_analysis_complete: bool

    # Response draft / HITL (set by ResponseDraftNode)
    response_draft: str  # factual CS response draft (NOT sent to customer)
    briefing_summary: str  # operator briefing with evidence summary
    review_disposition: str  # "approved" | "corrected" | "rejected" | ""
    review_notes: str  # human reviewer notes

    # Traceable output (set by PostProcessNode)
    citations_json: str  # JSON-encoded list[dict] -- cited rules/history refs
    provenance_json: str  # JSON-encoded dict -- full retrieval provenance
    partial_result: bool  # True when output is based on partial evidence

    # User-correctable input guidance
    input_error_message: str
    input_error_guidance: str

    # Invocation-scoped provider observability (never contains secret details)
    generation_mode: str
    provider_error_message: str
