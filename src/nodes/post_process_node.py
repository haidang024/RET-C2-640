"""PostProcessNode — traceable output post-processing for RET-C2-640."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import from_json
from src.services.llm_runtime import provider_metadata, request_advisory

# Prohibited patterns in output: no raw credentials or API keys
import re

_API_KEY_RE = re.compile(r"(?:api[_-]?key|bearer|authorization)\s*[:=]\s*\S{10,}", re.IGNORECASE)


class PostProcessNode(FunctionNode):
    """Traceable output post-processing node.

    Produces response draft, evidence summary, cited rules/history, review
    disposition, limitations, and partial-result messaging. Preserves verifiable
    provenance. No eligibility decisions, reward changes, or customer communications.
    trust_level: VERIFIED_EXTERNAL (outer boundary node).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: object | None = None, config: dict | None = None) -> None:
        super().__init__()
        self._llm = llm
        self._config = config or {}

    def _extra_security_gate_output(self, result: dict) -> dict:
        """S-3 domain output gate — ensure no raw credentials in output."""
        output = result.get("formatted_output", "")
        if isinstance(output, str) and _API_KEY_RE.search(output):
            raise SecurityViolationError("PostProcessNode: credential pattern detected in output")
        return result

    def execute(self, state: dict) -> dict:
        """Produce final traceable output with evidence citations and provenance."""
        if state.get("input_error_message"):
            message = str(state["input_error_message"])
            return {
                "formatted_output": message,
                "status": AgentStatus.SUCCESS.value,
                "input_error_message": message,
            }
        dispute_id = state.get("dispute_id", "")
        offer_id = state.get("offer_id", "")
        operator_id = state.get("operator_id", "")
        response_draft = state.get("response_draft", "")
        briefing_summary = state.get("briefing_summary", "")
        review_disposition = state.get("review_disposition", "")
        review_notes = state.get("review_notes", "")
        analysis_complete = state.get("analysis_complete", False)
        exception_analysis_complete = state.get("exception_analysis_complete", False)
        evidence_retrieved = state.get("evidence_retrieved", False)

        applicability_factors: list[dict] = from_json(state.get("applicability_factors_json", ""), default=[])
        evidence_gaps: list[str] = from_json(state.get("evidence_gaps_json", ""), default=[])
        exception_citations: list[str] = from_json(state.get("exception_citations_json", ""), default=[])
        prior_outcomes: list[dict] = from_json(state.get("prior_outcomes_json", ""), default=[])
        evidence_sources: list[dict] = from_json(state.get("evidence_sources_json", ""), default=[])

        partial_result = not (analysis_complete and evidence_retrieved)

        # Build citations list (rules + history references)
        citations: list[dict] = []
        for factor in applicability_factors:
            citations.append(
                {
                    "type": "offer_rule",
                    "rule_id": factor.get("rule_id", ""),
                    "source_id": factor.get("source_id", ""),
                    "api_version": factor.get("api_version", ""),
                }
            )
        for outcome in prior_outcomes[:5]:
            citations.append(
                {
                    "type": "prior_outcome",
                    "activity_id": outcome.get("activity_id", ""),
                    "source_id": outcome.get("source_id", ""),
                    "api_version": outcome.get("api_version", ""),
                }
            )

        # Build provenance record
        provenance = {
            "dispute_id": dispute_id,
            "offer_id": offer_id,
            "sources": evidence_sources,
            "analysis_complete": analysis_complete,
            "exception_analysis_complete": exception_analysis_complete,
            "partial_result": partial_result,
            "review_disposition": review_disposition,
        }

        # Compose final formatted output
        output_parts: list[str] = [
            "=== LOYALTY DISPUTE RESOLUTION — DECISION-SUPPORT OUTPUT ===",
            "",
            f"Dispute Reference: {dispute_id}",
            f"Offer: {offer_id}",
            f"Operator: {operator_id}",
            f"Review Disposition: {review_disposition or 'pending'}",
            "",
        ]

        if partial_result:
            output_parts.append(
                "NOTE: This output is based on partial evidence. "
                "Some sources did not return data. See evidence gaps for details."
            )
            output_parts.append("")

        output_parts.append("--- RESPONSE DRAFT (HUMAN-REVIEWED) ---")
        output_parts.append(response_draft or "[No draft available]")
        output_parts.append("")

        output_parts.append("--- EVIDENCE SUMMARY ---")
        output_parts.append(briefing_summary or "[No briefing available]")
        output_parts.append("")

        if evidence_gaps:
            output_parts.append(f"Evidence Gaps ({len(evidence_gaps)}):")
            for gap in evidence_gaps:
                output_parts.append(f"  - {gap}")
            output_parts.append("")

        if exception_citations:
            output_parts.append(f"Citations ({len(exception_citations)}):")
            for cite in exception_citations[:10]:
                output_parts.append(f"  - {cite}")
            output_parts.append("")

        output_parts.extend(
            [
                "--- LIMITATIONS ---",
                "This output is decision-support only. The agent does not:",
                "  - Determine eligibility or grant/revoke loyalty rewards",
                "  - Modify customer accounts or subscription records",
                "  - Send communications to the customer",
                "All eligibility and reward decisions require authorized human action.",
            ]
        )

        if review_notes:
            output_parts.append(f"\nReviewer Notes: {review_notes}")

        formatted_output = "\n".join(output_parts)

        request_advisory(
            state,
            "Review the safety and clarity of a deterministic loyalty dispute decision-support response.",
            self._llm,
            timeout_s=float(self._config.get("timeout_s", 30)),
            max_retry=int(self._config.get("max_retry", 3)),
        )

        emit_trace_event(
            "PostProcessNode_output_produced",
            {
                "dispute_id": dispute_id,
                "offer_id": offer_id,
                "operator_id": operator_id,
                "review_disposition": review_disposition,
                "citations_count": len(citations),
                "partial_result": partial_result,
                "analysis_complete": analysis_complete,
            },
            state,
        )

        return {
            "formatted_output": formatted_output,
            "citations_json": json.dumps(citations),
            "provenance_json": json.dumps(provenance),
            "partial_result": partial_result,
            "status": AgentStatus.SUCCESS.value,
            **provider_metadata(state),
        }
