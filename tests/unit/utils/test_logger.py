"""Tests for uni.services.logger module — logging system."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from uni.services.logger import (
    ColoredFormatter,
    GUIHandler,
    LogConfig,
    LogManager,
    PlainFormatter,
    _PrefixFilter,
    _resolve_level,
    get_gui_logger,
    get_logger,
    get_network_logger,
    get_probe_logger,
    setup_logging,
)

# ---------------------------------------------------------------------------
# _resolve_level
# ---------------------------------------------------------------------------


class TestResolveLevel:
    """Tests for _resolve_level()."""

    def test_int_passthrough(self) -> None:
        assert _resolve_level(logging.DEBUG) == logging.DEBUG

    def test_string_debug(self) -> None:
        assert _resolve_level("DEBUG") == logging.DEBUG

    def test_string_info(self) -> None:
        assert _resolve_level("INFO") == logging.INFO

    def test_string_warning(self) -> None:
        assert _resolve_level("WARNING") == logging.WARNING

    def test_string_error(self) -> None:
        assert _resolve_level("ERROR") == logging.ERROR

    def test_string_critical(self) -> None:
        assert _resolve_level("CRITICAL") == logging.CRITICAL

    def test_lowercase_string(self) -> None:
        assert _resolve_level("debug") == logging.DEBUG

    def test_invalid_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid log level"):
            _resolve_level("INVALID")


# ---------------------------------------------------------------------------
# LogConfig
# ---------------------------------------------------------------------------


class TestLogConfig:
    """Tests for LogConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = LogConfig()
        assert cfg.level == "INFO"
        assert cfg.console_level == "INFO"
        assert cfg.file_level == "DEBUG"
        assert cfg.log_file == "logs/uni.log"
        assert cfg.max_bytes == 5 * 1024 * 1024
        assert cfg.backup_count == 3
        assert cfg.use_colors is True

    def test_to_dict(self) -> None:
        cfg = LogConfig()
        d = cfg.to_dict()
        assert d["level"] == "INFO"
        assert d["log_file"] == "logs/uni.log"
        assert "max_bytes" in d
        assert "backup_count" in d

    def test_from_dict(self) -> None:
        data = {"level": "DEBUG", "log_file": "test.log", "use_colors": False}
        cfg = LogConfig.from_dict(data)
        assert cfg.level == "DEBUG"
        assert cfg.log_file == "test.log"
        assert cfg.use_colors is False

    def test_from_dict_unknown_keys_ignored(self) -> None:
        data = {"level": "WARNING", "unknown_key": "value"}
        cfg = LogConfig.from_dict(data)
        assert cfg.level == "WARNING"


# ---------------------------------------------------------------------------
# PlainFormatter
# ---------------------------------------------------------------------------


class TestPlainFormatter:
    """Tests for PlainFormatter."""

    def test_format(self) -> None:
        formatter = PlainFormatter()
        record = logging.LogRecord(
            name="uni.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "INFO" in result
        assert "uni.test" in result
        assert "Hello world" in result

    def test_no_colors(self) -> None:
        formatter = PlainFormatter()
        record = logging.LogRecord(
            name="uni.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "\033[" not in result  # No ANSI codes


# ---------------------------------------------------------------------------
# GUIHandler
# ---------------------------------------------------------------------------


class TestGUIHandler:
    """Tests for GUIHandler."""

    def test_emit_and_retrieve(self) -> None:
        handler = GUIHandler(capacity=100)
        record = logging.LogRecord(
            name="uni.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        records = handler.get_records()
        assert len(records) == 1
        assert records[0].getMessage() == "Test message"

    def test_capacity_limit(self) -> None:
        handler = GUIHandler(capacity=5)
        for i in range(10):
            record = logging.LogRecord(
                name="uni.test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg=f"Message {i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        records = handler.get_records()
        assert len(records) == 5
        # Should contain the last 5 messages
        assert records[0].getMessage() == "Message 5"
        assert records[-1].getMessage() == "Message 9"

    def test_level_filter(self) -> None:
        handler = GUIHandler()
        for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
            record = logging.LogRecord(
                name="uni.test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg=f"Level {level}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)

        warning_and_above = handler.get_records(level=logging.WARNING)
        assert len(warning_and_above) == 2

    def test_get_messages(self) -> None:
        handler = GUIHandler()
        record = logging.LogRecord(
            name="uni.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Formatted message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        messages = handler.get_messages()
        assert len(messages) == 1
        assert "Formatted message" in messages[0]

    def test_callback(self) -> None:
        handler = GUIHandler()
        received: list[logging.LogRecord] = []
        handler.add_callback(lambda r: received.append(r))

        record = logging.LogRecord(
            name="uni.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Callback test",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert len(received) == 1

    def test_remove_callback(self) -> None:
        handler = GUIHandler()
        received: list[logging.LogRecord] = []

        def capture(r: logging.LogRecord) -> None:
            received.append(r)

        handler.add_callback(capture)
        handler.remove_callback(capture)

        record = logging.LogRecord(
            name="uni.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="No callback",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert len(received) == 0

    def test_clear(self) -> None:
        handler = GUIHandler()
        record = logging.LogRecord(
            name="uni.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="To clear",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert handler.record_count == 1
        handler.clear()
        assert handler.record_count == 0

    def test_thread_safety(self) -> None:
        handler = GUIHandler(capacity=500)

        def emit_records(count: int) -> None:
            for i in range(count):
                record = logging.LogRecord(
                    name="uni.test",
                    level=logging.INFO,
                    pathname="test.py",
                    lineno=1,
                    msg=f"Thread msg {i}",
                    args=(),
                    exc_info=None,
                )
                handler.emit(record)

        threads = [threading.Thread(target=emit_records, args=(100,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert handler.record_count == 500


# ---------------------------------------------------------------------------
# _PrefixFilter
# ---------------------------------------------------------------------------


class TestPrefixFilter:
    """Tests for _PrefixFilter."""

    def test_matching_prefix(self) -> None:
        f = _PrefixFilter("uni.net")
        record = logging.LogRecord(
            name="uni.net.udp",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_exact_match(self) -> None:
        f = _PrefixFilter("uni.net")
        record = logging.LogRecord(
            name="uni.net",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True

    def test_non_matching(self) -> None:
        f = _PrefixFilter("uni.net")
        record = logging.LogRecord(
            name="uni.gui",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is False

    def test_uni_root_always_passes(self) -> None:
        f = _PrefixFilter("uni.net")
        record = logging.LogRecord(
            name="uni",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        assert f.filter(record) is True


# ---------------------------------------------------------------------------
# LogManager
# ---------------------------------------------------------------------------


class TestLogManager:
    """Tests for LogManager."""

    def test_setup(self) -> None:
        manager = LogManager()
        cfg = LogConfig(log_file="logs/test_uni.log", use_colors=False)
        manager.setup(cfg)
        assert manager._configured is True
        manager.shutdown()

    def test_shutdown(self) -> None:
        manager = LogManager()
        manager.setup(LogConfig(log_file="logs/test_uni.log", use_colors=False))
        manager.shutdown()
        assert manager._configured is False

    def test_set_level(self) -> None:
        manager = LogManager()
        manager.setup(LogConfig(log_file="logs/test_uni.log", use_colors=False))
        manager.set_level(logging.DEBUG)
        assert manager.get_console_level() == logging.DEBUG
        manager.shutdown()

    def test_set_level_string(self) -> None:
        manager = LogManager()
        manager.setup(LogConfig(log_file="logs/test_uni.log", use_colors=False))
        manager.set_level("WARNING")
        assert manager.get_console_level() == logging.WARNING
        manager.shutdown()

    def test_add_remove_filter(self) -> None:
        manager = LogManager()
        manager.setup(LogConfig(log_file="logs/test_uni.log", use_colors=False))
        manager.add_filter("uni.net")
        assert len(manager._console_handler.filters) == 1  # type: ignore[union-attr]
        manager.remove_filter("uni.net")
        assert len(manager._console_handler.filters) == 0  # type: ignore[union-attr]
        manager.shutdown()

    def test_clear_filters(self) -> None:
        manager = LogManager()
        manager.setup(LogConfig(log_file="logs/test_uni.log", use_colors=False))
        manager.add_filter("uni.net")
        manager.add_filter("uni.gui")
        manager.clear_filters()
        assert len(manager._console_handler.filters) == 0  # type: ignore[union-attr]
        manager.shutdown()

    def test_get_log_files(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        manager = LogManager()
        manager.setup(LogConfig(log_file=str(log_file), use_colors=False))

        logger = logging.getLogger("uni.test.files")
        logger.info("Test log file listing")

        files = manager.get_log_files()
        assert len(files) >= 1
        manager.shutdown()

    def test_total_log_size(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        manager = LogManager()
        manager.setup(LogConfig(log_file=str(log_file), use_colors=False))

        logger = logging.getLogger("uni.test.size")
        logger.info("Test log size calculation")

        size = manager.get_total_log_size()
        assert size > 0
        manager.shutdown()


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Tests for setup_logging() convenience function."""

    def test_basic_setup(self) -> None:
        manager = setup_logging(level="DEBUG", use_colors=False)
        assert isinstance(manager, LogManager)
        manager.shutdown()

    def test_with_log_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "app.log"
        manager = setup_logging(
            level="INFO",
            log_file=str(log_file),
            use_colors=False,
        )
        logger = get_logger("uni.test.setup")
        logger.info("Test setup")
        assert log_file.exists()
        manager.shutdown()

    def test_with_config(self, tmp_path: Path) -> None:
        cfg = LogConfig(
            level="WARNING",
            log_file=str(tmp_path / "configured.log"),
            use_colors=False,
        )
        manager = setup_logging(config=cfg)
        assert isinstance(manager, LogManager)
        manager.shutdown()

    def test_returns_manager(self) -> None:
        manager = setup_logging(level="INFO", use_colors=False)
        assert isinstance(manager, LogManager)
        manager.shutdown()


# ---------------------------------------------------------------------------
# get_logger helpers
# ---------------------------------------------------------------------------


class TestGetLoggers:
    """Tests for specialized logger getters."""

    def test_get_logger(self) -> None:
        logger = get_logger("uni.test")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "uni.test"

    def test_get_network_logger(self) -> None:
        logger = get_network_logger("uni.net.custom")
        assert logger.name == "uni.net.custom"

    def test_get_network_logger_default(self) -> None:
        logger = get_network_logger()
        assert logger.name == "uni.net"

    def test_get_gui_logger(self) -> None:
        logger = get_gui_logger("uni.gui.custom")
        assert logger.name == "uni.gui.custom"

    def test_get_probe_logger(self) -> None:
        logger = get_probe_logger("uni.probe.custom")
        assert logger.name == "uni.probe.custom"


# ---------------------------------------------------------------------------
# Integration: logging works end-to-end
# ---------------------------------------------------------------------------


class TestLoggingIntegration:
    """Integration tests for the logging system."""

    def test_logs_appear_in_file(self, tmp_path: Path) -> None:
        log_file = tmp_path / "integration.log"
        manager = setup_logging(
            level="DEBUG",
            log_file=str(log_file),
            use_colors=False,
        )

        logger = get_logger("uni.integration")
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        # Force flush
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = log_file.read_text(encoding="utf-8")
        assert "Debug message" in content
        assert "Info message" in content
        assert "Warning message" in content
        assert "Error message" in content
        manager.shutdown()

    def test_log_rotation(self, tmp_path: Path) -> None:
        log_file = tmp_path / "rotate.log"
        manager = setup_logging(
            level="DEBUG",
            log_file=str(log_file),
            max_bytes=500,  # Very small for testing rotation
            backup_count=2,
            use_colors=False,
        )

        logger = get_logger("uni.rotation")
        # Write enough to trigger rotation
        for i in range(50):
            logger.info("Log line %d with some padding data here", i)

        for handler in logging.getLogger().handlers:
            handler.flush()

        files = list(tmp_path.glob("rotate.log*"))
        assert len(files) >= 2  # main + at least one backup
        manager.shutdown()

    def test_gui_handler_captures_logs(self, tmp_path: Path) -> None:
        manager = setup_logging(
            level="DEBUG",
            log_file=str(tmp_path / "gui_test.log"),
            use_colors=False,
        )

        assert manager.gui_handler is not None
        logger = get_logger("uni.gui.test")
        logger.info("GUI capture test")

        for handler in logging.getLogger().handlers:
            handler.flush()

        messages = manager.gui_handler.get_messages(level=logging.INFO)
        gui_messages = [m for m in messages if "GUI capture test" in m]
        assert len(gui_messages) >= 1
        manager.shutdown()

    def test_network_category_color(self) -> None:
        from uni.services.logger import _CATEGORY_COLORS

        formatter = ColoredFormatter(use_colors=True)
        color = formatter._get_category_color("uni.net.udp")
        assert color is not None
        assert color == _CATEGORY_COLORS["uni.net"]
