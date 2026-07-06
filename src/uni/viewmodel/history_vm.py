"""History ViewModel — browse and export measurement history."""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from PySide6.QtCore import Signal

from uni.core.history.repository import (
    ErrorRecord,
    HistoryRepository,
    MeasurementRecord,
)
from uni.viewmodel.base import BaseViewModel

logger = logging.getLogger(__name__)


class HistoryViewModel(BaseViewModel):
    """Manages history browsing and export.

    Signals:
        measurements_updated: Emitted when measurement list changes.
        errors_updated: Emitted when error list changes.
        export_ready: Emitted with export data.
    """

    measurements_updated = Signal(list)  # list of measurement dicts
    errors_updated = Signal(list)  # list of error dicts
    export_ready = Signal(str, str)  # (filename, content)

    def __init__(self, repo: HistoryRepository | None = None) -> None:
        super().__init__()
        self._repo = repo
        self._measurements: list[MeasurementRecord] = []
        self._errors: list[ErrorRecord] = []

    def set_repository(self, repo: HistoryRepository) -> None:
        """Set the history repository."""
        self._repo = repo

    async def load_measurements(
        self, host: str | None = None, limit: int = 100
    ) -> None:
        """Load measurements from the database.

        Args:
            host: Optional host filter.
            limit: Maximum records.
        """
        if self._repo is None:
            return
        self._measurements = await self._repo.get_measurements(host=host, limit=limit)
        self.measurements_updated.emit([m.to_dict() for m in self._measurements])

    async def load_errors(self, limit: int = 100) -> None:
        """Load error records from the database.

        Args:
            limit: Maximum records.
        """
        if self._repo is None:
            return
        self._errors = await self._repo.get_errors(limit=limit)
        self.errors_updated.emit([e.to_dict() for e in self._errors])

    async def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics."""
        if self._repo is None:
            return {}
        return await self._repo.get_stats()

    def export_measurements_csv(self) -> str:
        """Export measurements to CSV string.

        Returns:
            CSV content string.
        """
        if not self._measurements:
            return ""
        output = io.StringIO()
        if self._measurements:
            first = self._measurements[0].to_dict()
            writer = csv.DictWriter(output, fieldnames=list(first.keys()))
            writer.writeheader()
            for m in self._measurements:
                writer.writerow(m.to_dict())
        return output.getvalue()

    def export_measurements_json(self, indent: int = 2) -> str:
        """Export measurements to JSON string.

        Args:
            indent: JSON indentation.

        Returns:
            JSON content string.
        """
        data = [m.to_dict() for m in self._measurements]
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def export_errors_json(self, indent: int = 2) -> str:
        """Export errors to JSON string.

        Args:
            indent: JSON indentation.

        Returns:
            JSON content string.
        """
        data = [e.to_dict() for e in self._errors]
        return json.dumps(data, indent=indent, ensure_ascii=False)
