"""LoyaltyAdapter — approved evidence retrieval adapter for RET-C2-640."""

from __future__ import annotations

from typing import Any


class LoyaltyAdapterError(Exception):
    """Raised on loyalty data source errors (not-found, timeout, access denied)."""


class LoyaltyAdapter:
    """Live loyalty evidence retrieval adapter.

    Fetches offer rules, customer loyalty history, and dispute records from
    approved configured sources via ctx.secrets.require().
    Never returns raw provider payloads; all records are normalized and
    provenance-stamped before being returned.
    """

    # Pinned API version for evidence provenance stamping
    API_VERSION = "2024-01"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @classmethod
    def create(cls, api_key: str) -> "LoyaltyAdapter":
        return cls(api_key)

    def retrieve_offer_rules(
        self,
        offer_id: str,
        source_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Retrieve normalized offer rules for the given offer from approved sources.

        Returns list of provenance-bearing rule records:
          {"rule_id": str, "description": str, "condition": str,
           "source_id": str, "api_version": str}
        Raises LoyaltyAdapterError on retrieval failure.
        """
        raise NotImplementedError("Live LoyaltyAdapter.retrieve_offer_rules() not wired in test/dev")

    def retrieve_loyalty_history(
        self,
        customer_ref: str,
        offer_id: str,
        period_start: str,
        period_end: str,
        source_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Retrieve normalized loyalty activity records for the dispute period.

        Returns list of provenance-bearing activity records:
          {"activity_id": str, "activity_type": str, "occurred_at": str,
           "points": int, "source_id": str, "api_version": str}
        Raises LoyaltyAdapterError on retrieval failure.
        """
        raise NotImplementedError("Live LoyaltyAdapter.retrieve_loyalty_history() not wired in test/dev")

    def retrieve_prior_disputes(
        self,
        customer_ref: str,
        offer_id: str,
        source_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Retrieve prior dispute/outcome records for the customer+offer from approved sources.

        Returns list of provenance-bearing dispute records:
          {"dispute_id": str, "outcome": str, "exception_applied": bool,
           "policy_ref": str, "source_id": str, "api_version": str}
        Raises LoyaltyAdapterError on retrieval failure.
        """
        raise NotImplementedError("Live LoyaltyAdapter.retrieve_prior_disputes() not wired in test/dev")


class FakeLoyaltyAdapter:
    """Deterministic test seam for LoyaltyAdapter.

    Records calls for assertion. Configurable raise_on_* for error path testing.
    All returned records carry 'source_id' and 'api_version' for provenance tests.
    """

    API_VERSION = "2024-01-fake"

    def __init__(
        self,
        offer_rules: list[dict[str, Any]] | None = None,
        loyalty_history: list[dict[str, Any]] | None = None,
        prior_disputes: list[dict[str, Any]] | None = None,
        raise_on_offer_rules: bool = False,
        raise_on_loyalty_history: bool = False,
        raise_on_prior_disputes: bool = False,
    ) -> None:
        self._offer_rules = offer_rules or [
            {
                "rule_id": "RULE-001",
                "description": "Earn 2x points on qualifying purchases over $50",
                "condition": "purchase_amount >= 50",
                "source_id": "LOYALTY_DB",
                "api_version": self.API_VERSION,
            }
        ]
        self._loyalty_history = loyalty_history or [
            {
                "activity_id": "ACT-001",
                "activity_type": "purchase",
                "occurred_at": "2024-01-15T10:30:00Z",
                "points": 150,
                "source_id": "LOYALTY_DB",
                "api_version": self.API_VERSION,
            }
        ]
        self._prior_disputes = prior_disputes or []
        self.raise_on_offer_rules = raise_on_offer_rules
        self.raise_on_loyalty_history = raise_on_loyalty_history
        self.raise_on_prior_disputes = raise_on_prior_disputes

        # Call recording for test assertions
        self.offer_rules_calls: list[dict[str, Any]] = []
        self.loyalty_history_calls: list[dict[str, Any]] = []
        self.prior_dispute_calls: list[dict[str, Any]] = []

    def retrieve_offer_rules(
        self,
        offer_id: str,
        source_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.offer_rules_calls.append({"offer_id": offer_id, "source_ids": source_ids})
        if self.raise_on_offer_rules:
            raise LoyaltyAdapterError("Simulated offer rules retrieval failure")
        return self._offer_rules

    def retrieve_loyalty_history(
        self,
        customer_ref: str,
        offer_id: str,
        period_start: str,
        period_end: str,
        source_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.loyalty_history_calls.append(
            {
                "customer_ref": customer_ref,
                "offer_id": offer_id,
                "period_start": period_start,
                "period_end": period_end,
                "source_ids": source_ids,
            }
        )
        if self.raise_on_loyalty_history:
            raise LoyaltyAdapterError("Simulated loyalty history retrieval failure")
        return self._loyalty_history

    def retrieve_prior_disputes(
        self,
        customer_ref: str,
        offer_id: str,
        source_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.prior_dispute_calls.append(
            {
                "customer_ref": customer_ref,
                "offer_id": offer_id,
                "source_ids": source_ids,
            }
        )
        if self.raise_on_prior_disputes:
            raise LoyaltyAdapterError("Simulated prior disputes retrieval failure")
        return self._prior_disputes
