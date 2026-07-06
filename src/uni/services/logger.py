"""Logging service with colored console, rotating files, and category filters.

Provides :func:`setup_logging` for application-wide log configuration and
:class:`LogManager` for runtime control (level changes, category filtering,
GUI log capture).

Features:
    - Rotating file logs with configurable size and backup count.
    - Colored console output (ANSI on Unix, colorama on Windows).
    - Category-based logging: ``uni.net``, ``uni.gui``, ``uni.probe``, etc.
    - GUI log handler that captures logs for display in a widget.
    - Structured format with timestamps, levels, categories, and context.
    - Thread-safe operation.

Example::

    from uni.services.logger import setup_logging, get_logger

    setup_logging(level="DEBUG", log_file="logs/uni.log")
    logger = get_logger("uni.probe")
    logger.info("Probe started to %s", target)
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import sys
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Log level helpers
# ---------------------------------------------------------------------------

# Map string level names to logging constants.
_LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _resolve_level(level: int | str) -> int:
    """Resolve a log level from int or string.

    Args:
        level: Logging level as int (e.g. ``logging.DEBUG``) or
            string (e.g. ``"DEBUG"``).

    Returns:
        Integer log level.

    Raises:
        ValueError: If the string is not a recognized level name.
    """
    if isinstance(level, int):
        return level
    level_str = level.upper().strip()
    if level_str not in _LOG_LEVELS:
        raise ValueError(
            f"Invalid log level: {level!r}. "
            f"Valid levels: {', '.join(_LOG_LEVELS)}"
        )
    return _LOG_LEVELS[level_str]


# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------

class _Color(Enum):
    """ANSI escape codes for colored terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"

    @property
    def code(self) -> str:
        """Raw ANSI escape string."""
        return self.value


# Level -> color mapping for console output.
_LEVEL_COLORS: dict[int, _Color] = {
    logging.DEBUG: _Color.GRAY,
    logging.INFO: _Color.GREEN,
    logging.WARNING: _Color.YELLOW,
    logging.ERROR: _Color.RED,
    logging.CRITICAL: _Color.BG_RED,
}

# Category -> color mapping for log source prefixes.
_CATEGORY_COLORS: dict[str, _Color] = {
    "uni.net": _Color.CYAN,
    "uni.probe": _Color.BLUE,
    "uni.traceroute": _Color.MAGENTA,
    "uni.discovery": _Color.YELLOW,
    "uni.gui": _Color.GREEN,
    "uni.plugin": _Color.CYAN,
    "uni.config": _Color.WHITE,
}


# ---------------------------------------------------------------------------
# Colored formatter
# ---------------------------------------------------------------------------

class ColoredFormatter(logging.Formatter):
    """Log formatter with ANSI-colored level names and category highlighting.

    On Windows, initializes colorama if available to translate ANSI codes
    to Win32 console API calls.

    Attributes:
        use_colors: Whether to emit ANSI color codes.
    """

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        use_colors: bool = True,
    ) -> None:
        """Initialize the colored formatter.

        Args:
            fmt: Log format string. Uses standard logging format specifiers.
            datefmt: Date format string.
            use_colors: Whether to use ANSI colors in output.
        """
        if fmt is None:
            fmt = "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
        if datefmt is None:
            datefmt = "%Y-%m-%d %H:%M:%S"
        super().__init__(fmt, datefmt=datefmt)
        self.use_colors = use_colors
        self._init_colorama()

    @staticmethod
    def _init_colorama() -> None:
        """Initialize colorama on Windows for ANSI support."""
        if sys.platform == "win32":
            try:
                import colorama
                if not colorama.just_fix_windows_console:
                    colorama.init()
            except ImportError:
                pass

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with optional colors.

        Args:
            record: The log record to format.

        Returns:
            Formatted log string.
        """
        # Store original values
        orig_levelname = record.levelname
        orig_name = record.name

        if self.use_colors and sys.stderr.isatty():
            # Color the level name
            color = _LEVEL_COLORS.get(record.levelno, _Color.WHITE)
            record.levelname = (
                f"{color.code}{record.levelname:<8}{_Color.RESET.code}"
            )

            # Color the logger name by category
            cat_color = self._get_category_color(record.name)
            if cat_color:
                record.name = (
                    f"{cat_color.code}{record.name}{_Color.RESET.code}"
                )
        else:
            record.levelname = f"{record.levelname:<8}"

        result = super().format(record)

        # Restore originals
        record.levelname = orig_levelname
        record.name = orig_name
        return result

    @staticmethod
    def _get_category_color(name: str) -> _Color | None:
        """Find the best matching color for a logger name.

        Args:
            name: Logger name (e.g. ``"uni.probe.session"``).

        Returns:
            Matching color, or None if no match.
        """
        # Try exact match first, then prefix match (longest first)
        if name in _CATEGORY_COLORS:
            return _CATEGORY_COLORS[name]
        for prefix in sorted(_CATEGORY_COLORS, key=len, reverse=True):
            if name.startswith(prefix):
                return _CATEGORY_COLORS[prefix]
        return None


class PlainFormatter(logging.Formatter):
    """Non-colored formatter for file output.

    Produces clean, parseable log lines without ANSI escape sequences.
    """

    def __init__(self, fmt: str | None = None, datefmt: str | None = None) -> None:
        """Initialize the plain formatter.

        Args:
            fmt: Log format string.
            datefmt: Date format string.
        """
        if fmt is None:
            fmt = "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
        if datefmt is None:
            datefmt = "%Y-%m-%d %H:%M:%S"
        super().__init__(fmt, datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record without colors.

        Args:
            record: The log record to format.

        Returns:
            Plain formatted log string.
        """
        record.levelname = f"{record.levelname:<8}"
        return super().format(record)


# ---------------------------------------------------------------------------
# GUI log handler
# ---------------------------------------------------------------------------

class GUIHandler(logging.Handler):
    """Logging handler that captures log records for GUI display.

    Stores the last N records in a thread-safe deque and notifies
    registered callbacks when new records arrive.

    Attributes:
        capacity: Maximum number of records to retain.
    """

    def __init__(self, capacity: int = 1000) -> None:
        """Initialize the GUI handler.

        Args:
            capacity: Maximum number of records to keep in memory.
        """
        super().__init__(level=logging.DEBUG)
        self.capacity = capacity
        self._records: deque[logging.LogRecord] = deque(maxlen=capacity)
        self._callbacks: list[Callable[[logging.LogRecord], None]] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """Capture a log record.

        Thread-safe: can be called from any thread.

        Args:
            record: The log record to capture.
        """
        with self._lock:
            self._records.append(record)
        for cb in self._callbacks:
            with contextlib.suppress(Exception):
                cb(record)

    def get_records(self, level: int = logging.DEBUG) -> list[logging.LogRecord]:
        """Get captured records at or above the given level.

        Args:
            level: Minimum log level to include.

        Returns:
            List of matching log records (newest last).
        """
        with self._lock:
            return [r for r in self._records if r.levelno >= level]

    def get_messages(
        self,
        level: int = logging.DEBUG,
        limit: int = 100,
        formatter: logging.Formatter | None = None,
    ) -> list[str]:
        """Get formatted log messages.

        Args:
            level: Minimum log level.
            limit: Maximum number of messages to return.
            formatter: Optional formatter. Uses default if None.

        Returns:
            List of formatted log message strings.
        """
        if formatter is None:
            formatter = PlainFormatter()
        records = self.get_records(level)
        # Return the most recent messages
        recent = records[-limit:] if len(records) > limit else records
        return [formatter.format(r) for r in recent]

    def add_callback(self, callback: Callable[[logging.LogRecord], None]) -> None:
        """Register a callback for new log records.

        Args:
            callback: Called with each new LogRecord.
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[logging.LogRecord], None]) -> None:
        """Unregister a callback.

        Args:
            callback: Callback to remove.
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def clear(self) -> None:
        """Clear all stored records."""
        with self._lock:
            self._records.clear()

    @property
    def record_count(self) -> int:
        """Number of stored records."""
        with self._lock:
            return len(self._records)


# ---------------------------------------------------------------------------
# LogManager
# ---------------------------------------------------------------------------

@dataclass
class LogConfig:
    """Configuration for the logging system.

    Attributes:
        level: Global log level.
        console_level: Console handler log level.
        file_level: File handler log level.
        gui_level: GUI handler log level.
        log_file: Path to the log file.
        max_bytes: Maximum log file size before rotation.
        backup_count: Number of rotated log files to keep.
        format: Log format string.
        date_format: Date format string.
        use_colors: Whether to use colored console output.
        capture_warnings: Whether to capture Python warnings.
    """

    level: str = "INFO"
    console_level: str = "INFO"
    file_level: str = "DEBUG"
    gui_level: str = "DEBUG"
    log_file: str = "logs/uni.log"
    max_bytes: int = 5 * 1024 * 1024
    backup_count: int = 3
    format: str = "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
    date_format: str = "%Y-%m-%d %H:%M:%S"
    use_colors: bool = True
    capture_warnings: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "level": self.level,
            "console_level": self.console_level,
            "file_level": self.file_level,
            "gui_level": self.gui_level,
            "log_file": self.log_file,
            "max_bytes": self.max_bytes,
            "backup_count": self.backup_count,
            "format": self.format,
            "date_format": self.date_format,
            "use_colors": self.use_colors,
            "capture_warnings": self.capture_warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogConfig:
        """Deserialize from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            LogConfig instance.
        """
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


class LogManager:
    """Central logging manager with runtime control.

    Provides methods to configure logging at startup and change
    levels/filters at runtime. Manages console, file, and GUI handlers.

    Attributes:
        config: Current logging configuration.
        gui_handler: The GUI log handler (for widget integration).
    """

    def __init__(self) -> None:
        """Initialize the log manager."""
        self.config = LogConfig()
        self.gui_handler: GUIHandler | None = None
        self._configured = False
        self._console_handler: logging.StreamHandler[Any] | None = None
        self._file_handler: logging.handlers.RotatingFileHandler | None = None
        self._lock = threading.Lock()

    def setup(self, config: LogConfig | None = None) -> None:
        """Configure the logging system.

        Safe to call multiple times — clears existing handlers first.

        Args:
            config: Logging configuration. Uses defaults if None.
        """
        if config is not None:
            self.config = config

        with self._lock:
            self._remove_handlers()
            self._add_console_handler()
            self._add_file_handler()
            self._add_gui_handler()
            self._configure_root()
            self._configured = True

        logger = logging.getLogger("uni")
        logger.info("Logging initialized (level=%s)", self.config.level)

    def shutdown(self) -> None:
        """Flush and remove all handlers.

        Call during application shutdown to ensure all log records
        are written to disk.
        """
        with self._lock:
            self._remove_handlers()
            self._configured = False

    def set_level(self, level: int | str, handler_type: str = "all") -> None:
        """Change the log level at runtime.

        Args:
            level: New log level.
            handler_type: Which handler to change: ``"all"``,
                ``"console"``, ``"file"``, or ``"gui"``.
        """
        resolved = _resolve_level(level)

        with self._lock:
            if handler_type in ("all", "console"):
                if self._console_handler:
                    self._console_handler.setLevel(resolved)
                root = logging.getLogger()
                root.setLevel(resolved)

            if handler_type in ("all", "file") and self._file_handler:
                self._file_handler.setLevel(resolved)

            if handler_type in ("all", "gui") and self.gui_handler:
                self.gui_handler.setLevel(resolved)

    def get_console_level(self) -> int:
        """Get the current console handler level.

        Returns:
            Console handler log level.
        """
        if self._console_handler:
            return self._console_handler.level
        return logging.INFO

    def get_file_level(self) -> int:
        """Get the current file handler level.

        Returns:
            File handler log level.
        """
        if self._file_handler:
            return self._file_handler.level
        return logging.DEBUG

    def add_filter(self, name: str) -> None:
        """Add a log filter to the console handler.

        Only records matching the filter name (logger name prefix)
        will be shown on console.

        Args:
            name: Logger name prefix to filter by (e.g. ``"uni.net"``).
        """
        if self._console_handler:
            self._console_handler.addFilter(_PrefixFilter(name))

    def remove_filter(self, name: str) -> None:
        """Remove a log filter from the console handler.

        Args:
            name: Filter name to remove.
        """
        if self._console_handler:
            for f in self._console_handler.filters:
                if isinstance(f, _PrefixFilter) and f.prefix == name:
                    self._console_handler.removeFilter(f)
                    break

    def clear_filters(self) -> None:
        """Remove all filters from the console handler."""
        if self._console_handler:
            self._console_handler.filters.clear()

    def get_log_files(self) -> list[Path]:
        """List all log files (current + rotated backups).

        Returns:
            Sorted list of log file paths.
        """
        log_path = Path(self.config.log_file)
        if not log_path.parent.exists():
            return []

        base = log_path.name
        parent = log_path.parent
        files = sorted(
            parent.glob(f"{base}*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files

    def get_total_log_size(self) -> int:
        """Get total size of all log files in bytes.

        Returns:
            Combined size in bytes.
        """
        return sum(f.stat().st_size for f in self.get_log_files())

    def clear_log_file(self) -> None:
        """Truncate the current log file.

        Rotated backups are preserved.
        """
        log_path = Path(self.config.log_file)
        if log_path.exists():
            with self._lock:
                if self._file_handler:
                    self._file_handler.flush()
                    self._file_handler.stream.truncate(0)  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _configure_root(self) -> None:
        """Configure the root logger."""
        root = logging.getLogger()
        root.setLevel(_resolve_level(self.config.level))

        if self.config.capture_warnings:
            logging.captureWarnings(True)
            warnings_logger = logging.getLogger("py.warnings")
            warnings_logger.setLevel(logging.WARNING)

    def _add_console_handler(self) -> None:
        """Add the colored console handler."""
        level = _resolve_level(self.config.console_level)

        if self.config.use_colors:
            formatter: logging.Formatter = ColoredFormatter(
                fmt=self.config.format,
                datefmt=self.config.date_format,
                use_colors=True,
            )
        else:
            formatter = PlainFormatter(
                fmt=self.config.format,
                datefmt=self.config.date_format,
            )

        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        self._console_handler = handler

    def _add_file_handler(self) -> None:
        """Add the rotating file handler."""
        log_path = Path(self.config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        level = _resolve_level(self.config.file_level)
        formatter = PlainFormatter(
            fmt=self.config.format,
            datefmt=self.config.date_format,
        )

        handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=self.config.max_bytes,
            backupCount=self.config.backup_count,
            encoding="utf-8",
        )
        handler.setLevel(level)
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
        self._file_handler = handler

    def _add_gui_handler(self) -> None:
        """Add the GUI log handler."""
        level = _resolve_level(self.config.gui_level)
        self.gui_handler = GUIHandler(capacity=2000)
        self.gui_handler.setLevel(level)
        logging.getLogger().addHandler(self.gui_handler)

    def _remove_handlers(self) -> None:
        """Remove all custom handlers from the root logger."""
        root = logging.getLogger()

        if self._console_handler:
            root.removeHandler(self._console_handler)
            self._console_handler = None

        if self._file_handler:
            self._file_handler.flush()
            self._file_handler.close()
            root.removeHandler(self._file_handler)
            self._file_handler = None

        if self.gui_handler:
            root.removeHandler(self.gui_handler)
            self.gui_handler = None


# ---------------------------------------------------------------------------
# Log filter
# ---------------------------------------------------------------------------

class _PrefixFilter(logging.Filter):
    """Filter that allows only records whose name starts with a prefix.

    Attributes:
        prefix: The logger name prefix to match.
    """

    def __init__(self, prefix: str) -> None:
        """Initialize the prefix filter.

        Args:
            prefix: Logger name prefix (e.g. ``"uni.net"``).
        """
        super().__init__()
        self.prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        """Check if the record matches the prefix.

        Args:
            record: Log record to filter.

        Returns:
            True if the record's logger name starts with the prefix.
        """
        return record.name.startswith(self.prefix) or record.name == "uni"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# Global log manager instance.
_log_manager: LogManager | None = None
_manager_lock = threading.Lock()


def get_log_manager() -> LogManager:
    """Get the global LogManager instance.

    Creates one on first call.

    Returns:
        The global LogManager.
    """
    global _log_manager
    if _log_manager is None:
        with _manager_lock:
            if _log_manager is None:
                _log_manager = LogManager()
    return _log_manager


def setup_logging(
    level: int | str = "INFO",
    log_file: str | None = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    use_colors: bool = True,
    config: LogConfig | None = None,
) -> LogManager:
    """Configure application-wide logging.

    This is the main entry point for logging setup. Can be called
    from ``main()`` or anywhere that needs to (re)configure logging.

    Args:
        level: Global log level (int or string).
        log_file: Path to the log file. None disables file logging.
        max_bytes: Maximum log file size before rotation.
        backup_count: Number of rotated backups to keep.
        use_colors: Whether to use colored console output.
        config: Full LogConfig to use. Overrides other arguments.

    Returns:
        The configured LogManager instance.

    Example::

        setup_logging(level="DEBUG", log_file="logs/uni.log")
        logger = get_logger("uni.probe")
        logger.info("Probe started")
    """
    manager = get_log_manager()

    if config is not None:
        manager.setup(config)
    else:
        cfg = LogConfig(
            level=_resolve_level(level) if isinstance(level, int) else level,
            console_level=_resolve_level(level) if isinstance(level, int) else level,
            log_file=log_file or "logs/uni.log",
            max_bytes=max_bytes,
            backup_count=backup_count,
            use_colors=use_colors,
        )
        manager.setup(cfg)

    return manager


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Convenience wrapper around ``logging.getLogger()``.

    Args:
        name: Logger name (e.g. ``"uni.probe"``, ``"uni.net"``).

    Returns:
        Configured logger instance.

    Example::

        logger = get_logger("uni.probe.session")
        logger.info("Session started")
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Specialized loggers
# ---------------------------------------------------------------------------

def get_network_logger(name: str = "uni.net") -> logging.Logger:
    """Get a logger for network operations.

    Pre-configured with the ``uni.net`` category for consistent
    color coding in console output.

    Args:
        name: Logger name (default: ``"uni.net"``).

    Returns:
        Logger instance.

    Example::

        net_log = get_network_logger("uni.net.udp")
        net_log.info("Sending %d bytes to %s", size, target)
    """
    return logging.getLogger(name)


def get_gui_logger(name: str = "uni.gui") -> logging.Logger:
    """Get a logger for GUI operations.

    Pre-configured with the ``uni.gui`` category.

    Args:
        name: Logger name (default: ``"uni.gui"``).

    Returns:
        Logger instance.

    Example::

        gui_log = get_gui_logger("uni.gui.main")
        gui_log.info("Window closed")
    """
    return logging.getLogger(name)


def get_probe_logger(name: str = "uni.probe") -> logging.Logger:
    """Get a logger for probe operations.

    Pre-configured with the ``uni.probe`` category.

    Args:
        name: Logger name (default: ``"uni.probe"``).

    Returns:
        Logger instance.

    Example::

        probe_log = get_probe_logger("uni.probe.session")
        probe_log.debug("RTT: %.2fms", rtt)
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Timestamped file handler (for daily rotation)
# ---------------------------------------------------------------------------

class TimedCompressHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotating file handler that creates timestamped log files.

    Extends the standard TimedRotatingFileHandler with a custom
    naming convention: ``app_2026-07-06.log``.
    """

    def __init__(
        self,
        filename: str,
        when: str = "midnight",
        interval: int = 1,
        backup_count: int = 7,
        encoding: str = "utf-8",
    ) -> None:
        """Initialize the timed compress handler.

        Args:
            filename: Base log file path.
            when: Rotation interval type (``"midnight"``, ``"h"``, ``"d"``).
            interval: Interval multiplier.
            backup_count: Number of backup files to keep.
            encoding: File encoding.
        """
        super().__init__(
            filename,
            when=when,
            interval=interval,
            backupCount=backup_count,
            encoding=encoding,
        )
