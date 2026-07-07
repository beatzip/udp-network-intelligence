"""Main window — top-level application window with navigation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from uni.app.constants import APP_NAME, APP_VERSION
from uni.view.dialogs.about import AboutDialog
from uni.view.views.dashboard import DashboardView
from uni.view.views.history import HistoryView
from uni.view.views.probe import ProbeView
from uni.view.views.servers import ServersView
from uni.view.views.traceroute import TracerouteView
from uni.view.widgets.status_indicator import StatusIndicator


class MainWindow(QMainWindow):
    """Main application window with page navigation.

    Signals:
        page_changed: Emitted with page index when navigation changes.
    """

    page_changed = Signal(int)

    PAGES = {
        "dashboard": 0,
        "probe": 1,
        "traceroute": 2,
        "servers": 3,
        "history": 4,
    }

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 800)

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Create pages
        self._dashboard_view = DashboardView()
        self._probe_view = ProbeView()
        self._traceroute_view = TracerouteView()
        self._servers_view = ServersView()
        self._history_view = HistoryView()

        self._stack.addWidget(self._dashboard_view)
        self._stack.addWidget(self._probe_view)
        self._stack.addWidget(self._traceroute_view)
        self._stack.addWidget(self._servers_view)
        self._stack.addWidget(self._history_view)

        # Default to dashboard
        self._stack.setCurrentIndex(0)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("View")
        for name, idx in self.PAGES.items():
            action = QAction(name.capitalize(), self)
            action.triggered.connect(
                lambda checked, i=idx: self._stack.setCurrentIndex(i)
            )
            view_menu.addAction(action)

        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar { background-color: #11111b; } "
            "QToolButton { color: #cdd6f4; padding: 6px 12px; "
            "font-size: 13px; } "
            "QToolButton:hover { background-color: #313244; } "
            "QToolButton:pressed { background-color: #45475a; }"
        )
        self.addToolBar(toolbar)

        for name, idx in self.PAGES.items():
            action = QAction(name.capitalize(), self)
            action.triggered.connect(
                lambda checked, i=idx: self._stack.setCurrentIndex(i)
            )
            toolbar.addAction(action)

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self._status_indicator = StatusIndicator(label="Ready")
        self._statusbar.addPermanentWidget(self._status_indicator)

    def _show_about(self) -> None:
        dialog = AboutDialog(self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def dashboard_view(self) -> DashboardView:
        """Access the dashboard view."""
        return self._dashboard_view

    @property
    def probe_view(self) -> ProbeView:
        """Access the probe view."""
        return self._probe_view

    @property
    def traceroute_view(self) -> TracerouteView:
        """Access the traceroute view."""
        return self._traceroute_view

    @property
    def servers_view(self) -> ServersView:
        """Access the servers view."""
        return self._servers_view

    @property
    def history_view(self) -> HistoryView:
        """Access the history view."""
        return self._history_view

    def set_status(self, text: str, level: str = "ok") -> None:
        """Update the status bar.

        Args:
            text: Status message.
            level: Status indicator level.
        """
        self._statusbar.showMessage(text)
        self._status_indicator.set_status(level)

    def navigate_to(self, page: str) -> None:
        """Navigate to a named page.

        Args:
            page: Page name ('dashboard', 'probe', 'traceroute', 'servers', 'history').
        """
        idx = self.PAGES.get(page, 0)
        self._stack.setCurrentIndex(idx)
