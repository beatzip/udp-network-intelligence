# UDP Network Intelligence v6

Professional UDP network diagnostics tool for gaming servers (CS2, Faceit, WarmupServer, BrutalCS, Cybershoke, Xplay, and custom servers).

## Features

- **UDP Probe Engine** — Normal / Deep / Aggressive testing modes with configurable intervals
- **Server Testing** — Parallel multi-target testing with Rate Limiter and Retry Strategy
- **Valve Source Query** — A2S_INFO, A2S_PLAYER, A2S_RULES with challenge handshake, Source Engine, Source 2, CS2, GoldSource
- **Statistics** — RTT, Mean, Median, Variance, StdDev, Percentiles (p50/p75/p90/p95/p99), EMA, Moving Average
- **Prediction Engine** — Connection probability, stability, quality score, rating (1-5 stars), confidence (all formulas documented)
- **Ranking Engine** — Multi-criteria server ranking with weighted scoring (RTT, loss, jitter, success rate, history, confidence)
- **History** — SQLite persistence for measurements, servers, rankings, errors
- **Charts** — pyqtgraph real-time RTT/Loss/Jitter charts with zoom, pan, export PNG
- **Export** — JSON, CSV, HTML with unified report structure
- **GUI** — PySide6 MVVM architecture, Dark Theme, thread-safe async operations

## Requirements

- Windows 10/11
- Python 3.12+
- Administrator privileges (for ICMP/raw sockets)

## Installation

```bash
git clone https://github.com/udp-network-intelligence/udp-network-intelligence.git
cd udp-network-intelligence
pip install -e ".[dev]"
```

## Usage

```bash
# Run the application
python -m uni.app.main

# Or use the installed entry point
uni
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/ tests/

# Format code
ruff format src/ tests/

# Type check
mypy src/
```

## Build Windows EXE

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller --name uni --onefile --windowed src/uni/app/main.py

# Or use the build script
python build.py
```

## Project Structure

```
src/uni/
├── app/           # Application bootstrap, lifecycle, config
├── core/          # Domain logic
│   ├── probe/     # UDP probe engine
│   ├── analysis/  # Statistics, prediction, ranking
│   ├── history/   # SQLite persistence
│   └── export/    # JSON/CSV/HTML export
├── net/           # Network layer (async UDP/ICMP sockets)
├── protocol/      # Wire protocol (A2S, Source Query)
├── plugins/       # Plugin system
├── view/          # PySide6 GUI (views, widgets, dialogs)
├── viewmodel/     # MVVM ViewModels
├── services/      # EventBus, TaskManager, Logger
└── utils/         # Shared utilities
```

## Architecture

- **MVVM** — PySide6 Views ↔ ViewModels ↔ Domain
- **AsyncIO** — Fully asynchronous network operations
- **EventBus** — Decoupled inter-module communication
- **SQLite** — Local history persistence
- **pyqtgraph** — High-performance real-time charts

## License

MIT License — see [LICENSE](LICENSE) for details.
