"""Probe ViewModel — manages probe campaigns with live progress."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Signal

from uni.core.probe.engine import (
    CampaignResult,
    ProbeEngine,
    ProbeTarget,
    TestMode,
    TestModeConfig,
)
from uni.viewmodel.base import BaseViewModel

logger = logging.getLogger(__name__)


class ProbeViewModel(BaseViewModel):
    """Manages probe campaign execution and results.

    Signals:
        probe_started: Emitted when a probe campaign begins.
        probe_progress: Emitted with (current, total, last_rtt).
        probe_completed: Emitted with campaign result dict.
        probe_error: Emitted with error message.
    """

    probe_started = Signal(str, int)  # target, total_probes
    probe_progress = Signal(int, int, float)  # current, total, last_rtt
    probe_completed = Signal(dict)  # campaign result dict
    probe_error = Signal(str)  # error message

    def __init__(self) -> None:
        super().__init__()
        self._engine = ProbeEngine()
        self._running = False
        self._last_result: CampaignResult | None = None

    @property
    def is_running(self) -> bool:
        """Whether a probe is currently running."""
        return self._running

    @property
    def last_result(self) -> CampaignResult | None:
        """Result of the last completed probe."""
        return self._last_result

    async def run_probe(
        self,
        host: str,
        port: int = 27015,
        mode: str = "normal",
        interval: float | None = None,
        count: int | None = None,
    ) -> None:
        """Run a probe campaign.

        Args:
            host: Target host.
            port: Target port.
            mode: Test mode (normal/deep/aggressive).
            interval: Custom probe interval (overrides mode).
            count: Custom probe count (overrides mode).
        """
        if self._running:
            self.emit_error("A probe is already running")
            return

        self._running = True
        self.probe_started.emit(f"{host}:{port}", count or 20)
        self.emit_status(f"Probing {host}:{port}...")

        test_mode = TestMode(mode)
        cfg: TestModeConfig | None = None
        if interval is not None or count is not None:
            base = {
                TestMode.NORMAL: TestModeConfig(count=20, interval=1.0, timeout=3.0),
                TestMode.DEEP: TestModeConfig(count=100, interval=0.5, timeout=3.0),
                TestMode.AGGRESSIVE: TestModeConfig(
                    count=200, interval=0.2, timeout=5.0
                ),
            }[test_mode]
            cfg = TestModeConfig(
                count=count or base.count,
                interval=interval if interval is not None else base.interval,
                timeout=base.timeout,
                payload_size=base.payload_size,
            )

        async def _progress_cb(current: int, total: int, result: Any) -> None:
            rtt = result.rtt_ms if result.rtt_ms is not None else -1.0
            self.probe_progress.emit(current, total, rtt)

        try:
            result = await self._engine.run_campaign(
                ProbeTarget(host=host, port=port),
                mode=test_mode,
                config=cfg,
                on_progress=_progress_cb,
            )
            self._last_result = result
            self.probe_completed.emit(result.to_dict())
            self.emit_status(
                f"Probe complete: grade={result.quality.grade.value}, "
                f"rtt={result.avg_rtt:.1f}ms"
            )
        except Exception as exc:
            self.probe_error.emit(str(exc))
            self.emit_error(f"Probe failed: {exc}")
        finally:
            self._running = False

    def get_mode_config(self, mode: str) -> dict[str, Any]:
        """Get configuration for a test mode.

        Args:
            mode: Mode name (normal/deep/aggressive).

        Returns:
            Mode configuration dictionary.
        """
        configs = {
            "normal": TestModeConfig(
                count=20, interval=1.0, timeout=3.0, label="Normal"
            ),
            "deep": TestModeConfig(count=100, interval=0.5, timeout=3.0, label="Deep"),
            "aggressive": TestModeConfig(
                count=200, interval=0.2, timeout=5.0, label="Aggressive"
            ),
        }
        cfg = configs.get(mode, configs["normal"])
        return {
            "count": cfg.count,
            "interval": cfg.interval,
            "timeout": cfg.timeout,
            "label": cfg.label,
        }
