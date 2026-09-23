"""PreProcessNode — dispute scope and authorization validation for RET-C2-640."""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

# Operator ID allowlist pattern: alphanumeric + hyphen, 4-32 chars
_OPERATOR_RE = re.compile(r"^[A-Za-z0-9\-]{4,32}$")

# Dispute ID pattern: DISP-<alphanumeric> or plain alphanumeric up to 64 chars
_DISPUTE_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{1,64}$")

# Offer ID pattern: up to 64 chars alphanumeric/hyphen/underscore
_OFFER_ID_RE = re.compile(r"^[A-Za-z0-9\-_]{1,64}$")

# ISO date pattern: YYYY-MM-DD
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Max input length to prevent large payload injection
_MAX_INPUT_LEN = 8192

# Approved source IDs allowlist (config-driven; also checked at evidence retrieval)
_APPROVED_SOURCE_IDS = frozenset(["LOYALTY_DB", "OFFER_CATALOG", "DISPUTE_HISTORY"])
_GREETING_ONLY = re.compile(
    r"^(?:hello|hi|hey|hello[,. ]*hi|xin chào|chào|こんにちは)[!. ,]*$",
    re.IGNORECASE,
)
_INPUT_GUIDANCE = [
    "Send a valid JSON loyalty-dispute request with all required identifiers and dates.",
    "Required fields: dispute_id, customer_ref, offer_id, dispute_period_start, dispute_period_end, operator_id.",
    'Set approved_source_ids to one or more of ["LOYALTY_DB", "OFFER_CATALOG", "DISPUTE_HISTORY"].',
]


def _input_error(message: str) -> dict[str, Any]:
    return {
        "status": AgentStatus.SUCCESS.value,
        "input_error_message": message,
        "input_error_guidance": "\n".join(_INPUT_GUIDANCE),
    }


def _parse_input(raw: str) -> dict:
    """Parse JSON dispute request from user_input or input_context."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


class PreProcessNode(FunctionNode):
    """Dispute scope and authorization validation node.

    S-2 extra gate: validates operator authorization, dispute criteria format,
    offer/source allowlisting, and bounded time range.
    Emits audit event without customer or account content (PII minimization).
    trust_level: VERIFIED_EXTERNAL (outer boundary node).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict) -> dict:
        """S-2 extra gate: reject malformed or over-length input before processing."""
        raw = state.get("user_input", "") or ""
        raw_ctx = state.get("input_context", {}) or {}
        # Allow input from input_context.raw (server.py passes this)
        effective = raw_ctx.get("raw", raw) if isinstance(raw_ctx, dict) else raw

        if len(effective) > _MAX_INPUT_LEN:
            raise SecurityViolationError(f"PreProcessNode: input exceeds maximum length ({_MAX_INPUT_LEN} chars)")
        return state

    def execute(self, state: dict) -> dict:
        """Validate and normalize authorized dispute criteria."""
        raw = state.get("user_input", "") or ""
        raw_ctx = state.get("input_context", {}) or {}
        effective = raw_ctx.get("raw", raw) if isinstance(raw_ctx, dict) else raw

        if not effective or not effective.strip():
            emit_trace_event(
                "PreProcessNode_validation_failed",
                {"reason": "empty_input"},
                state,
            )
            return _input_error("No loyalty-dispute request was provided.")

        if _GREETING_ONLY.fullmatch(effective.strip()):
            return _input_error("The message contains only a greeting and no loyalty-dispute request.")

        data = _parse_input(effective.strip())
        if not data:
            emit_trace_event(
                "PreProcessNode_validation_failed",
                {"reason": "invalid_json"},
                state,
            )
            return _input_error("The input is not a valid JSON dispute request.")

        # Validate required fields
        errors: list[str] = []
        authorization_errors: list[str] = []

        dispute_id = str(data.get("dispute_id", "")).strip()
        if not dispute_id or not _DISPUTE_ID_RE.match(dispute_id):
            errors.append("dispute_id is missing or invalid (alphanumeric/hyphen/underscore, 1-64 chars)")

        customer_ref = str(data.get("customer_ref", "")).strip()
        if not customer_ref or len(customer_ref) > 64:
            errors.append("customer_ref is missing or too long (max 64 chars)")

        offer_id = str(data.get("offer_id", "")).strip()
        if not offer_id or not _OFFER_ID_RE.match(offer_id):
            errors.append("offer_id is missing or invalid")

        period_start = str(data.get("dispute_period_start", "")).strip()
        if not period_start or not _DATE_RE.match(period_start):
            errors.append("dispute_period_start must be YYYY-MM-DD format")

        period_end = str(data.get("dispute_period_end", "")).strip()
        if not period_end or not _DATE_RE.match(period_end):
            errors.append("dispute_period_end must be YYYY-MM-DD format")

        if period_start and period_end and _DATE_RE.match(period_start) and _DATE_RE.match(period_end):
            if period_start > period_end:
                errors.append("dispute_period_start must not be after dispute_period_end")

        operator_id = str(data.get("operator_id", "")).strip()
        if not operator_id or not _OPERATOR_RE.match(operator_id):
            errors.append("operator_id is missing or invalid (alphanumeric/hyphen, 4-32 chars)")

        # Validate and allowlist source IDs
        raw_sources = data.get("approved_source_ids", [])
        if not isinstance(raw_sources, list) or not raw_sources:
            errors.append("approved_source_ids must be a non-empty list")
            approved_sources: list[str] = []
        else:
            approved_sources = [s for s in raw_sources if s in _APPROVED_SOURCE_IDS]
            rejected = [s for s in raw_sources if s not in _APPROVED_SOURCE_IDS]
            if rejected:
                message = f"approved_source_ids contains non-allowlisted sources: {rejected}"
                errors.append(message)
                authorization_errors.append(message)
            if not approved_sources:
                errors.append("no approved sources remain after allowlist filtering")

        if errors:
            emit_trace_event(
                "PreProcessNode_validation_failed",
                {"error_count": len(errors)},
                state,
            )
            if authorization_errors:
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [f"PreProcessNode: {e}" for e in errors],
                }
            return _input_error("; ".join(errors))

        emit_trace_event(
            "PreProcessNode_validation_passed",
            {
                "dispute_id": dispute_id,
                "offer_id": offer_id,
                "operator_id": operator_id,
                "source_count": len(approved_sources),
                # No customer_ref or PII in audit event
            },
            state,
        )

        return {
            "dispute_id": dispute_id,
            "customer_ref": customer_ref,
            "offer_id": offer_id,
            "dispute_period_start": period_start,
            "dispute_period_end": period_end,
            "approved_source_ids": json.dumps(approved_sources),
            "operator_id": operator_id,
            "normalized_input": effective.strip(),
            "status": AgentStatus.SUCCESS.value,
        }
