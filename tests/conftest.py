"""Shared test fixtures for UDP Network Intelligence."""

from __future__ import annotations

import sys

import pytest

from uni.app.config import AppConfig
from uni.services.event_bus import EventBus

# Ensure QApplication exists before any widget imports.
# On headless Linux CI (no libEGL), skip gracefully so the rest
# of the test suite can still collect and run.
_qapp = None


def _ensure_qapp() -> None:
    global _qapp
    if _qapp is None:
        try:
            from PySide6.QtWidgets import QApplication

            _qapp = QApplication.instance() or QApplication(sys.argv)
        except (ImportError, OSError):
            pass


_ensure_qapp()


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
