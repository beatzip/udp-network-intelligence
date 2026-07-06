"""OS-specific helpers — admin check, platform detection."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def is_admin() -> bool:
    """Check if the process has administrator privileges.

    On Windows, checks for admin token.
    On Unix, checks for effective UID 0.
    """
    if is_windows():
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll is not None:
            return bool(windll.shell32.IsUserAnAdmin())
        return False
    else:
        return int(os.geteuid()) == 0  # type: ignore[attr-defined]


def get_executable_dir() -> Path:
    """Get the directory of the running executable.

    Returns:
        Path to the directory containing the executable.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller / Nuitka bundle
        return Path(sys.executable).parent
    # Normal Python execution
    return Path(__file__).resolve().parent.parent.parent.parent


def get_data_dir() -> Path:
    """Get the application data directory.

    Returns:
        Path to the data directory (next to executable or in home).
    """
    exe_dir = get_executable_dir()
    data_dir = exe_dir / "data"
    if data_dir.exists() or (exe_dir / "uni.toml").exists():
        return data_dir

    # Fallback to user home
    home = Path.home()
    app_data = home / ".uni"
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data


def get_appdata_dir() -> Path:
    """Get Windows AppData directory for the application.

    Returns:
        Path to %APPDATA%/UNI/ or equivalent.
    """
    if is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = Path(appdata) / "UNI"
            path.mkdir(parents=True, exist_ok=True)
            return path
    return get_data_dir()
