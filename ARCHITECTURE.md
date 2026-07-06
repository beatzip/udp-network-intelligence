# UDP Network Intelligence v6 — Architecture Document

## 1. Directory Structure

```
udp-network-intelligence/
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                    # CI: lint, type-check, test
│   │   └── release.yml               # Build + publish release artifacts
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
│
├── src/
│   └── uni/                           # Main package (UNI = UDP Network Intelligence)
│       ├── __init__.py                # Package version, public API exports
│       │
│       ├── app/                       # Application layer — bootstrap & lifecycle
│       │   ├── __init__.py
│       │   ├── main.py                # Entry point: asyncio.run(), app init
│       │   ├── application.py         # Application class: lifecycle manager
│       │   ├── config.py              # AppConfig dataclass, load/save TOML/YAML
│       │   ├── settings.py            # Runtime settings, user preferences
│       │   └── constants.py           # Protocol constants, magic numbers, enums
│       │
│       ├── core/                      # Domain layer — business logic (no UI, no IO details)
│       │   ├── __init__.py
│       │   ├── probe/                 # UDP Probe engine
│       │   │   ├── __init__.py
│       │   │   ├── engine.py          # ProbeEngine: orchestrates probe campaigns
│       │   │   ├── sender.py          # AsyncUDPProbeSender: raw UDP send
│       │   │   ├── receiver.py        # AsyncUDPProbeReceiver: raw UDP listen + demux
│       │   │   ├── icmp.py            # ICMPLooker: parse ICMP Time Exceeded / Dest Unreachable
│       │   │   ├── session.py         # ProbeSession: stateful probe to one target
│       │   │   └── models.py          # dataclasses: ProbeResult, ProbeStats, HopInfo
│       │   │
│       │   ├── traceroute/            # UDP Traceroute engine
│       │   │   ├── __init__.py
│       │   │   ├── traceroute.py      # UDPTraceroute: TTL-incremented probes
│       │   │   ├── hop.py             # HopResolver: IP → hop mapping + dedup
│       │   │   └── models.py          # dataclasses: TracerouteResult, TracerouteHop
│       │   │
│       │   ├── discovery/             # Game server discovery & query
│       │   │   ├── __init__.py
│       │   │   ├── a2s.py             # A2S_INFO / A2S_PLAYER / A2S_RULES query
│       │   │   ├── query.py           # GenericSourceQuery: GoldSource / Source engine
│       │   │   ├── rules.py           # RulesDecoder: parse server rules
│       │   │   └── models.py          # dataclasses: ServerInfo, PlayerInfo, ServerRules
│       │   │
│       │   ├── analysis/              # Statistical analysis of probe data
│       │   │   ├── __init__.py
│       │   │   ├── statistics.py      # StatsComputer: mean, p50, p95, p99, stddev, jitter
│       │   │   ├── quality.py         # QualityScorer: rate connection quality A-F
│       │   │   ├── anomaly.py         # AnomalyDetector: spike/loss/jitter detection
│       │   │   └── models.py          # dataclasses: QualityReport, AnomalyEvent
│       │   │
│       │   ├── geo/                   # GeoIP resolution
│       │   │   ├── __init__.py
│       │   │   ├── resolver.py        # GeoResolver: IP → country/city/AS/coordinates
│       │   │   ├── provider.py        # GeoProvider protocol (abstract)
│       │   │   ├── mmdb_provider.py   # MaxMindDB provider implementation
│       │   │   └── models.py          # dataclasses: GeoInfo, Coordinates
│       │   │
│       │   └── history/               # Historical data persistence
│       │       ├── __init__.py
│       │       ├── repository.py      # HistoryRepository: CRUD for probe results
│       │       ├── schema.py          # SQLite table definitions (dataclasses)
│       │       └── migrations/        # Schema migration scripts
│       │           ├── __init__.py
│       │           └── v001_initial.py
│       │
│       ├── net/                       # Network layer — low-level transport
│       │   ├── __init__.py
│       │   ├── udp_socket.py          # AsyncUDPSocket: wrapper with stats, TTL, bind
│       │   ├── icmp_socket.py         # AsyncICMPSocket: raw ICMP receive (admin)
│       │   ├── raw_socket.py          # RawSocketManager: Winsock raw socket lifecycle
│       │   ├── pool.py                # SocketPool: reusable socket allocation
│       │   ├── firewall.py            # FirewallHelper: Windows Firewall rule management
│       │   └── models.py              # dataclasses: SocketConfig, NetworkStats
│       │
│       ├── protocol/                  # Wire protocol implementations
│       │   ├── __init__.py
│       │   ├── base.py                # BaseProtocol: abstract packet encoder/decoder
│       │   ├── a2s_protocol.py        # A2S packet format (Challenge, Info, Player, Rules)
│       │   ├── source_query.py        # Source Query protocol (newer format)
│       │   ├── icmp_parser.py         # ICMP message parser
│       │   ├── ip_parser.py           # IP header parser (for TTL extraction)
│       │   └── models.py              # dataclasses: Packet, A2SPacket, ICMPMessage
│       │
│       ├── plugins/                   # Plugin system
│       │   ├── __init__.py
│       │   ├── loader.py              # PluginLoader: discover, load, init plugins
│       │   ├── registry.py            # PluginRegistry: name → plugin mapping
│       │   ├── base.py                # PluginBase: abstract base class for plugins
│       │   ├── hooks.py               # HookSystem: event bus for plugin hooks
│       │   ├── builtins/              # Built-in plugins (shipped with app)
│       │   │   ├── __init__.py
│       │   │   ├── server_list/       # Predefined server lists plugin
│       │   │   │   ├── __init__.py
│       │   │   │   ├── plugin.py      # ServerListPlugin implementation
│       │   │   │   └── servers.json   # Bundled server definitions
│       │   │   └── export/            # Export results plugin (CSV, JSON, HTML)
│       │   │       ├── __init__.py
│       │   │       ├── plugin.py
│       │   │       └── formatters.py  # CSV/JSON/HTML formatters
│       │   └── external/              # User-installed plugins directory
│       │       └── .gitkeep
│       │
│       ├── view/                      # Presentation layer — PySide6 UI
│       │   ├── __init__.py
│       │   ├── main_window.py         # MainWindow: top-level QMainWindow
│       │   ├── menubar.py             # MenuBar: File, Tools, View, Help
│       │   ├── toolbar.py             # Toolbar: quick actions
│       │   ├── statusbar.py           # StatusBar: connection status, stats
│       │   │
│       │   ├── views/                 # Page/view widgets
│       │   │   ├── __init__.py
│       │   │   ├── dashboard.py       # DashboardView: overview with live charts
│       │   │   ├── probe.py           # ProbeView: configure & run probe campaigns
│       │   │   ├── traceroute.py      # TracerouteView: UDP traceroute with hop map
│       │   │   ├── discovery.py       # DiscoveryView: server browser / A2S query
│       │   │   ├── analysis.py        # AnalysisView: historical analysis & reports
│       │   │   ├── settings.py        # SettingsView: app configuration UI
│       │   │   └── plugins.py         # PluginsView: manage installed plugins
│       │   │
│       │   ├── widgets/               # Reusable custom widgets
│       │   │   ├── __init__.py
│       │   │   ├── chart.py           # LatencyChart, LossChart, JitterChart
│       │   │   ├── hop_table.py       # HopTable: traceroute hop display
│       │   │   ├── server_card.py     # ServerCard: server info card widget
│       │   │   ├── target_input.py    # TargetInput: IP:Port with validation
│       │   │   ├── probe_indicator.py # ProbeIndicator: live probe status dots
│       │   │   ├── stat_label.py      # StatLabel: labeled statistic display
│       │   │   └── log_console.py     # LogConsole: embedded log viewer
│       │   │
│       │   ├── dialogs/               # Modal dialog windows
│       │   │   ├── __init__.py
│       │   │   ├── about.py           # AboutDialog: version, credits
│       │   │   ├── export.py          # ExportDialog: export format selection
│       │   │   └── server_add.py      # AddServerDialog: add custom server
│       │   │
│       │   ├── resources/             # Static assets
│       │   │   ├── __init__.py
│       │   │   ├── icons/             # Application icons (.ico, .png)
│       │   │   │   └── uni.ico
│       │   │   ├── styles/            # Qt Stylesheets
│       │   │   │   ├── dark.qss
│       │   │   │   └── light.qss
│       │   │   └── fonts/             # Bundled fonts (optional)
│       │   │
│       │   └── styles/                # Style management
│       │       ├── __init__.py
│       │       └── theme.py           # ThemeManager: load/apply QSS themes
│       │
│       ├── viewmodel/                 # ViewModel layer — bridges View ↔ Model
│       │   ├── __init__.py
│       │   ├── base.py                # BaseViewModel: signals/slots common logic
│       │   ├── probe_vm.py            # ProbeViewModel: probe session logic
│       │   ├── traceroute_vm.py       # TracerouteViewModel
│       │   ├── discovery_vm.py        # DiscoveryViewModel: server query logic
│       │   ├── analysis_vm.py         # AnalysisViewModel: stats computation
│       │   ├── dashboard_vm.py        # DashboardViewModel: aggregate live data
│       │   ├── settings_vm.py         # SettingsViewModel: config read/write
│       │   └── history_vm.py          # HistoryViewModel: past results browsing
│       │
│       ├── services/                  # Application services — cross-cutting concerns
│       │   ├── __init__.py
│       │   ├── event_bus.py           # EventBus: async pub/sub for decoupled comms
│       │   ├── task_manager.py        # TaskManager: manage async background tasks
│       │   ├── notification.py        # NotificationService: toast/system notifications
│       │   ├── updater.py             # UpdateChecker: GitHub releases check
│       │   └── logger.py              # LoggingService: structured logging setup
│       │
│       └── utils/                     # Shared utilities (no domain logic)
│           ├── __init__.py
│           ├── ip.py                  # IP validation, parsing, port extraction
│           ├── format.py              # Human-readable formatters (bytes, ms, etc.)
│           ├── platform.py            # OS-specific helpers (admin check, firewall)
│           ├── async_utils.py         # Async helpers: gather_with_limit, retry, timeout
│           └── network.py             # Get local IP, DNS resolve, interface enumeration
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Shared fixtures: mock sockets, sample data
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── test_probe_engine.py
│   │   │   ├── test_traceroute.py
│   │   │   ├── test_a2s.py
│   │   │   ├── test_statistics.py
│   │   │   ├── test_quality_scorer.py
│   │   │   └── test_anomaly.py
│   │   ├── protocol/
│   │   │   ├── __init__.py
│   │   │   ├── test_a2s_protocol.py
│   │   │   ├── test_icmp_parser.py
│   │   │   └── test_ip_parser.py
│   │   ├── viewmodel/
│   │   │   ├── __init__.py
│   │   │   ├── test_probe_vm.py
│   │   │   └── test_discovery_vm.py
│   │   ├── plugins/
│   │   │   ├── __init__.py
│   │   │   └── test_plugin_loader.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── test_ip.py
│   │       └── test_format.py
│   └── integration/
│       ├── __init__.py
│       ├── test_probe_flow.py         # End-to-end probe test with mock network
│       ├── test_discovery_flow.py     # End-to-end server query test
│       └── test_plugin_system.py      # Plugin load + hook fire test
│
├── docs/
│   ├── ARCHITECTURE.md               # This file
│   ├── CONTRIBUTING.md
│   ├── CHANGELOG.md
│   ├── ROADMAP.md
│   └── screenshots/                   # App screenshots for README
│
├── pyproject.toml                     # Project metadata, dependencies, tool config
├── README.md
├── LICENSE                            # MIT
├── .gitignore
├── .pre-commit-config.yaml            # Ruff, mypy, trailing-whitespace
├── ruff.toml                          # Ruff linter/formatter config
├── mypy.ini                           # mypy strict config
└── uni.toml                           # Default app config (shipped with app)
```

---

## 2. Purpose of Each Folder

| Folder | Purpose |
|---|---|
| `.github/` | GitHub-specific: CI/CD workflows, issue/PR templates |
| `src/uni/` | Main application package — all production code |
| `src/uni/app/` | Application bootstrap, lifecycle, configuration |
| `src/uni/core/` | **Domain layer**: pure business logic (probing, tracing, analysis) — no UI or transport details |
| `src/uni/core/probe/` | UDP probe engine: send/receive/measure |
| `src/uni/core/traceroute/` | UDP-based traceroute with ICMP analysis |
| `src/uni/core/discovery/` | Game server query protocols (A2S, Source Query) |
| `src/uni/core/analysis/` | Statistical analysis, quality scoring, anomaly detection |
| `src/uni/core/geo/` | IP geolocation via MaxMindDB |
| `src/uni/core/history/` | SQLite persistence for probe results |
| `src/uni/net/` | **Network layer**: async socket wrappers, raw sockets, firewall |
| `src/uni/protocol/` | **Protocol layer**: packet encoding/decoding for A2S, ICMP, IP |
| `src/uni/plugins/` | **Plugin system**: loader, registry, hooks, built-in plugins |
| `src/uni/view/` | **Presentation layer**: PySide6 windows, widgets, dialogs, styles |
| `src/uni/viewmodel/` | **ViewModel layer**: mediators between Views and Domain models |
| `src/uni/services/` | **Services**: cross-cutting concerns (event bus, tasks, notifications) |
| `src/uni/utils/` | **Utilities**: pure functions, helpers (IP, format, platform) |
| `tests/` | Unit and integration tests |
| `tests/unit/` | Isolated tests per module |
| `tests/integration/` | Multi-module flow tests |
| `docs/` | Project documentation |

---

## 3. Purpose of Each File

### `src/uni/app/`

| File | Purpose |
|---|---|
| `main.py` | Entry point. Creates `asyncio.run()`, initializes Application, starts event loop |
| `application.py` | `Application` class. Owns all services, starts/stops subsystems, manages lifecycle |
| `config.py` | `AppConfig` dataclass. Load from `uni.toml`, save, validate. Sections: network, probe, geo, ui, plugins |
| `settings.py` | `SettingsManager` — runtime settings with change notifications (signals) |
| `constants.py` | Enums: `ProbeProtocol`, `ServerType`, `QualityGrade`. Constants: default ports, timeouts, buffer sizes |

### `src/uni/core/probe/`

| File | Purpose |
|---|---|
| `engine.py` | `ProbeEngine` — top-level orchestrator. Creates probe sessions, manages campaigns, aggregates results |
| `sender.py` | `AsyncProbeSender` — async coroutine that sends UDP packets at configured interval |
| `receiver.py` | `AsyncProbeReceiver` — listens for responses + ICMP, demuxes by session ID |
| `icmp.py` | `ICMPLooker` — listens for ICMP Time Exceeded / Destination Unreachable, maps to probe session |
| `session.py` | `ProbeSession` — stateful single-target probe: tracks sent/received/lost, computes running stats |
| `models.py` | `ProbeResult`, `ProbeStats`, `ProbeConfig` dataclasses |

### `src/uni/core/traceroute/`

| File | Purpose |
|---|---|
| `traceroute.py` | `UDPTraceroute` — sends probes with incrementing TTL, collects ICMP responses per hop |
| `hop.py` | `HopResolver` — maps TTL→response, handles timeouts, deduplicates |
| `models.py` | `TracerouteResult`, `TracerouteHop` dataclasses |

### `src/uni/core/discovery/`

| File | Purpose |
|---|---|
| `a2s.py` | `A2SQuery` — full A2S_INFO, A2S_PLAYER, A2S_RULES implementation with challenge handshake |
| `query.py` | `SourceQuery` — unified query interface for Source/GoldSource engines |
| `rules.py` | `RulesDecoder` — decode A2S_RULES key-value pairs |
| `models.py` | `ServerInfo`, `PlayerInfo`, `ServerRules`, `QueryResult` dataclasses |

### `src/uni/core/analysis/`

| File | Purpose |
|---|---|
| `statistics.py` | `StatsComputer` — compute min/max/mean/median/p95/p99/stddev/jitter from probe samples |
| `quality.py` | `QualityScorer` — rate overall connection quality (A–F grade) based on latency, loss, jitter |
| `anomaly.py` | `AnomalyDetector` — detect latency spikes, sudden loss, jitter bursts in time series |
| `models.py` | `QualityReport`, `AnomalyEvent`, `AnalysisResult` dataclasses |

### `src/uni/core/geo/`

| File | Purpose |
|---|---|
| `resolver.py` | `GeoResolver` — high-level: IP → GeoInfo, with cache |
| `provider.py` | `GeoProvider` — ABC/Protocol for geo data providers |
| `mmdb_provider.py` | `MaxMindProvider` — reads MaxMind GeoLite2 .mmdb files |
| `models.py` | `GeoInfo`, `Coordinates` dataclasses |

### `src/uni/core/history/`

| File | Purpose |
|---|---|
| `repository.py` | `HistoryRepository` — async CRUD: save probe result, query by target/date, get stats |
| `schema.py` | Table definitions as dataclasses, column mappings |
| `migrations/` | Versioned schema migrations for SQLite |

### `src/uni/net/`

| File | Purpose |
|---|---|
| `udp_socket.py` | `AsyncUDPSocket` — wraps `asyncio.DatagramProtocol`, adds send stats, TTL setting |
| `icmp_socket.py` | `AsyncICMPSocket` — raw ICMP receive (requires admin on Windows) |
| `raw_socket.py` | `RawSocketManager` — Winsock2 raw socket lifecycle (ctypes/cffi bindings) |
| `pool.py` | `SocketPool` — allocate/reuse sockets, manage concurrent limit |
| `firewall.py` | `FirewallHelper` — add/remove Windows Firewall rules for the app |
| `models.py` | `SocketConfig`, `NetworkInterface`, `NetworkStats` dataclasses |

### `src/uni/protocol/`

| File | Purpose |
|---|---|
| `base.py` | `BaseProtocol` — ABC for encode/decode packet |
| `a2s_protocol.py` | `A2SProtocol` — encode A2S challenges, decode info/player/rules responses |
| `source_query.py` | `SourceQueryProtocol` — newer Source Query format support |
| `icmp_parser.py` | `ICMPParser` — parse ICMPv4 messages (Type, Code, embedded IP header) |
| `ip_parser.py` | `IPParser` — parse IPv4 header, extract TTL, protocol, checksum |
| `models.py` | `Packet`, `A2SPacket`, `ICMPMessage`, `IPHeader` dataclasses |

### `src/uni/plugins/`

| File | Purpose |
|---|---|
| `loader.py` | `PluginLoader` — discover plugins in `external/` dir, import, instantiate |
| `registry.py` | `PluginRegistry` — name→plugin map, version tracking |
| `base.py` | `PluginBase` — ABC: `on_load()`, `on_unload()`, `get_hooks()`, metadata |
| `hooks.py` | `HookSystem` — async event bus: register hook, fire hook, priority ordering |
| `builtins/server_list/` | Predefined server lists (Faceit, CyberSHOKE, etc.) bundled as JSON |
| `builtins/export/` | Export probe results to CSV / JSON / HTML reports |

### `src/uni/view/`

| File | Purpose |
|---|---|
| `main_window.py` | `MainWindow` — QMainWindow: menu, toolbar, stacked widget for views, statusbar |
| `menubar.py` | `UniMenuBar` — File (exit), Tools (traceroute, discovery), View (theme), Help |
| `toolbar.py` | `UniToolBar` — Quick Probe, Stop, Settings shortcuts |
| `statusbar.py` | `UniStatusBar` — Active probes count, network status indicator |
| `views/dashboard.py` | `DashboardView` — Overview: live latency chart, active probes, recent results |
| `views/probe.py` | `ProbeView` — Target input, probe config (count, interval), start/stop, live chart |
| `views/traceroute.py` | `TracerouteView` — Target input, traceroute execution, hop table visualization |
| `views/discovery.py` | `DiscoveryView` — Server browser: add servers, A2S query, display results |
| `views/analysis.py` | `AnalysisView` — Historical data: date range filter, charts, anomaly list |
| `views/settings.py` | `SettingsView` — Config UI: network, plugins, theme, geo database path |
| `views/plugins.py` | `PluginsView` — Installed plugins list, enable/disable, info |
| `widgets/chart.py` | `LatencyChart`, `LossChart`, `JitterChart` — Qt Charts wrappers |
| `widgets/hop_table.py` | `HopTable` — QTableWidget for traceroute hops with color-coded latency |
| `widgets/server_card.py` | `ServerCard` — Card widget: name, map, players, ping, country flag |
| `widgets/target_input.py` | `TargetInput` — QLineEdit with IP:Port validation + autocomplete |
| `widgets/probe_indicator.py` | `ProbeIndicator` — Animated dots showing active probe status |
| `widgets/stat_label.py` | `StatLabel` — QLabel with title + value + optional trend arrow |
| `widgets/log_console.py` | `LogConsole` — QTextEdit-based log viewer with level filtering |
| `dialogs/about.py` | `AboutDialog` — Version, license, links |
| `dialogs/export.py` | `ExportDialog` — Format selection, file path, options |
| `dialogs/server_add.py` | `AddServerDialog` — IP:Port, name, game type input |
| `resources/icons/` | Application icon |
| `resources/styles/` | Dark/Light QSS themesheets |
| `styles/theme.py` | `ThemeManager` — load QSS, apply to QApplication, switch themes |

### `src/uni/viewmodel/`

| File | Purpose |
|---|---|
| `base.py` | `BaseViewModel` — common signal definitions, async task management |
| `probe_vm.py` | `ProbeViewModel` — holds probe config/results, exposes signals for chart updates |
| `traceroute_vm.py` | `TracerouteViewModel` — manages traceroute execution + hop data |
| `discovery_vm.py` | `DiscoveryViewModel` — server list model, query execution |
| `analysis_vm.py` | `AnalysisViewModel` — date range selection, stats computation trigger |
| `dashboard_vm.py` | `DashboardViewModel` — aggregates data from other VMs for overview |
| `settings_vm.py` | `SettingsViewModel` — bridges config read/write to SettingsView |
| `history_vm.py` | `HistoryViewModel` — query history, filter, display |

### `src/uni/services/`

| File | Purpose |
|---|---|
| `event_bus.py` | `EventBus` — async pub/sub: `emit()`, `on()`, `off()`. Decouples modules |
| `task_manager.py` | `TaskManager` — track background asyncio tasks, cancel on shutdown |
| `notification.py` | `NotificationService` — toast notifications via Qt system tray |
| `updater.py` | `UpdateChecker` — check GitHub releases API for new versions |
| `logger.py` | `LoggingService` — configure root logger, file + console handlers, rotation |

### `src/uni/utils/`

| File | Purpose |
|---|---|
| `ip.py` | `parse_target("1.2.3.4:27015")`, `is_valid_ip()`, `is_private_ip()` |
| `format.py` | `format_ms()`, `format_bytes()`, `format_bitrate()`, `format_duration()` |
| `platform.py` | `is_admin()`, `is_windows()`, `get_executable_dir()` |
| `async_utils.py` | `gather_with_limit()`, `retry()`, `cancel_on_timeout()`, `TaskGroup` |
| `network.py` | `get_local_ip()`, `resolve_dns()`, `list_interfaces()` |

---

## 4. Module Dependencies

```
                    ┌─────────────────────────────────────────┐
                    │              uni.view (UI)               │
                    │  main_window, views/*, widgets/*, dialogs│
                    └───────────────┬─────────────────────────┘
                                    │ depends on
                    ┌───────────────▼─────────────────────────┐
                    │         uni.viewmodel (ViewModels)        │
                    │  probe_vm, discovery_vm, dashboard_vm ...│
                    └───────┬────────────────┬────────────────┘
                            │                │
              ┌─────────────▼──┐     ┌──────▼──────────────────┐
              │  uni.core/*    │     │   uni.services/*         │
              │  (domain)      │     │   event_bus, task_mgr    │
              └──┬──────┬──────┘     └─────────────────────────┘
                 │      │
    ┌────────────▼┐  ┌──▼───────────────┐
    │  uni.net/*  │  │ uni.protocol/*   │
    │ (sockets)   │  │ (wire format)    │
    └──────┬──────┘  └────┬─────────────┘
           │              │
    ┌──────▼──────────────▼──────────────┐
    │           uni.utils/*              │
    │   (ip, format, async, platform)    │
    └────────────────────────────────────┘

    ┌────────────────────────────────────┐
    │          uni.plugins/*             │
    │  Uses: core, net, protocol, utils  │
    │  Exposes: hooks via uni.services   │
    └────────────────────────────────────┘
```

### Dependency Rules (enforced):

1. **view** → **viewmodel** only (never directly to core/net/protocol)
2. **viewmodel** → **core**, **services**, **utils** (never to view)
3. **core** → **protocol**, **net**, **utils** (never to view/viewmodel)
4. **net** → **protocol** (socket layer uses protocol for encoding)
5. **protocol** → **utils** only (pure encoding/decoding)
6. **services** → **utils** only (cross-cutting, no domain knowledge)
7. **plugins** → **core**, **net**, **protocol**, **utils**, **services** (full access via hooks)
8. **utils** → nothing (leaf package, pure functions)

---

## 5. Data Flow Diagram

### Probe Campaign Flow

```
User types IP:Port in ProbeView
        │
        ▼
ProbeViewModel.on_start_probe()
        │
        ├── validates target via utils/ip.py
        ├── creates ProbeConfig dataclass
        │
        ▼
ProbeEngine.start_campaign(config)
        │
        ├── creates ProbeSession(target, config)
        │       │
        │       ├── ProbeSender ──UDP──▶ target:27015
        │       │       (asyncio tasks sending at interval)
        │       │
        │       ├── ProbeReceiver ◀──UDP── target:27015
        │       │       (receives response, correlates by session_id)
        │       │
        │       └── ICMPLooker ◀──ICMP── network
        │               (receives ICMP TTL exceeded, maps to session)
        │
        │   All three feed into ProbeSession.update(result)
        │
        ▼
ProbeSession emits stats_update signal (via EventBus)
        │
        ├──▶ ProbeViewModel receives signal
        │       │
        │       ▼
        │    DashboardView updates LatencyChart / LossChart
        │
        └──▶ StatsComputer computes running statistics
                │
                ▼
             QualityScorer rates connection (A-F)
                │
                ▼
             AnomalyDetector flags spikes
                │
                ▼
             HistoryRepository.save(probe_result)  ──▶ SQLite
```

### Traceroute Flow

```
User clicks "Trace" in TracerouteView
        │
        ▼
TracerouteViewModel.on_start_traceroute(target)
        │
        ▼
UDPTraceroute.execute(target)
        │
        ├── for ttl in 1..max_hops:
        │       │
        │       ├── send UDP probe with IP_TTL = ttl
        │       │
        │       ├── await ICMP response (with timeout)
        │       │       │
        │       │       ├── ICMP Time Exceeded → intermediate hop
        │       │       └── ICMP Dest Unreachable → destination reached
        │       │
        │       └── HopResolver maps TTL → {ip, rtt, hostname}
        │
        ▼
TracerouteResult (list of TracerouteHop)
        │
        ▼
TracerouteViewModel updates TracerouteView
        │
        ├──▶ HopTable widget renders hops
        └──▶ GeoResolver resolves each hop IP → country/city
                │
                ▼
             Map visualization (optional, future)
```

### Server Discovery Flow

```
User selects server or enters IP:Port in DiscoveryView
        │
        ▼
DiscoveryViewModel.on_query_server(target)
        │
        ▼
A2SQuery.query_info(target)
        │
        ├── A2SProtocol.encode_challenge_request()
        ├── AsyncUDPSocket.send(packet)
        ├── AsyncUDPSocket.recv() → challenge response
        ├── A2SProtocol.encode_info_request(challenge)
        ├── AsyncUDPSocket.send(packet)
        ├── AsyncUDPSocket.recv() → info response
        └── A2SProtocol.decode_info(response) → ServerInfo
        │
        ▼
DiscoveryViewModel receives ServerInfo
        │
        └──▶ DiscoveryView renders ServerCard
                │
                └──▶ GeoResolver: server IP → GeoInfo (country flag)
```

### Event Bus Architecture

```
┌──────────┐   emit("probe.update")   ┌──────────┐
│   Core   │ ─────────────────────────▶│EventBus  │
│ (Engine) │                          │          │
└──────────┘                          └────┬─────┘
                                           │ dispatch
                              ┌────────────┼────────────┐
                              ▼            ▼            ▼
                     ┌────────────┐ ┌───────────┐ ┌──────────┐
                     │ProbeVM     │ │ Dashboard │ │ History  │
                     │(chart data)│ │  (stats)  │ │  (save)  │
                     └────────────┘ └───────────┘ └──────────┘
```

---

## 6. Development Plan (Phases)

### Phase 0 — Scaffolding & Infrastructure (Week 1)

| Step | Description |
|---|---|
| 0.1 | Create full directory structure (all `__init__.py` files) |
| 0.2 | Configure `pyproject.toml`: dependencies, dev deps, tools |
| 0.3 | Configure `ruff.toml` + `mypy.ini` for strict checking |
| 0.4 | Configure `.pre-commit-config.yaml` |
| 0.5 | Setup `.github/workflows/ci.yml` |
| 0.6 | Create `AppConfig` dataclass + `uni.toml` loader |
| 0.7 | Create `LoggingService` |
| 0.8 | Create `EventBus` |
| 0.9 | Create `constants.py` with all enums |
| 0.10 | Create all utility modules (`utils/*`) |
| 0.11 | Write tests for utils |

**Deliverable**: skeleton project with linting, type-checking, CI passing, utilities tested.

### Phase 1 — Protocol & Network Layer (Week 2)

| Step | Description |
|---|---|
| 1.1 | Implement `protocol/base.py` (abstract base) |
| 1.2 | Implement `protocol/a2s_protocol.py` (A2S wire format) |
| 1.3 | Implement `protocol/ip_parser.py` |
| 1.4 | Implement `protocol/icmp_parser.py` |
| 1.5 | Implement `net/udp_socket.py` (async UDP) |
| 1.6 | Implement `net/raw_socket.py` (Winsock raw, admin) |
| 1.7 | Implement `net/icmp_socket.py` |
| 1.8 | Implement `net/pool.py` (socket pool) |
| 1.9 | Implement `net/firewall.py` (Windows Firewall helper) |
| 1.10 | Write unit tests for all protocol modules |
| 1.11 | Write integration test: send/receive UDP loopback |

**Deliverable**: fully functional protocol encoding + async UDP networking.

### Phase 2 — Core Domain: Probe Engine (Week 3)

| Step | Description |
|---|---|
| 2.1 | Implement `core/probe/models.py` (ProbeResult, ProbeStats) |
| 2.2 | Implement `core/probe/session.py` (ProbeSession) |
| 2.3 | Implement `core/probe/sender.py` |
| 2.4 | Implement `core/probe/receiver.py` |
| 2.5 | Implement `core/probe/icmp.py` (ICMP listener) |
| 2.6 | Implement `core/probe/engine.py` (ProbeEngine orchestrator) |
| 2.7 | Implement `core/analysis/statistics.py` |
| 2.8 | Implement `core/analysis/quality.py` |
| 2.9 | Implement `core/analysis/anomaly.py` |
| 2.10 | Write unit tests for probe engine |
| 2.11 | Write integration test: probe loopback + analyze |

**Deliverable**: working probe engine with statistics, tested.

### Phase 3 — Traceroute & Discovery (Week 4)

| Step | Description |
|---|---|
| 3.1 | Implement `core/traceroute/traceroute.py` |
| 3.2 | Implement `core/traceroute/hop.py` |
| 3.3 | Implement `core/traceroute/models.py` |
| 3.4 | Implement `core/discovery/a2s.py` |
| 3.5 | Implement `core/discovery/query.py` |
| 3.6 | Implement `core/discovery/rules.py` |
| 3.7 | Implement `core/geo/resolver.py` + provider |
| 3.8 | Implement `core/history/repository.py` + schema |
| 3.9 | Write unit tests for traceroute + discovery |
| 3.10 | Write integration test: A2S query to public server |

**Deliverable**: traceroute, server discovery, geo, history — all tested.

### Phase 4 — Plugin System (Week 5)

| Step | Description |
|---|---|
| 4.1 | Implement `plugins/base.py` (PluginBase ABC) |
| 4.2 | Implement `plugins/hooks.py` (HookSystem) |
| 4.3 | Implement `plugins/loader.py` (PluginLoader) |
| 4.4 | Implement `plugins/registry.py` (PluginRegistry) |
| 4.5 | Implement `builtins/server_list/` plugin |
| 4.6 | Implement `builtins/export/` plugin |
| 4.7 | Write unit tests for plugin loader + hooks |
| 4.8 | Write integration test: load plugin, fire hook |

**Deliverable**: extensible plugin system with two built-in plugins.

### Phase 5 — GUI Foundation (Week 6)

| Step | Description |
|---|---|
| 5.1 | Implement `view/main_window.py` (QMainWindow) |
| 5.2 | Implement `view/menubar.py`, `toolbar.py`, `statusbar.py` |
| 5.3 | Implement `styles/theme.py` (dark/light QSS loading) |
| 5.4 | Create `resources/styles/dark.qss` |
| 5.5 | Create `resources/styles/light.qss` |
| 5.6 | Implement `widgets/target_input.py` |
| 5.7 | Implement `widgets/stat_label.py` |
| 5.8 | Implement `widgets/log_console.py` |
| 5.9 | Implement `viewmodel/base.py` + `settings_vm.py` |
| 5.10 | Implement `views/settings.py` |

**Deliverable**: runnable app with main window, theme, settings page.

### Phase 6 — GUI: Probe & Traceroute Views (Week 7)

| Step | Description |
|---|---|
| 6.1 | Implement `widgets/chart.py` (LatencyChart, LossChart) |
| 6.2 | Implement `widgets/probe_indicator.py` |
| 6.3 | Implement `viewmodel/probe_vm.py` |
| 6.4 | Implement `views/probe.py` |
| 6.5 | Implement `viewmodel/traceroute_vm.py` |
| 6.6 | Implement `widgets/hop_table.py` |
| 6.7 | Implement `views/traceroute.py` |
| 6.8 | Wire ProbeViewModel ↔ ProbeEngine via EventBus |

**Deliverable**: fully functional Probe and Traceroute pages with live charts.

### Phase 7 — GUI: Discovery & Dashboard (Week 8)

| Step | Description |
|---|---|
| 7.1 | Implement `widgets/server_card.py` |
| 7.2 | Implement `viewmodel/discovery_vm.py` |
| 7.3 | Implement `views/discovery.py` |
| 7.4 | Implement `viewmodel/dashboard_vm.py` |
| 7.5 | Implement `views/dashboard.py` |
| 7.6 | Implement `viewmodel/history_vm.py` |
| 7.7 | Implement `views/analysis.py` |
| 7.8 | Implement `dialogs/about.py`, `export.py`, `server_add.py` |
| 7.9 | Implement `views/plugins.py` |

**Deliverable**: all views functional, app is feature-complete.

### Phase 8 — Polish & Release (Week 9)

| Step | Description |
|---|---|
| 8.1 | Implement `task_manager.py` (clean shutdown) |
| 8.2 | Implement `notification.py` (system tray toasts) |
| 8.3 | Implement `updater.py` (GitHub release check) |
| 8.4 | Full application `Application` lifecycle in `app/application.py` |
| 8.5 | Create `app/main.py` entry point |
| 8.6 | Write comprehensive README.md |
| 8.7 | Write CONTRIBUTING.md |
| 8.8 | Write CHANGELOG.md |
| 8.9 | Add `resources/icons/uni.ico` |
| 8.10 | Final CI workflow: lint + test + build |
| 8.11 | Create GitHub Release workflow (pyinstaller/Nuitka build) |
| 8.12 | Final code review, type coverage, test coverage ≥80% |

**Deliverable**: production-ready v6.0.0 release.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **MVVM over MVC** | PySide6 signals/slots naturally map to ViewModel pattern; keeps Views thin |
| **EventBus for cross-module comms** | Decouples probe engine from UI; plugins can subscribe to events |
| **Protocol layer separate from net** | Wire format changes shouldn't affect socket management |
| **SocketPool** | Limits concurrent sockets (Windows has per-process limits); reuses binds |
| **Raw socket manager** | ICMP requires raw sockets on Windows (admin); isolated for clean elevation |
| **Plugin system with hooks** | Third-party extensions without modifying core code |
| **SQLite for history** | Zero-config, single-file, sufficient for local probe data |
| **MaxMindDB for GeoIP** | Industry standard, works offline, free GeoLite2 database |
| **TOML for config** | Python 3.11+ stdlib support, human-readable, Pythonic |
| **Ruff for linting** | Fast, comprehensive, replaces flake8+isort+pyupgrade |

---

*Architecture document for UDP Network Intelligence v6*
*Generated for project initialization*
