"""Build script — create Windows EXE with PyInstaller.

Usage:
    python build.py

Produces: dist/uni.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def build() -> None:
    """Run PyInstaller to create a single-file Windows executable."""
    root = Path(__file__).parent
    src = root / "src"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "uni",
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        # Include the uni package
        "--paths", str(src),
        # Hidden imports that PyInstaller may miss
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "pyqtgraph",
        "--hidden-import", "numpy",
        # Data files
        "--add-data", f"{root / 'uni.toml'};.",
        "--add-data", f"{root / 'src' / 'uni' / 'view' / 'resources' / 'styles'};uni/view/resources/styles",
        "--add-data", f"{root / 'src' / 'uni' / 'plugins' / 'builtins'};uni/plugins/builtins",
        # Entry point
        str(src / "uni" / "app" / "main.py"),
    ]

    print("Building uni.exe ...")
    print(f"Command: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(root))

    if result.returncode == 0:
        exe_path = root / "dist" / "uni.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\nBuild successful: {exe_path}")
            print(f"Size: {size_mb:.1f} MB")
        else:
            print("\nBuild completed but exe not found")
    else:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
