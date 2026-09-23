"""PB-6: invoke execution order and negative S-1 boundary."""

import importlib
import inspect
import json
import pkgutil
from typing import ClassVar

from framework.nodes.base_node import BaseNode
from framework.schemas.trust_level import TrustLevel


class _PrivilegedTrustGateFixture(BaseNode):
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _security_gate_input(self, state):
        return state

    def execute(self, state):
        return {"status": "success"}

    def _security_gate_output(self, result):
        return result


def _discover_node_classes() -> list[type]:
    package = importlib.import_module("src.nodes")
    discovered = []
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, prefix="src.nodes."):
        module = importlib.import_module(module_name)
        for candidate in vars(module).values():
            if (
                isinstance(candidate, type)
                and issubclass(candidate, BaseNode)
                and candidate is not BaseNode
                and candidate.__module__ == module_name
                and not inspect.isabstract(candidate)
                and candidate not in discovered
            ):
                discovered.append(candidate)
    return discovered


def _valid_state(trust_level: TrustLevel) -> dict:
    return {
        "caller_trust_level": trust_level.value,
        "correlation_id": "pb6-correlation",
        "session_id": "pb6-session",
        "thread_id": "pb6-thread",
        "trace_id": "pb6-trace",
        "user_input": json.dumps(
            {
                "dispute_id": "DISP-PB6",
                "customer_ref": "CUST-PB6",
                "offer_id": "OFFER-PB6",
                "dispute_period_start": "2026-01-01",
                "dispute_period_end": "2026-08-19",
                "operator_id": "OP-6400",
                "approved_source_ids": ["LOYALTY_DB"],
            }
        ),
        "dispute_id": "DISP-PB6",
        "customer_ref": "CUST-PB6",
        "offer_id": "OFFER-PB6",
        "dispute_period_start": "2026-01-01",
        "dispute_period_end": "2026-08-19",
        "operator_id": "OP-6400",
        "approved_source_ids": json.dumps(["LOYALTY_DB"]),
        "offer_rules_json": json.dumps(
            [
                {
                    "rule_id": "RULE-PB6",
                    "description": "Test rule",
                    "condition": "documented activity",
                    "source_id": "LOYALTY_DB",
                    "api_version": "test",
                }
            ]
        ),
        "loyalty_history_json": json.dumps(
            [
                {
                    "activity_id": "ACT-PB6",
                    "activity_type": "purchase",
                    "occurred_at": "2026-02-01T00:00:00Z",
                    "points": 100,
                    "source_id": "LOYALTY_DB",
                    "api_version": "test",
                }
            ]
        ),
        "applicability_factors_json": "[]",
        "constraints_json": "[]",
        "evidence_gaps_json": "[]",
        "exception_factors_json": "[]",
        "exception_citations_json": "[]",
        "prior_outcomes_json": "[]",
        "evidence_retrieved": True,
        "analysis_complete": True,
        "exception_analysis_complete": True,
        "hitl_allowed": False,
        "hitl_count": 0,
        "status": "success",
    }


class TestInvokeOrder:
    def test_s1_denial_refuses_execution_before_execute(self, monkeypatch):
        import framework.nodes.base_node as base_node_module

        events: list[str] = []
        execute_calls: list[object] = []
        monkeypatch.setattr(
            base_node_module,
            "emit_trace_event",
            lambda event_type, _payload, _state: events.append(event_type),
        )
        original_execute = _PrivilegedTrustGateFixture.execute

        def spy_execute(self, state):
            execute_calls.append(state)
            return original_execute(self, state)

        monkeypatch.setattr(_PrivilegedTrustGateFixture, "execute", spy_execute)
        result = _PrivilegedTrustGateFixture()(
            {
                "caller_trust_level": TrustLevel.ANONYMOUS.value,
                "correlation_id": "pb6-s1-denial",
            }
        )
        assert result["status"] == "error"
        assert "S-1 trust gate denied" in result["error_log"][0]
        assert events == ["s1_denied"]
        assert not execute_calls

    def test_call_order_for_every_node(self, monkeypatch):
        import framework.nodes.base_node as base_node_module
        from src.services.loyalty_adapter import FakeLoyaltyAdapter

        failures: list[str] = []
        for node_cls in _discover_node_classes():
            order: list[str] = []
            monkeypatch.setattr(
                base_node_module,
                "emit_trace_event",
                lambda event_type, _payload, _state, _o=order: _o.append(f"event:{event_type}"),
            )
            for method_name, label in (
                ("_security_gate_input", "security_gate_input"),
                ("execute", "execute"),
                ("_security_gate_output", "security_gate_output"),
            ):
                original = getattr(node_cls, method_name)

                def spy(self, arg, _o=order, _label=label, _orig=original):
                    _o.append(_label)
                    return _orig(self, arg)

                monkeypatch.setattr(node_cls, method_name, spy)

            instance = node_cls()
            if hasattr(instance, "_adapter_override"):
                instance._adapter_override = FakeLoyaltyAdapter()
            instance(_valid_state(node_cls.required_trust_level))
            expected = [
                "event:node_start",
                "security_gate_input",
                "execute",
                "security_gate_output",
                "event:node_complete",
            ]
            if order != expected:
                failures.append(f"{node_cls.__name__}: expected {expected}, got {order}")
        assert not failures, "\n".join(failures)
