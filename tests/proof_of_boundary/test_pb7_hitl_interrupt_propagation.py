"""PB-7: HITL Interrupt Propagation Verification for RET-C2-640.

config/config.yaml has hitl.enabled: true — this test is ACTIVE (not skipped).

Tests:
  PB-7-A: interrupt() raises GraphInterrupt and propagates through __call__()
  PB-7-B: hitl_allowed=False guard prevents interrupt() and deadlock
  PB-7-C: approved/corrected/rejected resume routes work correctly
"""

from __future__ import annotations

import json
import pathlib

import pytest

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

# ---------------------------------------------------------------------------
# Conditional skip — only runs when config/agent.yaml has hitl.enabled: true
# ---------------------------------------------------------------------------

_CONFIG_PATH = pathlib.Path(__file__).parents[2] / "config" / "config.yaml"


def _hitl_enabled() -> bool:
    """Return True when config/config.yaml declares hitl.enabled: true."""
    if not _CONFIG_PATH.exists():
        return False
    try:
        import yaml

        data = yaml.safe_load(_CONFIG_PATH.read_text())
    except Exception:
        return False
    hitl = (data or {}).get("hitl", {})
    return bool(hitl.get("enabled", False))


pytestmark = pytest.mark.skipif(
    not _hitl_enabled(),
    reason="config/config.yaml does not set hitl.enabled: true — PB-7 not applicable",
)

# ---------------------------------------------------------------------------
# Shared state builder
# ---------------------------------------------------------------------------


def _base_state(**overrides) -> dict:
    """Return minimal state for ResponseDraftNode PB-7 tests."""
    state = {
        "caller_trust_level": TrustLevel.ANONYMOUS.value,
        "correlation_id": "pb7-test",
        "session_id": "pb7-session",
        "thread_id": "pb7-thread",
        "trace_id": "pb7-trace",
        "node_history": [],
        "error_log": [],
        "hitl_allowed": True,
        "hitl_count": 0,
        # Domain fields required by ResponseDraftNode.execute()
        "dispute_id": "DISP-PB7",
        "offer_id": "OFFER-PB7",
        "operator_id": "OP-1234",
        "evidence_retrieved": True,
        "analysis_complete": True,
        "exception_analysis_complete": True,
        "applicability_factors_json": json.dumps(
            [
                {
                    "rule_id": "R-001",
                    "description": "2x points",
                    "condition": "x>=50",
                    "source_id": "LOYALTY_DB",
                    "api_version": "fake",
                    "matching_activity_count": 1,
                    "note": "structural only",
                },
            ]
        ),
        "constraints_json": json.dumps([]),
        "evidence_gaps_json": json.dumps([]),
        "exception_factors_json": json.dumps([]),
        "exception_citations_json": json.dumps(["Rule: R-001 (source: LOYALTY_DB)"]),
        "prior_outcomes_json": json.dumps([]),
        # HITL state (not yet reviewed)
        "hitl_draft": "",
        "review_disposition": "",
        "response_draft": "",
        "briefing_summary": "",
        "review_notes": "",
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# PB-7-A: interrupt() raises GraphInterrupt and propagates
# ---------------------------------------------------------------------------


def test_pb7_hitl_interrupt_propagates(monkeypatch) -> None:
    """PB-7: interrupt() raises GraphInterrupt and propagates through __call__()."""
    from langgraph.errors import GraphInterrupt
    from src.nodes.response_draft_node import ResponseDraftNode
    import src.nodes.response_draft_node as response_draft_module

    def raise_interrupt(_payload):
        raise GraphInterrupt()

    monkeypatch.setattr(response_draft_module, "interrupt", raise_interrupt)

    node = ResponseDraftNode()
    state = _base_state(hitl_allowed=True, hitl_draft="")

    with pytest.raises(GraphInterrupt):
        node(state)


# ---------------------------------------------------------------------------
# PB-7-B: hitl_allowed=False guard prevents deadlock
# ---------------------------------------------------------------------------


def test_pb7_hitl_allowed_false_skips_interrupt() -> None:
    """PB-7 guard: hitl_allowed=False must NOT raise GraphInterrupt (no deadlock)."""
    from src.nodes.response_draft_node import ResponseDraftNode

    node = ResponseDraftNode()
    state = _base_state(hitl_allowed=False, hitl_draft="")

    result = node(state)  # must NOT raise GraphInterrupt
    assert result.get("status") == AgentStatus.SUCCESS.value
    assert result.get("response_draft", "") != ""


# ---------------------------------------------------------------------------
# PB-7-C: HITL resume routes
# ---------------------------------------------------------------------------


def test_pb7_resume_approved() -> None:
    """PB-7: 'approved' resume -> SUCCESS with draft intact."""
    from src.nodes.response_draft_node import ResponseDraftNode

    node = ResponseDraftNode()
    state = _base_state(
        hitl_draft="DRAFT-DISP-PB7",
        review_disposition="approved",
        response_draft="[PB7 approved draft]",
        briefing_summary="PB7 summary",
    )

    result = node(state)
    assert result.get("status") == AgentStatus.SUCCESS.value
    assert result.get("review_disposition") == "approved"


def test_pb7_resume_corrected() -> None:
    """PB-7: 'corrected' resume -> corrected draft from review_notes."""
    from src.nodes.response_draft_node import ResponseDraftNode

    node = ResponseDraftNode()
    state = _base_state(
        hitl_draft="DRAFT-DISP-PB7",
        review_disposition="corrected",
        response_draft="[Original draft]",
        review_notes="[Corrected by reviewer]",
        briefing_summary="PB7 summary",
    )

    result = node(state)
    assert result.get("status") == AgentStatus.SUCCESS.value
    assert "[Corrected by reviewer]" in result.get("response_draft", "")


def test_pb7_resume_rejected() -> None:
    """PB-7: 'rejected' resume -> ERROR status."""
    from src.nodes.response_draft_node import ResponseDraftNode

    node = ResponseDraftNode()
    state = _base_state(
        hitl_draft="DRAFT-DISP-PB7",
        review_disposition="rejected",
        response_draft="[Draft]",
        review_notes="Insufficient evidence for this claim",
        briefing_summary="PB7 summary",
    )

    result = node(state)
    assert result.get("status") == AgentStatus.ERROR.value
    error_log = result.get("error_log", [])
    assert any("rejected" in e.lower() for e in error_log)
