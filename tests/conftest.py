"""Fixtures for the Dashable integration tests."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/dashable in tests."""
    yield
