"""Shared test fixtures for UDP Network Intelligence."""

from __future__ import annotations

import pytest

from uni.app.config import AppConfig
from uni.services.event_bus import EventBus


@pytest.fixture
def event_bus() -> EventBus:
    """Fresh EventBus instance."""
    return EventBus()


@pytest.fixture
def app_config() -> AppConfig:
    """Default AppConfig instance."""
    return AppConfig()


@pytest.fixture
def sample_target() -> tuple[str, int]:
    """Sample (host, port) target."""
    return ("127.0.0.1", 27015)
