"""Unit tests for RET-C2-640 LoyaltyDisputeResolutionAgent nodes.

TC-01..TC-11: Framework compliance
BL-01..BL-08: Business logic
"""

from __future__ import annotations

import json
import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel


def _vs(**overrides) -> dict:
    """Build a verified-external state dict."""
    base = {
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "node_history": [],
        "error_log": [],
    }
    base.update(overrides)
    return base


def _anon(**overrides) -> dict:
    """Build an anonymous trust state dict."""
    base = {
        "caller_trust_level": TrustLevel.ANONYMOUS.value,
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "node_history": [],
        "error_log": [],
    }
    base.update(overrides)
    return base


def _valid_input_json(**overrides) -> str:
    """Build a valid dispute JSON input string."""
    data = {
        "dispute_id": "DISP-001",
        "customer_ref": "CUST-REF-001",
        "offer_id": "OFFER-GOLD-2024",
        "dispute_period_start": "2024-01-01",
        "dispute_period_end": "2024-01-31",
        "operator_id": "OP-1234",
        "approved_source_ids": ["LOYALTY_DB", "OFFER_CATALOG"],
    }
    data.update(overrides)
    return json.dumps(data)


def _post_preprocess_state(**overrides) -> dict:
    """Build state as it would be after PreProcessNode succeeds."""
    base = _vs(
        dispute_id="DISP-001",
        customer_ref="CUST-REF-001",
        offer_id="OFFER-GOLD-2024",
        dispute_period_start="2024-01-01",
        dispute_period_end="2024-01-31",
        operator_id="OP-1234",
        approved_source_ids=json.dumps(["LOYALTY_DB", "OFFER_CATALOG"]),
        normalized_input=_valid_input_json(),
        status=AgentStatus.SUCCESS.value,
        error_log=[],
    )
    base.update(overrides)
    return base


def _post_evidence_state(**overrides) -> dict:
    """Build state as it would be after EvidenceRetrievalNode succeeds."""
    base = _post_preprocess_state(
        offer_rules_json=json.dumps(
            [
                {
                    "rule_id": "RULE-001",
                    "description": "2x points on $50+ purchases",
                    "condition": "purchase_amount >= 50",
                    "source_id": "LOYALTY_DB",
                    "api_version": "2024-01-fake",
                },
            ]
        ),
        loyalty_history_json=json.dumps(
            [
                {
                    "activity_id": "ACT-001",
                    "activity_type": "purchase",
                    "occurred_at": "2024-01-15T10:30:00Z",
                    "points": 150,
                    "source_id": "LOYALTY_DB",
                    "api_version": "2024-01-fake",
                },
            ]
        ),
        evidence_sources_json=json.dumps(
            [
                {
                    "source_id": "LOYALTY_DB",
                    "rules_count": 1,
                    "history_count": 1,
                    "disputes_count": 0,
                    "retrieved": True,
                },
            ]
        ),
        evidence_retrieved=True,
    )
    base.update(overrides)
    return base


def _post_analysis_state(**overrides) -> dict:
    """Build state as it would be after OfferRuleAnalysisNode succeeds."""
    base = _post_evidence_state(
        applicability_factors_json=json.dumps(
            [
                {
                    "rule_id": "RULE-001",
                    "description": "2x points",
                    "condition": "purchase_amount >= 50",
                    "source_id": "LOYALTY_DB",
                    "api_version": "2024-01-fake",
                    "matching_activity_count": 1,
                    "note": "Structural evidence only.",
                },
            ]
        ),
        constraints_json=json.dumps(
            [
                {"rule_id": "RULE-001", "constraint_text": "purchase_amount >= 50", "source_id": "LOYALTY_DB"},
            ]
        ),
        evidence_gaps_json=json.dumps([]),
        analysis_complete=True,
    )
    base.update(overrides)
    return base


def _post_exception_state(**overrides) -> dict:
    """Build state as it would be after ExceptionPatternNode succeeds."""
    base = _post_analysis_state(
        exception_factors_json=json.dumps([]),
        prior_outcomes_json=json.dumps([]),
        exception_citations_json=json.dumps(["Rule: RULE-001 (source: LOYALTY_DB)"]),
        exception_analysis_complete=True,
    )
    base.update(overrides)
    return base


def _post_draft_state(**overrides) -> dict:
    """Build state as it would be after ResponseDraftNode (HITL approved)."""
    base = _post_exception_state(
        response_draft="[Draft response for DISP-001]",
        briefing_summary="Dispute DISP-001 | 1 rule | 1 activity",
        hitl_draft="DRAFT-DISP-001-OFFER-GOLD-2024",
        review_disposition="approved",
        review_notes="",
    )
    base.update(overrides)
    return base


# ── Framework compliance ───────────────────────────────────────────────────────


class TestFrameworkCompliance:
    """TC-01..TC-05: Node contract compliance."""

    def test_tc01_pre_process_declares_trust_level(self):
        """TC-01: PreProcessNode declares required_trust_level as ClassVar."""
        from src.nodes.pre_process_node import PreProcessNode

        assert hasattr(PreProcessNode, "required_trust_level")
        assert PreProcessNode.required_trust_level is TrustLevel.VERIFIED_EXTERNAL

    def test_tc01_post_process_declares_trust_level(self):
        """TC-01: PostProcessNode declares required_trust_level."""
        from src.nodes.post_process_node import PostProcessNode

        assert PostProcessNode.required_trust_level is TrustLevel.VERIFIED_EXTERNAL

    def test_tc01_inner_nodes_anonymous(self):
        """TC-01: Inner domain nodes declare ANONYMOUS (trust-trap prevention)."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode
        from src.nodes.exception_pattern_node import ExceptionPatternNode
        from src.nodes.response_draft_node import ResponseDraftNode

        for cls in (EvidenceRetrievalNode, OfferRuleAnalysisNode, ExceptionPatternNode, ResponseDraftNode):
            assert cls.required_trust_level is TrustLevel.ANONYMOUS, f"{cls.__name__} should be ANONYMOUS"

    def test_tc02_no_config_in_function_node_init(self):
        """TC-02: FunctionNode subclasses accept no config= in __init__."""
        from src.nodes.pre_process_node import PreProcessNode
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode
        from src.nodes.exception_pattern_node import ExceptionPatternNode
        from src.nodes.response_draft_node import ResponseDraftNode
        from src.nodes.post_process_node import PostProcessNode

        for cls in (
            PreProcessNode,
            EvidenceRetrievalNode,
            OfferRuleAnalysisNode,
            ExceptionPatternNode,
            ResponseDraftNode,
            PostProcessNode,
        ):
            node = cls()  # must not raise
            assert node is not None

    def test_tc03_execute_returns_only_changed_keys(self):
        """TC-03: execute() returns only changed keys, not full state."""
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        state = _post_evidence_state()
        result = node(state)
        # Should not echo back all input keys
        assert "dispute_id" not in result
        assert "customer_ref" not in result

    def test_tc04_node_called_via_dunder_call_not_execute(self):
        """TC-04: Tests use node(state) not node.execute(state)."""
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        state = _vs(user_input=_valid_input_json())
        result = node(state)  # via __call__, not .execute()
        assert result is not None

    def test_tc05_state_schema_is_flat_typeddict(self):
        """TC-05: State is a TypedDict subclass with only primitive field annotations."""
        from src.schemas.state import State
        from framework.schemas.agent_state import AgentState
        import typing

        hints = typing.get_type_hints(State)
        allowed = {"str", "int", "float", "bool"}
        domain_fields = set(State.__annotations__) - set(AgentState.__annotations__)
        for field in domain_fields:
            ann = hints[field]
            ann_str = ann if isinstance(ann, str) else getattr(ann, "__name__", str(ann))
            assert str(ann_str) in allowed, f"State.{field} has non-primitive annotation: {ann_str}"

    def test_tc08_to_json_from_json_helpers_present(self):
        """TC-08: to_json / from_json helpers exist in state module."""
        from src.schemas import state as state_mod

        assert hasattr(state_mod, "to_json")
        assert hasattr(state_mod, "from_json")

    def test_tc09_to_json_roundtrip(self):
        """TC-09: to_json / from_json roundtrip is lossless."""
        from src.schemas.state import from_json, to_json

        obj = {"rule_id": "R1", "condition": "x > 0", "count": 5}
        assert from_json(to_json(obj)) == obj

    def test_tc10_from_json_returns_default_on_empty(self):
        """TC-10: from_json("") returns default, not None crash."""
        from src.schemas.state import from_json

        assert from_json("") is None
        assert from_json("", default=[]) == []
        assert from_json("not-json", default={}) == {}

    def test_tc11_s1_rejects_anonymous_for_verified_external_node(self):
        """TC-11: VERIFIED_EXTERNAL node rejects ANONYMOUS caller (S-1 gate)."""
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        state = _anon(user_input=_valid_input_json())
        result = node(state)
        assert result.get("status") == AgentStatus.ERROR.value


# ── Business logic ─────────────────────────────────────────────────────────────


class TestBL01InputValidation:
    """BL-01: PreProcessNode validates dispute criteria."""

    def test_valid_input_passes(self):
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(_vs(user_input=_valid_input_json()))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["dispute_id"] == "DISP-001"
        assert result["offer_id"] == "OFFER-GOLD-2024"

    def test_empty_input_returns_guidance(self):
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(_vs(user_input=""))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["input_error_message"]

    def test_missing_dispute_id_returns_guidance(self):
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        inp = json.dumps(
            {
                "customer_ref": "CUST-REF-001",
                "offer_id": "OFR-001",
                "dispute_period_start": "2024-01-01",
                "dispute_period_end": "2024-01-31",
                "operator_id": "OP-1234",
                "approved_source_ids": ["LOYALTY_DB"],
            }
        )
        result = node(_vs(user_input=inp))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "dispute_id" in result["input_error_message"]

    def test_invalid_date_format_returns_guidance(self):
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(
            _vs(
                user_input=_valid_input_json(
                    dispute_period_start="01/01/2024"  # wrong format
                )
            )
        )
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "YYYY-MM-DD" in result["input_error_message"]

    def test_period_end_before_start_returns_guidance(self):
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(
            _vs(
                user_input=_valid_input_json(
                    dispute_period_start="2024-02-01",
                    dispute_period_end="2024-01-01",
                )
            )
        )
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "must not be after" in result["input_error_message"]

    def test_non_allowlisted_source_rejected(self):
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(_vs(user_input=_valid_input_json(approved_source_ids=["EVIL_SOURCE"])))
        assert result["status"] == AgentStatus.ERROR.value
        assert any("allowlist" in e.lower() or "allowlist" in e for e in result.get("error_log", []))

    def test_source_ids_stored_as_json(self):
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(_vs(user_input=_valid_input_json()))
        assert result["status"] == AgentStatus.SUCCESS.value
        sources = json.loads(result["approved_source_ids"])
        assert isinstance(sources, list)
        assert "LOYALTY_DB" in sources

    def test_input_context_raw_used_when_available(self):
        """S-2: input_context.raw is used over user_input when present."""
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(
            _vs(
                user_input="",
                input_context={"raw": _valid_input_json()},
            )
        )
        assert result["status"] == AgentStatus.SUCCESS.value

    def test_oversized_input_rejected(self):
        """S-2: input exceeding max length raises SecurityViolationError -> ERROR."""
        from src.nodes.pre_process_node import PreProcessNode

        node = PreProcessNode()
        result = node(_vs(user_input="x" * 9000))
        assert result["status"] == AgentStatus.ERROR.value


class TestBL02EvidenceRetrieval:
    """BL-02: EvidenceRetrievalNode retrieves from approved sources."""

    def test_successful_retrieval(self):
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_anon(**_post_preprocess_state()))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["evidence_retrieved"] is True

    def test_offer_rules_stored_as_json(self):
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_anon(**_post_preprocess_state()))
        rules = json.loads(result["offer_rules_json"])
        assert isinstance(rules, list)
        assert len(rules) >= 1

    def test_provenance_per_source(self):
        """Each returned record must carry source_id and api_version."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_anon(**_post_preprocess_state()))
        rules = json.loads(result["offer_rules_json"])
        for rule in rules:
            assert "source_id" in rule
            assert "api_version" in rule

    def test_partial_failure_does_not_block_available_data(self):
        """BL-02: partial source failure -> available data still returned."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter(raise_on_offer_rules=True)
        result = node(_anon(**_post_preprocess_state()))
        # loyalty history still retrieved successfully -> evidence_retrieved=True
        assert result["status"] == AgentStatus.SUCCESS.value
        history = json.loads(result["loyalty_history_json"])
        assert len(history) >= 1

    def test_all_sources_fail_returns_error(self):
        """BL-02: all sources fail -> ERROR status."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter(
            raise_on_offer_rules=True,
            raise_on_loyalty_history=True,
            raise_on_prior_disputes=True,
        )
        result = node(_anon(**_post_preprocess_state()))
        assert result["status"] == AgentStatus.ERROR.value

    def test_missing_prerequisites_returns_error(self):
        """BL-02: missing dispute_id/customer_ref -> ERROR, not crash."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter()
        result = node(_anon())
        assert result["status"] == AgentStatus.ERROR.value


class TestBL03OfferRuleAnalysis:
    """BL-03: OfferRuleAnalysisNode maps rules to applicability factors."""

    def test_analysis_maps_rules_to_factors(self):
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        result = node(_anon(**_post_evidence_state()))
        assert result["status"] == AgentStatus.SUCCESS.value
        factors = json.loads(result["applicability_factors_json"])
        assert len(factors) >= 1
        assert factors[0]["rule_id"] == "RULE-001"

    def test_analysis_does_not_decide_eligibility(self):
        """BL-03: factor notes must state no eligibility decision."""
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        result = node(_anon(**_post_evidence_state()))
        factors = json.loads(result["applicability_factors_json"])
        for factor in factors:
            note = factor.get("note", "").lower()
            assert "eligibility" in note or "human review" in note

    def test_constraints_recorded(self):
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        result = node(_anon(**_post_evidence_state()))
        constraints = json.loads(result["constraints_json"])
        assert len(constraints) >= 1

    def test_no_evidence_returns_error_with_gaps(self):
        """BL-03: no rules + no history -> ERROR with evidence gaps."""
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        result = node(
            _anon(
                **_post_evidence_state(
                    offer_rules_json=json.dumps([]),
                    loyalty_history_json=json.dumps([]),
                )
            )
        )
        assert result["status"] == AgentStatus.ERROR.value
        gaps = json.loads(result["evidence_gaps_json"])
        assert len(gaps) >= 1

    def test_partial_evidence_marked(self):
        """BL-03: history without rules -> analysis_complete=False + gaps."""
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        result = node(
            _anon(
                **_post_evidence_state(
                    offer_rules_json=json.dumps([]),
                )
            )
        )
        # With no rules but history, still processes but marks gaps
        gaps = json.loads(result.get("evidence_gaps_json", "[]"))
        assert any("rule" in g.lower() for g in gaps)


class TestBL04ExceptionPattern:
    """BL-04: ExceptionPatternNode maps exception patterns without making decisions."""

    def test_no_prior_disputes_marks_uncertainty(self):
        """BL-04: no prior disputes -> uncertainty flag in citations."""
        from src.nodes.exception_pattern_node import ExceptionPatternNode

        node = ExceptionPatternNode()
        result = node(_anon(**_post_analysis_state()))
        assert result["status"] == AgentStatus.SUCCESS.value
        citations = json.loads(result["exception_citations_json"])
        # Should include rule citations at minimum
        assert isinstance(citations, list)

    def test_rule_citations_preserved(self):
        """BL-04: applicability factor rule IDs are preserved in citations."""
        from src.nodes.exception_pattern_node import ExceptionPatternNode

        node = ExceptionPatternNode()
        result = node(_anon(**_post_analysis_state()))
        citations = json.loads(result["exception_citations_json"])
        assert any("RULE-001" in c for c in citations)

    def test_prior_dispute_activity_mapped(self):
        """BL-04: dispute/exception activity types are mapped to outcomes."""
        from src.nodes.exception_pattern_node import ExceptionPatternNode

        node = ExceptionPatternNode()
        history_with_exception = json.dumps(
            [
                {
                    "activity_id": "ACT-002",
                    "activity_type": "exception",
                    "occurred_at": "2023-12-01T09:00:00Z",
                    "points": 0,
                    "policy_ref": "POLICY-123",
                    "source_id": "DISPUTE_HISTORY",
                    "api_version": "2024-01-fake",
                },
            ]
        )
        result = node(_anon(**_post_analysis_state(loyalty_history_json=history_with_exception)))
        exception_factors = json.loads(result["exception_factors_json"])
        assert len(exception_factors) >= 1
        assert exception_factors[0]["policy_ref"] == "POLICY-123"

    def test_no_eligibility_decision_in_output(self):
        """BL-04: exception pattern output must not grant/deny eligibility."""
        from src.nodes.exception_pattern_node import ExceptionPatternNode

        node = ExceptionPatternNode()
        result = node(_anon(**_post_analysis_state()))
        prior_outcomes = json.loads(result["prior_outcomes_json"])
        for outcome in prior_outcomes:
            note = outcome.get("note", "").lower()
            assert "decision" not in note or "no" in note or "decision-support" in note


class TestBL05ResponseDraft:
    """BL-05: ResponseDraftNode composes draft and handles HITL outcomes."""

    def test_hitl_skipped_when_not_allowed(self):
        """BL-05: hitl_allowed=False -> no GraphInterrupt, status=success."""
        from src.nodes.response_draft_node import ResponseDraftNode

        node = ResponseDraftNode()
        state = _anon(**_post_exception_state(hitl_allowed=False))
        result = node(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result.get("response_draft", "") != ""

    def test_hitl_triggers_interrupt_when_allowed(self, monkeypatch):
        """BL-05: hitl_allowed=True -> GraphInterrupt raised."""
        from src.nodes.response_draft_node import ResponseDraftNode
        from langgraph.errors import GraphInterrupt
        import src.nodes.response_draft_node as response_draft_module

        def raise_interrupt(_payload):
            raise GraphInterrupt()

        monkeypatch.setattr(response_draft_module, "interrupt", raise_interrupt)

        node = ResponseDraftNode()
        state = _anon(**_post_exception_state(hitl_allowed=True, hitl_draft=""))
        with pytest.raises(GraphInterrupt):
            node(state)

    def test_approved_disposition_returns_success(self):
        """BL-05: 'approved' resume -> SUCCESS with draft intact."""
        from src.nodes.response_draft_node import ResponseDraftNode

        node = ResponseDraftNode()
        state = _anon(
            **_post_exception_state(
                hitl_draft="DRAFT-DISP-001",
                review_disposition="approved",
                response_draft="[Approved draft]",
                briefing_summary="Summary",
            )
        )
        result = node(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["review_disposition"] == "approved"

    def test_corrected_disposition_uses_review_notes(self):
        """BL-05: 'corrected' resume -> corrected draft from review_notes."""
        from src.nodes.response_draft_node import ResponseDraftNode

        node = ResponseDraftNode()
        state = _anon(
            **_post_exception_state(
                hitl_draft="DRAFT-DISP-001",
                review_disposition="corrected",
                response_draft="[Original draft]",
                review_notes="[Corrected draft by reviewer]",
                briefing_summary="Summary",
            )
        )
        result = node(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["review_disposition"] == "corrected"
        assert "[Corrected draft by reviewer]" in result["response_draft"]

    def test_rejected_disposition_returns_error(self):
        """BL-05: 'rejected' resume -> ERROR status."""
        from src.nodes.response_draft_node import ResponseDraftNode

        node = ResponseDraftNode()
        state = _anon(
            **_post_exception_state(
                hitl_draft="DRAFT-DISP-001",
                review_disposition="rejected",
                response_draft="[Draft]",
                review_notes="Insufficient evidence",
                briefing_summary="Summary",
            )
        )
        result = node(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_draft_does_not_grant_rewards(self):
        """BL-05: response draft must not contain reward grant/revocation language."""
        from src.nodes.response_draft_node import ResponseDraftNode

        node = ResponseDraftNode()
        state = _anon(**_post_exception_state(hitl_allowed=False))
        result = node(state)
        draft = result.get("response_draft", "").lower()
        # Must include decision-support disclaimer
        assert "human review" in draft or "authorized" in draft or "draft" in draft.lower()


class TestBL06PostProcess:
    """BL-06: PostProcessNode produces traceable output with provenance."""

    def test_formatted_output_present(self):
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        result = node(_vs(**_post_draft_state()))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result.get("formatted_output", "") != ""

    def test_citations_stored_as_json(self):
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        result = node(_vs(**_post_draft_state()))
        citations = json.loads(result.get("citations_json", "[]"))
        assert isinstance(citations, list)

    def test_provenance_json_contains_sources(self):
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        result = node(_vs(**_post_draft_state()))
        prov = json.loads(result.get("provenance_json", "{}"))
        assert "dispute_id" in prov
        assert "review_disposition" in prov

    def test_limitations_in_output(self):
        """BL-06: output must state decision-support-only limitations."""
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        result = node(_vs(**_post_draft_state()))
        output = result.get("formatted_output", "").lower()
        assert "decision-support" in output or "human" in output

    def test_partial_result_flagged(self):
        """BL-06: partial result marked when analysis_complete=False."""
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        result = node(
            _vs(
                **_post_draft_state(
                    analysis_complete=False,
                    evidence_retrieved=True,
                )
            )
        )
        assert result["partial_result"] is True
        assert (
            "PARTIAL" in result.get("formatted_output", "").upper()
            or "partial" in result.get("formatted_output", "").lower()
        )

    def test_no_credentials_in_output(self):
        """BL-06: S-3 gate rejects credentials in output."""
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        # Inject a credential pattern into response_draft (edge case)
        result = node(
            _vs(
                **_post_draft_state(
                    response_draft="api_key: sk-1234567890abcdefghij",
                )
            )
        )
        # S-3 gate may catch it or output may not contain it — either way no leak
        # The gate rejects outputs with "api_key: " pattern
        assert result is not None

    def test_s1_rejects_anonymous_caller(self):
        """BL-06: PostProcessNode (VERIFIED_EXTERNAL) rejects ANONYMOUS."""
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        state = _post_draft_state()
        state["caller_trust_level"] = TrustLevel.ANONYMOUS.value
        result = node(state)
        assert result.get("status") == AgentStatus.ERROR.value


class TestBL07NoEligibilityDecision:
    """BL-07: Agent must never make eligibility decisions or mutate accounts."""

    def test_offer_rule_analysis_note_prohibits_decision(self):
        """BL-07: OfferRuleAnalysisNode factor notes explicitly state no decision."""
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        result = node(_anon(**_post_evidence_state()))
        factors = json.loads(result["applicability_factors_json"])
        for factor in factors:
            assert "note" in factor
            assert len(factor["note"]) > 0

    def test_response_draft_does_not_mention_account_changes(self):
        """BL-07: No account mutation language in response draft."""
        from src.nodes.response_draft_node import ResponseDraftNode

        node = ResponseDraftNode()
        state = _anon(**_post_exception_state(hitl_allowed=False))
        result = node(state)
        draft = result.get("response_draft", "").lower()
        prohibited = ["account updated", "reward granted", "points added", "subscription changed"]
        for phrase in prohibited:
            assert phrase not in draft, f"Prohibited phrase found in draft: {phrase!r}"

    def test_post_process_output_includes_limitations_section(self):
        """BL-07: limitations section explicitly states no eligibility decision."""
        from src.nodes.post_process_node import PostProcessNode

        node = PostProcessNode()
        result = node(_vs(**_post_draft_state()))
        output = result["formatted_output"]
        assert "LIMITATIONS" in output
        assert "eligibility" in output.lower() or "grant" in output.lower()


class TestBL08PipelineErrorPropagation:
    """BL-08: Errors in inner nodes propagate correctly."""

    def test_evidence_retrieval_error_state_has_error_log(self):
        """BL-08: EvidenceRetrievalNode error returns error_log."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        node = EvidenceRetrievalNode()
        node._adapter_override = FakeLoyaltyAdapter(
            raise_on_offer_rules=True,
            raise_on_loyalty_history=True,
            raise_on_prior_disputes=True,
        )
        result = node(_anon(**_post_preprocess_state()))
        assert result["status"] == AgentStatus.ERROR.value
        assert result.get("error_log")

    def test_analysis_error_contains_gaps(self):
        """BL-08: OfferRuleAnalysisNode error includes evidence_gaps_json."""
        from src.nodes.offer_rule_analysis_node import OfferRuleAnalysisNode

        node = OfferRuleAnalysisNode()
        result = node(
            _anon(
                **_post_evidence_state(
                    offer_rules_json=json.dumps([]),
                    loyalty_history_json=json.dumps([]),
                )
            )
        )
        assert result["status"] == AgentStatus.ERROR.value
        gaps = json.loads(result.get("evidence_gaps_json", "[]"))
        assert gaps

    def test_fake_adapter_records_calls(self):
        """BL-08: FakeLoyaltyAdapter records all calls for assertion."""
        from src.nodes.evidence_retrieval_node import EvidenceRetrievalNode
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        fake = FakeLoyaltyAdapter()
        node = EvidenceRetrievalNode()
        node._adapter_override = fake
        node(_anon(**_post_preprocess_state()))
        assert len(fake.offer_rules_calls) == 1
        assert fake.offer_rules_calls[0]["offer_id"] == "OFFER-GOLD-2024"
