"""EvidenceRetrievalNode — approved loyalty evidence retrieval for RET-C2-640."""

from __future__ import annotations

import json
from typing import ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.base import MissingSecret
from shared.utils.audit_logger import emit_trace_event
from src.schemas.state import from_json
from src.services.loyalty_adapter import FakeLoyaltyAdapter, LoyaltyAdapter, LoyaltyAdapterError


class EvidenceRetrievalNode(FunctionNode):
    """Approved loyalty evidence retrieval node.

    Fetches offer rules, customer loyalty history, and prior dispute records
    from allowlisted configured sources. Normalizes raw provider data into
    provenance-bearing records; enforces source allowlisting.
    Does NOT make eligibility decisions or mutate accounts.
    trust_level: ANONYMOUS (inner DomainWorkflowGraph node).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    # Allow injection of a fake adapter for tests
    _adapter_override: LoyaltyAdapter | FakeLoyaltyAdapter | None = None

    def execute(self, state: dict) -> dict:
        """Retrieve evidence from all approved sources."""
        request = from_json(state.get("user_input", ""), default={})
        if not isinstance(request, dict):
            request = {}
        dispute_id = state.get("dispute_id", "") or str(request.get("dispute_id", ""))
        customer_ref = state.get("customer_ref", "") or str(request.get("customer_ref", ""))
        offer_id = state.get("offer_id", "") or str(request.get("offer_id", ""))
        period_start = state.get("dispute_period_start", "") or str(request.get("dispute_period_start", ""))
        period_end = state.get("dispute_period_end", "") or str(request.get("dispute_period_end", ""))
        operator_id = state.get("operator_id", "") or str(request.get("operator_id", ""))
        approved_source_ids: list[str] = from_json(state.get("approved_source_ids", ""), default=[])
        if not approved_source_ids:
            requested_sources = request.get("approved_source_ids", [])
            approved_source_ids = requested_sources if isinstance(requested_sources, list) else []
        domain_fields = {
            "dispute_id": dispute_id,
            "customer_ref": customer_ref,
            "offer_id": offer_id,
            "dispute_period_start": period_start,
            "dispute_period_end": period_end,
            "operator_id": operator_id,
            "approved_source_ids": json.dumps(approved_source_ids),
        }

        if not all([dispute_id, customer_ref, offer_id, approved_source_ids]):
            emit_trace_event(
                "EvidenceRetrievalNode_prerequisites_missing",
                {
                    "has_dispute_id": bool(dispute_id),
                    "has_customer_ref": bool(customer_ref),
                    "has_offer_id": bool(offer_id),
                    "has_sources": bool(approved_source_ids),
                },
                state,
            )
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["EvidenceRetrievalNode: missing required state from PreProcessNode"],
            }

        try:
            adapter = self._get_adapter(state)
        except MissingSecret:
            unavailable_sources = [
                {
                    "source_id": source_id,
                    "rules_count": 0,
                    "history_count": 0,
                    "disputes_count": 0,
                    "retrieved": False,
                    "coverage": "credential unavailable",
                }
                for source_id in approved_source_ids
            ]
            emit_trace_event(
                "EvidenceRetrievalNode_connector_unavailable",
                {"dispute_id": dispute_id, "offer_id": offer_id},
                state,
            )
            return {
                **domain_fields,
                "offer_rules_json": json.dumps([]),
                "loyalty_history_json": json.dumps([]),
                "evidence_sources_json": json.dumps(unavailable_sources),
                "evidence_retrieved": False,
                "retrieval_unavailable": True,
                "status": AgentStatus.SUCCESS.value,
            }
        error_log: list[str] = []
        offer_rules: list[dict] = []
        loyalty_history: list[dict] = []
        prior_disputes: list[dict] = []

        # Retrieve offer rules (partial failure allowed)
        try:
            offer_rules = adapter.retrieve_offer_rules(
                offer_id=offer_id,
                source_ids=approved_source_ids,
            )
        except LoyaltyAdapterError as exc:
            error_log.append(f"EvidenceRetrievalNode: offer rules retrieval failed — {exc}")

        # Retrieve loyalty history (partial failure allowed)
        try:
            loyalty_history = adapter.retrieve_loyalty_history(
                customer_ref=customer_ref,
                offer_id=offer_id,
                period_start=period_start,
                period_end=period_end,
                source_ids=approved_source_ids,
            )
        except LoyaltyAdapterError as exc:
            error_log.append(f"EvidenceRetrievalNode: loyalty history retrieval failed — {exc}")

        # Retrieve prior disputes (partial failure allowed)
        try:
            prior_disputes = adapter.retrieve_prior_disputes(
                customer_ref=customer_ref,
                offer_id=offer_id,
                source_ids=approved_source_ids,
            )
        except LoyaltyAdapterError as exc:
            error_log.append(f"EvidenceRetrievalNode: prior disputes retrieval failed — {exc}")

        evidence_retrieved = bool(offer_rules or loyalty_history or prior_disputes)

        # Build provenance records per source
        evidence_sources: list[dict] = []
        for src_id in approved_source_ids:
            rules_from_src = [r for r in offer_rules if r.get("source_id") == src_id]
            history_from_src = [h for h in loyalty_history if h.get("source_id") == src_id]
            disputes_from_src = [d for d in prior_disputes if d.get("source_id") == src_id]
            evidence_sources.append(
                {
                    "source_id": src_id,
                    "rules_count": len(rules_from_src),
                    "history_count": len(history_from_src),
                    "disputes_count": len(disputes_from_src),
                    "retrieved": bool(rules_from_src or history_from_src or disputes_from_src),
                }
            )

        if not evidence_retrieved:
            emit_trace_event(
                "EvidenceRetrievalNode_no_evidence",
                {"dispute_id": dispute_id, "offer_id": offer_id, "sources": approved_source_ids},
                state,
            )
            return {
                "offer_rules_json": json.dumps([]),
                "loyalty_history_json": json.dumps([]),
                "evidence_sources_json": json.dumps(evidence_sources),
                "evidence_retrieved": False,
                "status": AgentStatus.ERROR.value,
                "error_log": ["EvidenceRetrievalNode: no evidence retrieved from any approved source"],
            }

        emit_trace_event(
            "EvidenceRetrievalNode_evidence_retrieved",
            {
                "dispute_id": dispute_id,
                "offer_id": offer_id,
                "rules_count": len(offer_rules),
                "history_count": len(loyalty_history),
                "prior_disputes_count": len(prior_disputes),
                "partial_failure": bool(error_log),
                # No customer_ref in audit event (PII minimization)
            },
            state,
        )

        result: dict = {
            **domain_fields,
            "offer_rules_json": json.dumps(offer_rules),
            "loyalty_history_json": json.dumps(loyalty_history),
            "evidence_sources_json": json.dumps(evidence_sources),
            "evidence_retrieved": evidence_retrieved,
            "retrieval_unavailable": False,
            "status": AgentStatus.SUCCESS.value,
        }
        if error_log:
            result["error_log"] = error_log
        return result

    def _get_adapter(self, state: dict) -> LoyaltyAdapter | FakeLoyaltyAdapter:
        """Return adapter; use override for tests."""
        if self._adapter_override is not None:
            return self._adapter_override
        ctx = InvocationContext.from_state(state)
        api_key = ctx.secrets.require("loyalty_api_key")
        return LoyaltyAdapter.create(api_key)
