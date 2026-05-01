"""
main_window.py - Cửa sổ chính Mission Control (Single-Screen).

Cấu trúc layout:
    MainWindow (QMainWindow)
    └── centralWidget (QVBoxLayout)
        ├── TopStatusBar (36px fixed — Battery + WiFi + GPS + Flight Mode)
        └── QHBoxLayout (body)
            ├── LeftToolbar (48px fixed — icon buttons)
            ├── LeftPanel (320px fixed — Attitude 3D + Instruments + Telemetry)
            ├── MapPanel (stretch — bản đồ Leaflet trung tâm)
            └── RightPanel (320px fixed — Camera + Command Log)

Không còn: NavRail, QStackedWidget, DashboardTab, ManualControlTab, tab_log.
ConfigTab → QDialog (mở từ nút Settings trên LeftToolbar).
MissionTab → MapPanel (map chiếm center, waypoint panel floating).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout
)

from ui.widgets.top_status_bar import TopStatusBar
from ui.widgets.left_toolbar import LeftToolbar
from ui.widgets.left_panel import LeftPanel
from ui.widgets.right_panel import RightPanel
from ui.map_panel import MapPanel
from ui.config_tab import ConfigTab


# ══════════════════════════════════════════════
# MISSION CONTROL DARK THEME
# ══════════════════════════════════════════════

DARK_THEME = """
QMainWindow, QWidget {
    background-color: #0a0e17;
    color: #c0c8d8;
    font-family: 'Segoe UI', 'Roboto', sans-serif;
}
QGroupBox {
    border: 1px solid #1a2332;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 18px;
    font-weight: bold;
    color: #808098;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}
QLabel {
    color: #c0c8d8;
    border: none;
}
QProgressBar {
    border: 1px solid #1a2332;
    border-radius: 4px;
    background-color: #1a1a2e;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 3px;
    background-color: #00ff88;
}
QPushButton {
    background-color: #141a28;
    color: #c0c8d8;
    border: 1px solid #1a2332;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #1a2840;
    border-color: #2a3a52;
}
QPushButton:pressed {
    background-color: #0a1020;
}
QPushButton:disabled {
    background-color: #0d1117;
    color: #3a3a4a;
    border-color: #1a2332;
}
QSlider::groove:horizontal {
    border: 1px solid #1a2332;
    height: 6px;
    background: #1a1a2e;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #00ff88;
    border: 1px solid #00cc6a;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #33ffaa;
}
QLineEdit {
    background-color: #141a28;
    color: #c0c8d8;
    border: 1px solid #1a2332;
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: rgba(0, 255, 136, 0.2);
}
QTableWidget {
    background-color: #080c14;
    color: #c0c8d8;
    border: 1px solid #1a2332;
    gridline-color: #1a2332;
    alternate-background-color: #0d1117;
}
QTableWidget::item { padding: 4px; }
QHeaderView::section {
    background-color: #0a0e17;
    color: #00ff88;
    border: 1px solid #1a2332;
    padding: 4px;
    font-weight: bold;
}
QScrollBar:vertical {
    background: #0a0e17;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2a3442;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #3a4a5a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QSpinBox {
    background-color: #141a28;
    color: #c0c8d8;
    border: 1px solid #1a2332;
    border-radius: 4px;
    padding: 4px;
}
QDialog {
    background-color: #0a0e17;
    color: #c0c8d8;
}
"""


class MainWindow(QMainWindow):
    """
    Cửa sổ chính Mission Control — single-screen layout.

    Chỉ chứa UI layout, logic xử lý nằm ở GCSApp (main.py).

    Widget ownership (truy cập từ GCSApp):
        self.top_bar        — TopStatusBar
        self.left_toolbar   — LeftToolbar (ARM/Takeoff/RTH/Settings/Disconnect)
        self.left_panel     — LeftPanel (Attitude 3D + Instruments + Telemetry)
        self.map_panel      — MapPanel (map Leaflet + waypoint overlay)
        self.right_panel    — RightPanel (Camera + CommandLog)
        self.command_log    — shortcut → right_panel.command_log
        self.config_tab     — ConfigTab (QDialog, không hiển thị mặc định)

    Backward-compatible shortcuts (cho main.py rewiring an toàn):
        self.btn_disconnect → left_toolbar.btn_disconnect
        self.mission_tab    → map_panel (alias)
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drone GCS — Mission Control")
        self.resize(1600, 900)
        self.setMinimumSize(1280, 720)

        # Font dùng chung
        self._bold_font = QFont()
        self._bold_font.setBold(True)

        # Áp dụng Dark Theme
        self.setStyleSheet(DARK_THEME)

        # Xây dựng giao diện
        self._setup_ui()

    def _setup_ui(self):
        """Xây dựng single-screen Mission Control layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ═══════ TOP STATUS BAR (36px) ═══════
        self.top_bar = TopStatusBar()
        main_layout.addWidget(self.top_bar)

        # ═══════ BODY: Toolbar + Left + Center + Right ═══════
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # ── Left Toolbar (48px fixed) ──
        self.left_toolbar = LeftToolbar()
        body_layout.addWidget(self.left_toolbar)

        # ── Left Panel (320px fixed — Attitude + Telemetry) ──
        self.left_panel = LeftPanel()
        body_layout.addWidget(self.left_panel)

        # ── Center Map (stretch) ──
        self.map_panel = MapPanel()
        body_layout.addWidget(self.map_panel, stretch=1)

        # ── Right Panel (320px fixed — Camera + Log) ──
        self.right_panel = RightPanel()
        body_layout.addWidget(self.right_panel)

        main_layout.addLayout(body_layout)

        # ═══════ BACKWARD-COMPATIBLE SHORTCUTS ═══════
        # Để main.py rewiring an toàn — giữ tên cũ chỉ trỏ tới widget mới

        # btn_disconnect: main.py dùng self.btn_disconnect.clicked.connect(...)
        self.btn_disconnect = self.left_toolbar.btn_disconnect

        # mission_tab: main.py dùng self.mission_tab cho waypoint/map logic
        self.mission_tab = self.map_panel

        # command_log shortcut
        self.command_log = self.right_panel.command_log

        # ═══════ CONFIG TAB → DIALOG (không hiển thị mặc định) ═══════
        self.config_tab = ConfigTab()
        # Settings button mở dialog
        self.left_toolbar.btn_settings.clicked.connect(self._open_config_dialog)

        # ═══════ TOOLBAR SIGNALS ═══════
        # Waypoints toggle
        self.left_toolbar.btn_waypoints.clicked.connect(self.map_panel.toggle_waypoint_panel)

        # Locate drone
        self.left_toolbar.locate_clicked.connect(self._locate_drone_on_map)

    # ══════════════════════════════════════════════
    # ACTIONS
    # ══════════════════════════════════════════════

    def _open_config_dialog(self):
        """Mở ConfigTab dạng modal dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle("⚙ Cấu hình Drone GCS")
        dialog.resize(600, 500)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #0a0e17;
                color: #c0c8d8;
            }
        """)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        # Tạo config tab mới trong dialog (tránh reparent)
        config = ConfigTab()
        layout.addWidget(config)
        dialog.exec()

    def _locate_drone_on_map(self):
        """Chuyển map tới vị trí drone hiện tại."""
        self.map_panel._locate_drone()
