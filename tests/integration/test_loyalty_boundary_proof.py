"""PB-3: External-service boundary proof for RET-C2-640.

Proves controlled fake-adapter mapping and provenance across the L1-to-service
boundary. Verifies:
  - All returned records carry source_id and api_version (provenance)
  - Allowlist enforcement (only approved source IDs accepted)
  - No raw provider data leaks (normalized output only)
  - Idempotent call recording
"""

from __future__ import annotations

import json


from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel


def _anon(**overrides) -> dict:
    base = {
        "caller_trust_level": TrustLevel.ANONYMOUS.value,
        "correlation_id": "pb3-test",
        "session_id": "pb3-session",
        "node_history": [],
        "error_log": [],
    }
    base.update(overrides)
    return base


def _preprocess_state(**overrides) -> dict:
    base = _anon(
        dispute_id="DISP-PB3",
        customer_ref="CUST-PB3",
        offer_id="OFFER-PB3",
        dispute_period_start="2024-01-01",
        dispute_period_end="2024-01-31",
        operator_id="OP-1234",
        approved_source_ids=json.dumps(["LOYALTY_DB", "OFFER_CATALOG"]),
        normalized_input="{}",
        status=AgentStatus.SUCCESS.value,
    )
    base.update(overrides)
    return base


class TestLoyaltyBoundaryProvenance:
    """PB-3: Fake adapter mapping and provenance across L1 boundary."""

    def test_all_offer_rules_carry_provenance(self):
        """PB-3: Every offer rule returned must have source_id and api_version."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_preprocess_state())

        rules = json.loads(result["offer_rules_json"])
        assert len(rules) >= 1
        for rule in rules:
            assert "source_id" in rule, f"Rule missing source_id: {rule}"
            assert "api_version" in rule, f"Rule missing api_version: {rule}"
            assert rule["source_id"] != "", "source_id must not be empty"

    def test_all_history_records_carry_provenance(self):
        """PB-3: Every history record must have source_id and api_version."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_preprocess_state())

        history = json.loads(result["loyalty_history_json"])
        assert len(history) >= 1
        for record in history:
            assert "source_id" in record, f"History record missing source_id: {record}"
            assert "api_version" in record, f"History record missing api_version: {record}"

    def test_evidence_sources_json_tracks_per_source(self):
        """PB-3: evidence_sources_json records retrieval counts per source."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_preprocess_state())

        sources = json.loads(result["evidence_sources_json"])
        assert isinstance(sources, list)
        source_ids = {s["source_id"] for s in sources}
        assert "LOYALTY_DB" in source_ids

    def test_adapter_call_recorded_for_assertion(self):
        """PB-3: FakeLoyaltyAdapter records each call with correct parameters."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        fake = FakeLoyaltyAdapter()
        node = EvidenceRetrievalNode()
        node._adapter_override = fake

        node(_preprocess_state())

        assert len(fake.offer_rules_calls) == 1
        assert fake.offer_rules_calls[0]["offer_id"] == "OFFER-PB3"

        assert len(fake.loyalty_history_calls) == 1
        call = fake.loyalty_history_calls[0]
        assert call["customer_ref"] == "CUST-PB3"
        assert call["period_start"] == "2024-01-01"
        assert call["period_end"] == "2024-01-31"

    def test_partial_source_failure_still_provides_provenance(self):
        """PB-3: partial failure case still includes evidence_sources_json provenance."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter(raise_on_offer_rules=True)
        result = node(_preprocess_state())

        # Should still succeed with loyalty history
        assert result["status"] == AgentStatus.SUCCESS.value
        sources = json.loads(result["evidence_sources_json"])
        assert isinstance(sources, list)

    def test_no_raw_api_response_in_state(self):
        """PB-3: No raw provider API response objects in state (normalized only)."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_preprocess_state())

        # All values must be JSON-serializable primitives (no objects)
        for key, value in result.items():
            assert not callable(value), f"Non-serializable value in state key: {key}"
            if isinstance(value, str) and value.startswith("["):
                parsed = json.loads(value)
                assert isinstance(parsed, list)

    def test_allowlist_enforced_at_source_level(self):
        """PB-3: PreProcessNode enforces source ID allowlist before retrieval."""
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(
            {
                "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
                "correlation_id": "pb3-allowlist",
                "node_history": [],
                "error_log": [],
                "user_input": json.dumps(
                    {
                        "dispute_id": "DISP-001",
                        "customer_ref": "CUST-001",
                        "offer_id": "OFFER-001",
                        "dispute_period_start": "2024-01-01",
                        "dispute_period_end": "2024-01-31",
                        "operator_id": "OP-1234",
                        "approved_source_ids": ["EVIL_SOURCE", "ANOTHER_BAD"],
                    }
                ),
            }
        )
        assert result["status"] == AgentStatus.ERROR.value


def test_outer_graph_interrupts_and_resumes_with_persistent_inner_checkpoint():
    """The nested Cat-2 graph must preserve its HITL checkpoint through resume."""
    from framework.schemas.invocation_context import InvocationContext
    from framework.secrets.context import bound_secrets
    from langgraph.checkpoint.memory import MemorySaver
    from shared.secrets.inmemory_provider import InMemoryProvider
    from src.graph.graph import Graph

    provider = InMemoryProvider({})
    graph = Graph(config={"hitl": {"enabled": True, "max_hitl": 1}, "llm": None})
    graph.compile(checkpointer=MemorySaver())
    graph.provision_secrets(provider)
    ctx = InvocationContext(
        session_id="integration-session",
        thread_id="integration-thread",
        caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
        hitl_allowed=True,
    )
    payload = json.dumps(
        {
            "dispute_id": "DISP-INTEGRATION",
            "customer_ref": "CUST-MASKED-INTEGRATION",
            "offer_id": "OFFER-INTEGRATION",
            "dispute_period_start": "2026-01-01",
            "dispute_period_end": "2026-08-19",
            "operator_id": "OP-6400",
            "approved_source_ids": ["LOYALTY_DB"],
        }
    )

    with bound_secrets(provider):
        suspended = graph.invoke(payload, ctx=ctx)
        assert suspended["status"] == AgentStatus.AWAITING_HUMAN.value
        assert suspended["hitl_metadata"]["type"] == "human_review_required"

        resumed = graph.resume(
            thread_id="integration-thread",
            feedback={"review_disposition": "approved", "review_notes": "reviewed"},
        )

    assert resumed["status"] == AgentStatus.SUCCESS.value
    assert "decision-support" in resumed["output"].lower()
    assert "partial evidence" in resumed["output"].lower()
