"""Tests use AgentCore's real secret context with inert credentials."""

import pytest

from framework.secrets.context import bound_secrets
from shared.secrets.inmemory_provider import InMemoryProvider


@pytest.fixture(autouse=True)
def _bound_test_secrets():
    with bound_secrets(InMemoryProvider({"loyalty_api_key": "test-loyalty"})):
        yield
