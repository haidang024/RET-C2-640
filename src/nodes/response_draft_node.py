"""ResponseDraftNode — CS response draft composition and HITL review for RET-C2-640."""

from __future__ import annotations

from typing import ClassVar

from langgraph.types import interrupt

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import from_json

# HITL resume dispositions
_APPROVED = "approved"
_CORRECTED = "corrected"
_REJECTED = "rejected"


class ResponseDraftNode(FunctionNode):
    """Customer-service response draft composition and HITL review node.

    Synthesizes evidence into a factual CS response draft and briefing for
    authorized human review. Uses D6 interrupt() only when hitl_allowed is True.
    Handles approved/corrected/rejected HITL outcomes idempotently.
    Does NOT send messages, change accounts, or grant/revoke rewards.
    trust_level: ANONYMOUS (inner DomainWorkflowGraph node).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: object | None = None) -> None:
        super().__init__()
        self._llm = llm

    def execute(self, state: dict) -> dict:
        """Compose response draft and interrupt for human review."""
        dispute_id = state.get("dispute_id", "")
        offer_id = state.get("offer_id", "")
        operator_id = state.get("operator_id", "")
        analysis_complete = state.get("analysis_complete", False)
        exception_analysis_complete = state.get("exception_analysis_complete", False)
        evidence_retrieved = state.get("evidence_retrieved", False)

        applicability_factors: list[dict] = from_json(state.get("applicability_factors_json", ""), default=[])
        constraints: list[dict] = from_json(state.get("constraints_json", ""), default=[])
        evidence_gaps: list[str] = from_json(state.get("evidence_gaps_json", ""), default=[])
        exception_factors: list[dict] = from_json(state.get("exception_factors_json", ""), default=[])
        exception_citations: list[str] = from_json(state.get("exception_citations_json", ""), default=[])
        prior_outcomes: list[dict] = from_json(state.get("prior_outcomes_json", ""), default=[])

        # Check if already reviewed (idempotency via hitl_draft key)
        existing_disposition = state.get("review_disposition", "")
        hitl_draft_key = state.get("hitl_draft", "")

        # If this is a HITL resume, handle disposition
        if existing_disposition in (_APPROVED, _CORRECTED, _REJECTED) and hitl_draft_key:
            return self._handle_review_outcome(state, existing_disposition)

        # Compose factual evidence summary (decision-support only — no eligibility ruling)
        evidence_summary_parts: list[str] = []

        evidence_summary_parts.append(f"Dispute ID: {dispute_id} | Offer: {offer_id} | Operator: {operator_id}")
        evidence_summary_parts.append(
            f"Evidence status: retrieved={evidence_retrieved}, "
            f"analysis_complete={analysis_complete}, "
            f"exception_analysis_complete={exception_analysis_complete}"
        )

        if applicability_factors:
            evidence_summary_parts.append(f"Applicability factors ({len(applicability_factors)} rules mapped):")
            for factor in applicability_factors[:5]:  # bounded display
                evidence_summary_parts.append(
                    f"  - Rule {factor.get('rule_id', 'N/A')}: {factor.get('description', '')[:120]}"
                )

        if constraints:
            evidence_summary_parts.append(f"Rule constraints ({len(constraints)}):")
            for c in constraints[:3]:
                evidence_summary_parts.append(f"  - {c.get('rule_id', 'N/A')}: {c.get('constraint_text', '')[:80]}")

        if evidence_gaps:
            evidence_summary_parts.append(f"Evidence gaps ({len(evidence_gaps)}):")
            for gap in evidence_gaps[:3]:
                evidence_summary_parts.append(f"  - {gap[:120]}")

        if exception_factors:
            evidence_summary_parts.append(f"Exception patterns found ({len(exception_factors)}) — see citations")

        if prior_outcomes:
            evidence_summary_parts.append(f"Prior outcomes on record: {len(prior_outcomes)}")

        briefing_summary = "\n".join(evidence_summary_parts)

        # Compose factual response draft (NOT a eligibility decision, NOT sent to customer)
        draft_parts: list[str] = [
            "=== CUSTOMER SERVICE RESPONSE DRAFT — FOR AUTHORIZED HUMAN REVIEW ONLY ===",
            "",
            "This draft summarizes available evidence for dispute resolution. "
            "Eligibility determination and reward decisions are reserved for authorized personnel.",
            "",
            f"Regarding your dispute (Reference: {dispute_id}):",
            "",
            "We have reviewed the loyalty program offer terms and your activity records " "for the dispute period.",
        ]

        if applicability_factors:
            draft_parts.append(
                f"\nOur records show {len(applicability_factors)} applicable offer rule(s) "
                "on file for this offer. Details are available in the full evidence summary."
            )

        if evidence_gaps:
            draft_parts.append(
                "\nNote: The following information could not be confirmed at this time: " + "; ".join(evidence_gaps[:2])
            )

        draft_parts.extend(
            [
                "",
                "[DRAFT — Pending authorized human review before any response is issued]",
                "[No eligibility decision, reward grant/revocation, or account change has been made]",
            ]
        )

        response_draft = "\n".join(draft_parts)
        draft_key = f"DRAFT-{dispute_id}-{offer_id}"

        emit_trace_event(
            "ResponseDraftNode_draft_composed",
            {
                "dispute_id": dispute_id,
                "offer_id": offer_id,
                "factors_count": len(applicability_factors),
                "gaps_count": len(evidence_gaps),
                "exception_factors_count": len(exception_factors),
                "citations_count": len(exception_citations),
                # No customer data or draft content in audit event
            },
            state,
        )

        # D6 HITL interrupt — guarded by hitl_allowed to prevent deadlock.
        # The current generation mode is deterministic, so the injected LLM is
        # intentionally not called when composing this evidence-grounded draft.
        if state.get("hitl_allowed", True):
            feedback = interrupt(
                {
                    "type": "human_review_required",
                    "dispute_id": dispute_id,
                    "offer_id": offer_id,
                    "briefing": briefing_summary,
                    "draft": response_draft,
                    "citations": exception_citations,
                    "instructions": (
                        "Review evidence and draft. Set review_disposition to "
                        "'approved', 'corrected' (with review_notes), or 'rejected'."
                    ),
                }
            )
            feedback_data = feedback if isinstance(feedback, dict) else {}
            resumed_state = {
                **state,
                "response_draft": response_draft,
                "briefing_summary": briefing_summary,
                "hitl_draft": draft_key,
                "review_disposition": str(feedback_data.get("review_disposition", "")),
                "review_notes": str(feedback_data.get("review_notes", "")),
            }
            return self._handle_review_outcome(
                resumed_state,
                resumed_state["review_disposition"],
            )

        # hitl_allowed=False: return draft without interrupting (no deadlock)
        emit_trace_event(
            "ResponseDraftNode_hitl_skipped",
            {"dispute_id": dispute_id, "reason": "hitl_allowed_false"},
            state,
        )
        return {
            "response_draft": response_draft,
            "briefing_summary": briefing_summary,
            "hitl_draft": draft_key,
            "review_disposition": "",
            "review_notes": "HITL skipped (hitl_allowed=False)",
            "status": AgentStatus.SUCCESS.value,
        }

    def _handle_review_outcome(self, state: dict, disposition: str) -> dict:
        """Handle the human review outcome after HITL resume."""
        dispute_id = state.get("dispute_id", "")
        review_notes = state.get("review_notes", "")
        response_draft = state.get("response_draft", "")
        briefing_summary = state.get("briefing_summary", "")
        hitl_draft = state.get("hitl_draft", f"DRAFT-{dispute_id}")

        if disposition == _REJECTED:
            emit_trace_event(
                "ResponseDraftNode_review_rejected",
                {"dispute_id": dispute_id},
                state,
            )
            return {
                "response_draft": response_draft,
                "briefing_summary": briefing_summary,
                "hitl_draft": hitl_draft,
                "review_disposition": _REJECTED,
                "review_notes": review_notes,
                "status": AgentStatus.ERROR.value,
                "error_log": [f"ResponseDraftNode: human reviewer rejected the draft — {review_notes}"],
            }

        if disposition == _CORRECTED:
            corrected_draft = review_notes or response_draft
            emit_trace_event(
                "ResponseDraftNode_review_corrected",
                {"dispute_id": dispute_id},
                state,
            )
            return {
                "response_draft": corrected_draft,
                "briefing_summary": briefing_summary,
                "hitl_draft": hitl_draft,
                "review_disposition": _CORRECTED,
                "review_notes": review_notes,
                "status": AgentStatus.SUCCESS.value,
            }

        # Default: approved or empty (treat as approved in resume)
        emit_trace_event(
            "ResponseDraftNode_review_approved",
            {"dispute_id": dispute_id},
            state,
        )
        return {
            "response_draft": response_draft,
            "briefing_summary": briefing_summary,
            "hitl_draft": hitl_draft,
            "review_disposition": _APPROVED,
            "review_notes": review_notes,
            "status": AgentStatus.SUCCESS.value,
        }
