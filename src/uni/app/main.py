"""Entry point — launches the PySide6 GUI application."""

from __future__ import annotations

import asyncio
import logging
import socket
import sys
import time as _time
from typing import Any

from PySide6.QtCore import QThread
from PySide6.QtCore import Signal as QtSignal
from PySide6.QtWidgets import QApplication, QFileDialog

from uni.services.logger import setup_logging

A2S_INFO = (
    b"\xff\xff\xff\xff\x54\x53\x6f\x75\x72\x63\x65"
    b"\x20\x45\x6e\x67\x69\x6e\x65\x20\x51\x75"
    b"\x65\x72\x79\x00"
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------


class _ProbeWorker(QThread):
    """Sends A2S_INFO packets and measures RTT."""

    progress = QtSignal(int, int, float)
    finished = QtSignal(dict)

    def __init__(self, host: str, port: int, count: int, interval: float) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._count = count
        self._interval = interval
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        from uni.net.models import SocketConfig
        from uni.net.udp_socket import AsyncUDPSocket

        async def _probe() -> dict[str, Any]:
            config = SocketConfig(host="0.0.0.0", port=0, ttl=64)
            rtts: list[float] = []
            sent = 0
            received = 0

            async with AsyncUDPSocket(config) as sock:
                for i in range(self._count):
                    if self._stop:
                        break
                    sent += 1
                    try:
                        pkt = await sock.send_receive(
                            A2S_INFO,
                            (self._host, self._port),
                            timeout=2.0,
                        )
                        if pkt.rtt_ms is not None:
                            received += 1
                            rtts.append(pkt.rtt_ms)
                            self.progress.emit(i + 1, self._count, pkt.rtt_ms)
                        else:
                            self.progress.emit(i + 1, self._count, -1)
                    except (TimeoutError, OSError):
                        self.progress.emit(i + 1, self._count, -1)
                    await asyncio.sleep(self._interval / 1000.0)

            avg = sum(rtts) / len(rtts) if rtts else 0.0
            loss = (sent - received) / sent * 100 if sent else 0.0
            jitter = 0.0
            if len(rtts) >= 2:
                diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
                jitter = sum(diffs) / len(diffs)
            return {
                "host": self._host,
                "port": self._port,
                "sent": sent,
                "received": received,
                "avg_rtt": round(avg, 2),
                "min_rtt": round(min(rtts), 2) if rtts else 0.0,
                "max_rtt": round(max(rtts), 2) if rtts else 0.0,
                "loss": round(loss, 1),
                "jitter": round(jitter, 2),
                "rtts": rtts,
            }

        result = asyncio.run(_probe())
        self.finished.emit(result)


class _TracerouteWorker(QThread):
    """UDP traceroute with increasing TTL."""

    hop = QtSignal(dict)
    progress = QtSignal(int, int)
    finished = QtSignal(dict)
    error = QtSignal(str)

    def __init__(self, host: str, port: int, max_hops: int = 30) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._max_hops = max_hops
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            target_ip = socket.gethostbyname(self._host)
        except socket.gaierror as e:
            self.error.emit(f"Cannot resolve {self._host}: {e}")
            return

        resolved = 0
        reached = False
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(3.0)

        try:
            for ttl in range(1, self._max_hops + 1):
                if self._stop or reached:
                    break
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
                probe = A2S_INFO

                sent_time = _time.monotonic()
                try:
                    sock.sendto(probe, (target_ip, self._port))
                    _data, addr = sock.recvfrom(4096)
                    rtt = (_time.monotonic() - sent_time) * 1000
                    ip = addr[0]

                    try:
                        hostname = socket.gethostbyaddr(ip)[0]
                    except (socket.herror, socket.gaierror):
                        hostname = ""

                    self.hop.emit(
                        {
                            "ttl": ttl,
                            "ip": ip,
                            "rtt_ms": round(rtt, 1),
                            "hostname": hostname,
                        }
                    )
                    resolved += 1

                    if ip == target_ip:
                        reached = True
                except TimeoutError:
                    self.hop.emit(
                        {
                            "ttl": ttl,
                            "ip": "*",
                            "rtt_ms": None,
                            "hostname": "",
                        }
                    )

                self.progress.emit(ttl, self._max_hops)
        finally:
            sock.close()

        self.finished.emit(
            {
                "resolved": resolved,
                "total": ttl,
            }
        )


class _QueryWorker(QThread):
    """Send A2S_INFO and parse response for server info."""

    result = QtSignal(dict)
    error = QtSignal(str)

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port

    def run(self) -> None:
        try:
            from uni.protocol.a2s_protocol import A2SQueryProtocol

            protocol = A2SQueryProtocol()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3.0)
            try:
                wire = protocol.encode_info_request()
                sock.sendto(wire.encode(), (self._host, self._port))
                data, _ = sock.recvfrom(4096)
            finally:
                sock.close()

            # Handle challenge response
            if protocol.is_challenge_response(data):
                challenge = protocol.extract_challenge(data)
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock2.settimeout(3.0)
                try:
                    wire2 = protocol.encode_info_request(challenge=challenge)
                    sock2.sendto(wire2.encode(), (self._host, self._port))
                    data, _ = sock2.recvfrom(4096)
                finally:
                    sock2.close()

            # Parse response using protocol decoder
            try:
                info_obj = protocol.decode_info_response(data)
                info: dict[str, Any] = {
                    "host": self._host,
                    "port": self._port,
                    "name": info_obj.name,
                    "map_name": info_obj.map_name,
                    "game": info_obj.game,
                    "player_count": info_obj.player_count,
                    "max_players": info_obj.max_players,
                    "app_id": info_obj.app_id,
                    "version": info_obj.version,
                }
            except Exception:
                # Fallback: raw byte parsing for GoldSource etc
                info = self._raw_parse(data)

            self.result.emit(info)
        except Exception as e:
            self.error.emit(str(e))

    def _raw_parse(self, data: bytes) -> dict[str, Any]:
        info: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "name": "",
            "map_name": "",
            "game": "",
            "player_count": 0,
            "max_players": 0,
        }
        if len(data) < 6:
            return info
        payload = data[5:]
        parts = payload.split(b"\x00")
        if data[4] == 0x49 and len(parts) >= 6:
            info["name"] = parts[1].decode("utf-8", errors="replace")
            info["map_name"] = parts[2].decode("utf-8", errors="replace")
            info["game"] = parts[3].decode("utf-8", errors="replace")
            counts = parts[5]
            if len(counts) >= 2:
                info["player_count"] = counts[0]
                info["max_players"] = counts[1]
        elif data[4] == 0x6D and len(parts) >= 5:
            info["name"] = parts[1].decode("utf-8", errors="replace")
            info["map_name"] = parts[2].decode("utf-8", errors="replace")
            info["game"] = parts[3].decode("utf-8", errors="replace")
            try:
                info["player_count"] = int(parts[4])
                info["max_players"] = int(parts[5])
            except (ValueError, IndexError):
                pass
        return info


# ---------------------------------------------------------------------------
# Signal wiring
# ---------------------------------------------------------------------------


def _wire_signals(window: object) -> None:
    """Connect every view signal to its backend handler."""
    from typing import cast

    from uni.core.history.repository import (
        HistoryRepository,
        MeasurementRecord,
        ServerRecord,
    )
    from uni.view.main_window import MainWindow

    win = cast("MainWindow", window)
    repo = HistoryRepository("data/history.db")
    asyncio.run(repo.initialize())

    _workers: list[QThread] = []

    # -- Servers --

    def _reload_servers() -> None:
        servers = asyncio.run(repo.get_servers(limit=200))
        win.servers_view.update_servers(
            [
                {
                    "host": s.host,
                    "port": s.port,
                    "name": s.name,
                    "map_name": s.map_name,
                    "game": s.game,
                    "player_count": s.player_count,
                    "max_players": s.max_players,
                    "last_seen": "",
                }
                for s in servers
            ]
        )

    def _query_and_save(host: str, port: int, initial_name: str = "") -> None:
        qw = _QueryWorker(host, port)
        _workers.append(qw)

        def _on_result(info: dict[str, Any]) -> None:
            record = ServerRecord(
                host=host,
                port=port,
                first_seen=_time.time(),
                last_seen=_time.time(),
                name=info.get("name", "") or initial_name,
                map_name=info.get("map_name", ""),
                game=info.get("game", ""),
                player_count=info.get("player_count", 0),
                max_players=info.get("max_players", 0),
            )
            asyncio.run(repo.save_server(record))
            _reload_servers()

        qw.result.connect(_on_result)
        qw.error.connect(lambda m: logger.warning("Query failed: %s", m))
        qw.start()
        win.servers_view._status_label.setText(f"Querying {host}:{port}...")

    def _on_add_server(host: str, port: int, name: str) -> None:
        record = ServerRecord(
            host=host,
            port=port,
            first_seen=_time.time(),
            last_seen=_time.time(),
            name=name,
        )
        asyncio.run(repo.save_server(record))
        _query_and_save(host, port, name)
        _reload_servers()

    def _on_query_server(host: str, port: int) -> None:
        _query_and_save(host, port)

    win.servers_view.add_server_requested.connect(_on_add_server)
    win.servers_view.query_server_requested.connect(_on_query_server)
    win.servers_view.refresh_requested.connect(_reload_servers)

    # -- Probe --

    _probe_worker: _ProbeWorker | None = None

    def _on_probe_requested(
        host: str,
        port: int,
        _mode: str,
        interval: float,
        count: int,
    ) -> None:
        nonlocal _probe_worker
        pv = win.probe_view
        pv._start_btn.setEnabled(False)
        pv._stop_btn.setEnabled(True)
        pv._progress.setVisible(True)
        pv._progress.setMaximum(count)
        pv._progress.setValue(0)
        pv._latency_chart.clear_data()
        pv._loss_chart.clear_data()
        pv._jitter_chart.clear_data()
        pv._status.setText(f"Probing {host}:{port}...")
        pv._status.setStyleSheet("color: #cdd6f4;")

        _probe_worker = _ProbeWorker(host, port, count, interval)
        _probe_worker.progress.connect(_on_probe_progress)
        _probe_worker.finished.connect(_on_probe_finished)
        _probe_worker.start()

    def _on_probe_stop() -> None:
        nonlocal _probe_worker
        if _probe_worker is not None:
            _probe_worker.stop()
        pv = win.probe_view
        pv._start_btn.setEnabled(True)
        pv._stop_btn.setEnabled(False)
        pv._progress.setVisible(False)
        pv._status.setText("Stopped")
        pv._status.setStyleSheet("color: #facc15;")

    _loss_acc: list[float] = []

    def _on_probe_progress(current: int, total: int, rtt: float) -> None:
        pv = win.probe_view
        pv._progress.setValue(current)
        if rtt >= 0:
            pv._latency_chart.add_point(rtt)
            # Running loss calculation
            _loss_acc.append(0.0 if rtt >= 0 else 1.0)
            loss_pct = (
                (1.0 - sum(_loss_acc) / len(_loss_acc)) * 100 if _loss_acc else 0.0
            )
            pv._loss_chart.add_point(loss_pct)
            pv._status.setText(f"Probe {current}/{total} — RTT: {rtt:.1f}ms")
        else:
            _loss_acc.append(1.0)
            loss_pct = (
                (1.0 - sum(_loss_acc) / len(_loss_acc)) * 100 if _loss_acc else 0.0
            )
            pv._loss_chart.add_point(loss_pct)
            pv._status.setText(f"Probe {current}/{total} — timeout")

    def _on_probe_finished(result: dict[str, Any]) -> None:
        nonlocal _probe_worker, _loss_acc
        pv = win.probe_view
        pv._start_btn.setEnabled(True)
        pv._stop_btn.setEnabled(False)
        pv._progress.setVisible(False)
        _loss_acc = []
        avg = result.get("avg_rtt", 0)
        loss = result.get("loss", 0)
        jitter = result.get("jitter", 0)
        pv._status.setText(
            f"Done — RTT: {avg:.1f}ms  Loss: {loss}%  Jitter: {jitter:.1f}ms"
        )
        pv._status.setStyleSheet("color: #4ade80; font-weight: bold;")

        # Save measurement
        sent = result.get("sent", 0)
        received = result.get("received", 0)
        record = MeasurementRecord(
            target_host=result.get("host", ""),
            target_port=result.get("port", 0),
            timestamp=_time.time(),
            mode="normal",
            sent=sent,
            received=received,
            lost=sent - received,
            min_rtt=result.get("min_rtt", 0),
            max_rtt=result.get("max_rtt", 0),
            avg_rtt=avg,
            jitter=jitter,
        )
        asyncio.run(repo.save_measurement(record))
        _reload_history()
        _probe_worker = None

    win.probe_view.probe_requested.connect(_on_probe_requested)
    win.probe_view._stop_btn.clicked.connect(_on_probe_stop)

    # -- Traceroute --

    _trace_worker: _TracerouteWorker | None = None

    def _on_trace_requested(host: str, port: int) -> None:
        nonlocal _trace_worker
        tv = win.traceroute_view
        tv._trace_btn.setEnabled(False)
        tv._stop_btn.setEnabled(True)
        tv._progress.setVisible(True)
        tv._table.setRowCount(0)
        tv._status.setText(f"Tracing {host}:{port}...")
        tv._status.setStyleSheet("color: #cdd6f4;")

        _trace_worker = _TracerouteWorker(host, port)
        _trace_worker.hop.connect(tv.add_hop)
        _trace_worker.progress.connect(tv.set_progress)
        _trace_worker.finished.connect(_on_trace_finished)
        _trace_worker.error.connect(tv.on_error)
        _trace_worker.start()

    def _on_trace_stop() -> None:
        nonlocal _trace_worker
        if _trace_worker is not None:
            _trace_worker.stop()
        tv = win.traceroute_view
        tv._trace_btn.setEnabled(True)
        tv._stop_btn.setEnabled(False)
        tv._progress.setVisible(False)
        tv._status.setText("Stopped")
        tv._status.setStyleSheet("color: #facc15;")

    def _on_trace_finished(result: dict[str, Any]) -> None:
        nonlocal _trace_worker
        tv = win.traceroute_view
        tv._trace_btn.setEnabled(True)
        tv._stop_btn.setEnabled(False)
        tv._progress.setVisible(False)
        resolved = result.get("resolved", 0)
        total = result.get("total", 0)
        tv._status.setText(f"Complete: {resolved}/{total} hops resolved")
        tv._status.setStyleSheet("color: #4ade80; font-weight: bold;")
        _trace_worker = None

    win.traceroute_view.traceroute_requested.connect(_on_trace_requested)
    win.traceroute_view._stop_btn.clicked.connect(_on_trace_stop)

    # -- Dashboard --

    def _on_dashboard_refresh() -> None:
        servers = asyncio.run(repo.get_servers(limit=200))
        win.dashboard_view.update_stat("servers", str(len(servers)))
        measurements = asyncio.run(repo.get_measurements(limit=1000))
        win.dashboard_view.update_stat("measurements", str(len(measurements)))
        if measurements:
            avg_rtt = sum(m.avg_rtt for m in measurements) / len(measurements)
            avg_loss = sum(m.loss_rate for m in measurements) / len(measurements) * 100
            win.dashboard_view.update_stat("avg_rtt", f"{avg_rtt:.1f} ms")
            win.dashboard_view.update_stat("avg_loss", f"{avg_loss:.1f}%")
            win.dashboard_view.clear_charts()
            for m in measurements[-50:]:
                if m.avg_rtt > 0:
                    win.dashboard_view.add_latency_point(m.avg_rtt)
                win.dashboard_view.add_loss_point(m.loss_rate * 100)

    def _on_dashboard_export() -> None:
        path, _ = QFileDialog.getSaveFileName(
            win,
            "Export Report",
            "report.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        measurements = asyncio.run(repo.get_measurements(limit=10000))
        import json

        data = {
            "measurements": [
                {
                    "host": m.target_host,
                    "port": m.target_port,
                    "mode": m.mode,
                    "sent": m.sent,
                    "received": m.received,
                    "lost": m.lost,
                    "avg_rtt": m.avg_rtt,
                    "jitter": m.jitter,
                    "timestamp": m.timestamp,
                }
                for m in measurements
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        win.dashboard_view._export_btn.setText("Exported!")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(
            2000,
            lambda: win.dashboard_view._export_btn.setText("Export"),
        )

    win.dashboard_view._refresh_btn.clicked.connect(_on_dashboard_refresh)
    win.dashboard_view._export_btn.clicked.connect(_on_dashboard_export)

    # -- History --

    def _reload_history() -> None:
        measurements = asyncio.run(repo.get_measurements(limit=100))
        win.history_view.update_measurements(
            [
                {
                    "target_host": m.target_host,
                    "target_port": m.target_port,
                    "mode": m.mode,
                    "sent": m.sent,
                    "received": m.received,
                    "lost": m.lost,
                    "avg_rtt": m.avg_rtt,
                    "jitter": m.jitter,
                    "quality_grade": m.quality_grade,
                    "duration_seconds": m.duration_seconds,
                }
                for m in measurements
            ]
        )

    # Initial load
    _reload_servers()
    _on_dashboard_refresh()
    _reload_history()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Application entry point."""
    setup_logging(level=logging.INFO)
    logger.info("UDP Network Intelligence v6 starting")

    app = QApplication(sys.argv)

    from uni.view.main_window import MainWindow
    from uni.view.styles.theme import ThemeManager

    ThemeManager().apply("dark")

    window = MainWindow()
    _wire_signals(window)
    window.show()

    logger.info("GUI ready")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
