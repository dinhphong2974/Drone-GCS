"""
LeftPanel — Panel trái 320px chứa Attitude 3D, Instruments, và Telemetry.

Cấu trúc dọc:
1. Section "THÁI ĐỘ BAY & LA BÀN": Panda3D drone 3D + Compass/ADI instruments
2. Section "THÔNG SỐ TELEMETRY FC": Grid 2 cột Label | Value
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox, QGridLayout,
    QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont
from PySide6.QtWebEngineWidgets import QWebEngineView

from ui.attitude_3d_widget import Attitude3DWidget


class LeftPanel(QWidget):
    """
    Panel trái chứa Flight Attitude + Telemetry.

    Widget ownership cho GCSApp:
        - widget_3d_attitude (Panda3D)
        - instruments_view (QWebEngineView — Compass + ADI)
        - val_roll, val_pitch, val_yaw
        - val_alt, val_spd, val_lat, val_lon
        - val_current, val_power
        - val_surface_alt, val_lidar_qual, val_opflow, val_vario
        - val_armed, val_gps_fix, val_sats, val_gps_accuracy
        - val_rssi, val_distance
    """

    # ═══════ STYLE CONSTANTS ═══════
    DARK_BG = "#0d1117"
    SECTION_BG = "#0a0e17"
    BORDER_COLOR = "#1a2332"
    TEXT_COLOR = "#c0c8d8"
    VALUE_COLOR = "#00ff88"
    MUTED = "#808098"
    LABEL_FONT = "Segoe UI"
    VALUE_FONT = "Consolas"

    _GROUP_STYLE = """
        QGroupBox {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 6px;
            margin-top: 14px;
            padding-top: 18px;
            font-size: 10px;
            font-weight: bold;
            color: {accent};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: {accent};
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setObjectName("leftPanel")
        self._instruments_ready = False
        self._setup_ui()

    def _setup_ui(self):
        # Scroll area wrapping
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {self.DARK_BG};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {self.DARK_BG};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: #2a3442;
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 4, 6, 8)
        content_layout.setSpacing(6)

        # ═══════ SECTION 1: ATTITUDE & COMPASS ═══════
        attitude_group = QGroupBox("THÁI ĐỘ BAY & LA BÀN")
        attitude_group.setStyleSheet(
            self._GROUP_STYLE.format(
                bg=self.SECTION_BG, border=self.BORDER_COLOR,
                accent=self.VALUE_COLOR
            )
        )
        att_layout = QVBoxLayout(attitude_group)
        att_layout.setContentsMargins(6, 6, 6, 6)
        att_layout.setSpacing(4)

        # Panda3D 3D Attitude Widget
        self.widget_3d_attitude = Attitude3DWidget()
        self.widget_3d_attitude.setMinimumSize(320 - 20, 240)
        self.widget_3d_attitude.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        att_layout.addWidget(self.widget_3d_attitude)

        # Instruments WebView (Compass + ADI)
        self.instruments_view = QWebEngineView()
        self.instruments_view.setFixedHeight(200)
        self.instruments_view.setStyleSheet(f"background: {self.SECTION_BG}; border: none;")
        self.instruments_view.page().setBackgroundColor(Qt.transparent)

        # Load instruments HTML
        instruments_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "assets", "instruments.html"
        )
        self.instruments_view.loadFinished.connect(self._on_instruments_loaded)
        self.instruments_view.setUrl(QUrl.fromLocalFile(instruments_path))

        att_layout.addWidget(self.instruments_view)
        content_layout.addWidget(attitude_group)

        # ═══════ SECTION 2: TELEMETRY FC ═══════
        telem_group = QGroupBox("THÔNG SỐ TELEMETRY FC")
        telem_group.setStyleSheet(
            self._GROUP_STYLE.format(
                bg=self.SECTION_BG, border=self.BORDER_COLOR,
                accent=self.VALUE_COLOR
            )
        )
        telem_layout = QGridLayout(telem_group)
        telem_layout.setContentsMargins(8, 8, 8, 8)
        telem_layout.setSpacing(3)
        telem_layout.setColumnStretch(0, 1)
        telem_layout.setColumnStretch(1, 1)

        # Telemetry fields — row by row
        row = 0

        # ARM status
        row = self._add_field(telem_layout, row, "Trạng thái", "val_armed", "DISARMED")
        # Attitude
        row = self._add_field(telem_layout, row, "Roll", "val_roll", "0.0°")
        row = self._add_field(telem_layout, row, "Pitch", "val_pitch", "0.0°")
        row = self._add_field(telem_layout, row, "Yaw", "val_yaw", "0.0°")

        # Separator
        row = self._add_separator(telem_layout, row)

        # Navigation
        row = self._add_field(telem_layout, row, "Độ cao (Baro)", "val_alt", "N/A")
        row = self._add_field(telem_layout, row, "Vận tốc", "val_spd", "N/A")
        row = self._add_field(telem_layout, row, "Vario", "val_vario", "N/A")
        row = self._add_field(telem_layout, row, "Latitude", "val_lat", "N/A")
        row = self._add_field(telem_layout, row, "Longitude", "val_lon", "N/A")

        # Separator
        row = self._add_separator(telem_layout, row)

        # GPS
        row = self._add_field(telem_layout, row, "GPS Fix", "val_gps_fix", "N/A")
        row = self._add_field(telem_layout, row, "Vệ tinh", "val_sats", "N/A")
        row = self._add_field(telem_layout, row, "HDOP", "val_gps_accuracy", "N/A")

        # Separator
        row = self._add_separator(telem_layout, row)

        # Power
        row = self._add_field(telem_layout, row, "Dòng điện", "val_current", "N/A")
        row = self._add_field(telem_layout, row, "Công suất", "val_power", "N/A")

        # Separator
        row = self._add_separator(telem_layout, row)

        # Sensors
        row = self._add_field(telem_layout, row, "LiDAR", "val_surface_alt", "N/A")
        row = self._add_field(telem_layout, row, "LiDAR Quality", "val_lidar_qual", "N/A")
        row = self._add_field(telem_layout, row, "Optical Flow", "val_opflow", "N/A")
        row = self._add_field(telem_layout, row, "RSSI", "val_rssi", "N/A")
        row = self._add_field(telem_layout, row, "Khoảng cách", "val_distance", "N/A")

        content_layout.addWidget(telem_group)
        content_layout.addStretch(1)

        scroll.setWidget(content)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        # Panel background
        self.setStyleSheet(f"""
            #leftPanel {{
                background-color: {self.DARK_BG};
                border-right: 1px solid {self.BORDER_COLOR};
            }}
        """)

    def _add_field(self, grid: QGridLayout, row: int,
                   label_text: str, attr_name: str, default: str) -> int:
        """Thêm một hàng Label | Value vào grid và gắn attribute."""
        lbl = QLabel(label_text)
        lbl.setFont(QFont(self.LABEL_FONT, 9))
        lbl.setStyleSheet(f"color: {self.MUTED};")

        val = QLabel(default)
        val.setFont(QFont(self.VALUE_FONT, 9, QFont.Bold))
        val.setStyleSheet(f"color: {self.VALUE_COLOR};")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        grid.addWidget(lbl, row, 0)
        grid.addWidget(val, row, 1)

        # Gắn attribute để GCSApp truy cập: self.left_panel.val_roll, v.v.
        setattr(self, attr_name, val)

        return row + 1

    def _add_separator(self, grid: QGridLayout, row: int) -> int:
        """Thêm separator ngang mỏng."""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {self.BORDER_COLOR};")
        grid.addWidget(sep, row, 0, 1, 2)
        return row + 1

    # ═══════ PUBLIC METHODS ═══════

    def update_instruments(self, heading: float, roll: float, pitch: float):
        """Cập nhật Compass + ADI instruments qua JavaScript."""
        if self._instruments_ready:
            js = f"updateInstruments({heading}, {roll}, {pitch});"
            self.instruments_view.page().runJavaScript(js)

    # ═══════ PRIVATE ═══════

    def _on_instruments_loaded(self, ok: bool):
        """Callback khi instruments.html đã load xong."""
        self._instruments_ready = ok
