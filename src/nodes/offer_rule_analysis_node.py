"""OfferRuleAnalysisNode — offer rule and eligibility-evidence analysis for RET-C2-640."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import from_json


class OfferRuleAnalysisNode(FunctionNode):
    """Offer rule and eligibility-evidence analysis node.

    Maps normalized offer rules and customer activity evidence into cited
    applicability factors and constraints. Does NOT decide eligibility or
    reward entitlement. Marks missing/ambiguous evidence explicitly.
    Returns safe partial output when evidence is incomplete.
    trust_level: ANONYMOUS (inner DomainWorkflowGraph node).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict) -> dict:
        """Map offer rules and loyalty history into applicability factors."""
        offer_rules: list[dict] = from_json(state.get("offer_rules_json", ""), default=[])
        loyalty_history: list[dict] = from_json(state.get("loyalty_history_json", ""), default=[])
        dispute_id = state.get("dispute_id", "")
        offer_id = state.get("offer_id", "")

        if not offer_rules and not loyalty_history:
            emit_trace_event(
                "OfferRuleAnalysisNode_insufficient_evidence",
                {"dispute_id": dispute_id, "offer_id": offer_id},
                state,
            )
            result = {
                "applicability_factors_json": json.dumps([]),
                "constraints_json": json.dumps([]),
                "evidence_gaps_json": json.dumps(
                    [
                        "No offer rules retrieved — cannot evaluate applicability conditions",
                        "No loyalty history retrieved — cannot verify qualifying activity",
                    ]
                ),
                "analysis_complete": False,
            }
            if state.get("retrieval_unavailable", False):
                return {**result, "status": AgentStatus.SUCCESS.value}
            return {
                **result,
                "status": AgentStatus.ERROR.value,
                "error_log": ["OfferRuleAnalysisNode: insufficient evidence to perform analysis"],
            }

        applicability_factors: list[dict] = []
        constraints: list[dict] = []
        evidence_gaps: list[str] = []

        # Map offer rules to applicability factors (no eligibility decision)
        for rule in offer_rules:
            rule_id = rule.get("rule_id", "unknown")
            description = rule.get("description", "")
            condition = rule.get("condition", "")
            source_id = rule.get("source_id", "")
            api_version = rule.get("api_version", "")

            # Check if any activity satisfies the condition (structural mapping only)
            matching_activities = [a for a in loyalty_history if a.get("activity_type") == "purchase"]

            applicability_factors.append(
                {
                    "rule_id": rule_id,
                    "description": description,
                    "condition": condition,
                    "source_id": source_id,
                    "api_version": api_version,
                    "matching_activity_count": len(matching_activities),
                    "note": (
                        "Matching activity count is structural evidence only. "
                        "Eligibility determination is reserved for authorized human review."
                    ),
                }
            )

            # Record constraint if condition is present
            if condition:
                constraints.append(
                    {
                        "rule_id": rule_id,
                        "constraint_text": condition,
                        "source_id": source_id,
                    }
                )

        # Identify evidence gaps
        if not offer_rules:
            evidence_gaps.append("No offer rules found — applicability cannot be assessed")
        if not loyalty_history:
            evidence_gaps.append("No loyalty activity history found for the dispute period")

        # Flag any activities without matching rules
        if loyalty_history and not offer_rules:
            evidence_gaps.append("Activity history present but no rules to map against")

        analysis_complete = bool(offer_rules and loyalty_history)

        emit_trace_event(
            "OfferRuleAnalysisNode_analysis_complete",
            {
                "dispute_id": dispute_id,
                "offer_id": offer_id,
                "factors_count": len(applicability_factors),
                "constraints_count": len(constraints),
                "gaps_count": len(evidence_gaps),
                "analysis_complete": analysis_complete,
                # No customer data, amounts, or PII in audit event
            },
            state,
        )

        return {
            "applicability_factors_json": json.dumps(applicability_factors),
            "constraints_json": json.dumps(constraints),
            "evidence_gaps_json": json.dumps(evidence_gaps),
            "analysis_complete": analysis_complete,
            "status": AgentStatus.SUCCESS.value,
        }
