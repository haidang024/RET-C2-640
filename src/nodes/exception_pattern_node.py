"""ExceptionPatternNode — prior dispute and exception-pattern analysis for RET-C2-640."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import from_json


class ExceptionPatternNode(FunctionNode):
    """Prior dispute and exception-pattern analysis node.

    Maps permitted prior dispute/outcome patterns and documented exception
    references into traceable decision-support evidence. Does NOT infer policy
    or make a grant/denial decision. Preserves citations and marks uncertainty.
    trust_level: ANONYMOUS (inner DomainWorkflowGraph node).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        """Map prior disputes and exception patterns into traceable evidence."""
        loyalty_history: list[dict] = from_json(state.get("loyalty_history_json", ""), default=[])
        applicability_factors: list[dict] = from_json(state.get("applicability_factors_json", ""), default=[])
        dispute_id = state.get("dispute_id", "")
        offer_id = state.get("offer_id", "")

        # Prior disputes are stored in evidence_sources_json provenance
        # (they were retrieved by EvidenceRetrievalNode as part of loyalty_history context)
        # For this node we look for dispute-related entries in loyalty_history
        prior_disputes_from_history: list[dict] = [
            item for item in loyalty_history if item.get("activity_type") in ("dispute", "exception", "correction")
        ]

        exception_factors: list[dict] = []
        prior_outcomes: list[dict] = []
        exception_citations: list[str] = []
        uncertainty_flags: list[str] = []

        # Map exception patterns from prior outcomes
        for dispute_record in prior_disputes_from_history:
            activity_id = dispute_record.get("activity_id", "unknown")
            activity_type = dispute_record.get("activity_type", "")
            occurred_at = dispute_record.get("occurred_at", "")
            source_id = dispute_record.get("source_id", "")
            api_version = dispute_record.get("api_version", "")

            prior_outcomes.append(
                {
                    "activity_id": activity_id,
                    "activity_type": activity_type,
                    "occurred_at": occurred_at,
                    "source_id": source_id,
                    "api_version": api_version,
                    "note": (
                        "Prior outcome record is provided as decision-support context only. "
                        "No policy inference or grant/denial determination is made by this node."
                    ),
                }
            )

            if activity_type == "exception":
                policy_ref = dispute_record.get("policy_ref", "")
                exception_factors.append(
                    {
                        "activity_id": activity_id,
                        "exception_type": "documented_exception",
                        "source_id": source_id,
                        "policy_ref": policy_ref or "unspecified",
                        "citation": f"Exception recorded at {occurred_at} (source: {source_id})",
                    }
                )
                if policy_ref:
                    exception_citations.append(f"Policy ref: {policy_ref} (activity: {activity_id})")

        # Map applicable rule citations from analysis
        for factor in applicability_factors:
            rule_id = factor.get("rule_id", "")
            src = factor.get("source_id", "")
            if rule_id:
                exception_citations.append(f"Rule: {rule_id} (source: {src})")

        # Mark uncertainty when prior disputes are absent
        if not prior_disputes_from_history:
            uncertainty_flags.append(
                "No prior dispute or exception records found — "
                "exception pattern context is unavailable for this offer/customer combination"
            )

        if not applicability_factors:
            uncertainty_flags.append(
                "No applicability factors available — " "exception pattern analysis is limited without rule mapping"
            )

        exception_analysis_complete = bool(prior_disputes_from_history or applicability_factors)

        emit_trace_event(
            "ExceptionPatternNode_analysis_complete",
            {
                "dispute_id": dispute_id,
                "offer_id": offer_id,
                "prior_outcomes_count": len(prior_outcomes),
                "exception_factors_count": len(exception_factors),
                "citations_count": len(exception_citations),
                "uncertainty_flags_count": len(uncertainty_flags),
                "exception_analysis_complete": exception_analysis_complete,
                # No customer data or PII in audit event
            },
            state,
        )

        return {
            "exception_factors_json": json.dumps(exception_factors),
            "prior_outcomes_json": json.dumps(prior_outcomes),
            "exception_citations_json": json.dumps(exception_citations + uncertainty_flags),
            "exception_analysis_complete": exception_analysis_complete,
            "status": AgentStatus.SUCCESS.value,
        }
