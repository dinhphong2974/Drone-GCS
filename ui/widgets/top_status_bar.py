"""
TopStatusBar — Thanh trạng thái 36px trên cùng của Mission Control.

Hiển thị: Tên app | Battery | WiFi + Ping | GPS | Flight Mode | UTC Time
Nhận dữ liệu qua các public method update_*() được gọi từ GCSApp.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from datetime import datetime, timezone


class TopStatusBar(QWidget):
    """
    Thanh trạng thái Mission Control — cố định 36px trên cùng.

    Widget ownership cho GCSApp truy cập:
    - lbl_batt_volt, lbl_batt_perc, bar_battery_volt (pin)
    - lbl_ping (ping RTT)
    - lbl_wifi_icon (trạng thái WiFi)
    - lbl_flight_mode (trạng thái bay / ARM)
    - btn_disconnect → nằm ở LeftToolbar, không ở đây
    """

    # ═══════ STYLE CONSTANTS ═══════
    DARK_BG = "#0a0e17"
    BORDER_COLOR = "#1a2332"
    TEXT_COLOR = "#c0c8d8"
    ACCENT_GREEN = "#00ff88"
    ACCENT_YELLOW = "#ffd700"
    ACCENT_RED = "#ff4444"
    MUTED = "#808098"
    FONT_MONO = "Consolas"
    FONT_UI = "Segoe UI"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setObjectName("topStatusBar")
        self._setup_ui()
        self._start_clock()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        # ── 1. App Name ──
        self.lbl_app_name = QLabel("🛸 Drone GCS")
        self.lbl_app_name.setFont(QFont(self.FONT_UI, 11, QFont.Bold))
        self.lbl_app_name.setStyleSheet(f"color: {self.ACCENT_GREEN}; padding-right: 8px;")
        layout.addWidget(self.lbl_app_name)

        layout.addWidget(self._separator())

        # ── 2. Battery ──
        self.lbl_batt_volt = QLabel("-- V")
        self.lbl_batt_volt.setFont(QFont(self.FONT_MONO, 9))
        self.lbl_batt_volt.setStyleSheet(f"color: {self.TEXT_COLOR}; padding: 0 4px;")
        layout.addWidget(self.lbl_batt_volt)

        self.bar_battery_volt = QProgressBar()
        self.bar_battery_volt.setFixedSize(60, 14)
        self.bar_battery_volt.setTextVisible(False)
        self.bar_battery_volt.setValue(0)
        self.bar_battery_volt.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 3px;
                background-color: #1a1a2e;
            }}
            QProgressBar::chunk {{
                border-radius: 2px;
                background-color: {self.MUTED};
            }}
        """)
        layout.addWidget(self.bar_battery_volt)

        self.lbl_batt_perc = QLabel("-- %")
        self.lbl_batt_perc.setFont(QFont(self.FONT_MONO, 9))
        self.lbl_batt_perc.setStyleSheet(f"color: {self.TEXT_COLOR}; padding: 0 4px;")
        layout.addWidget(self.lbl_batt_perc)

        layout.addWidget(self._separator())

        # ── 3. WiFi + Ping ──
        self.lbl_wifi_icon = QLabel("📶 ---")
        self.lbl_wifi_icon.setFont(QFont(self.FONT_UI, 9))
        self.lbl_wifi_icon.setStyleSheet(f"color: {self.MUTED}; padding: 0 6px;")
        layout.addWidget(self.lbl_wifi_icon)

        self.lbl_ping = QLabel("🏓 ---ms")
        self.lbl_ping.setFont(QFont(self.FONT_MONO, 9))
        self.lbl_ping.setStyleSheet(f"color: {self.MUTED}; padding: 0 6px;")
        layout.addWidget(self.lbl_ping)

        layout.addWidget(self._separator())

        # ── 4. GPS ──
        self.lbl_gps = QLabel("🛰 GPS: ---")
        self.lbl_gps.setFont(QFont(self.FONT_MONO, 9))
        self.lbl_gps.setStyleSheet(f"color: {self.MUTED}; padding: 0 6px;")
        layout.addWidget(self.lbl_gps)

        layout.addWidget(self._separator())

        # ── 5. Flight Mode ──
        self.lbl_flight_mode = QLabel("⏸ IDLE")
        self.lbl_flight_mode.setFont(QFont(self.FONT_UI, 9, QFont.Bold))
        self.lbl_flight_mode.setStyleSheet(f"color: {self.MUTED}; padding: 0 6px;")
        layout.addWidget(self.lbl_flight_mode)

        # ── Spacer ──
        layout.addStretch(1)

        # ── 6. UTC Clock ──
        self.lbl_clock = QLabel("--:--:-- UTC")
        self.lbl_clock.setFont(QFont(self.FONT_MONO, 9))
        self.lbl_clock.setStyleSheet(f"color: {self.TEXT_COLOR}; padding: 0 4px;")
        layout.addWidget(self.lbl_clock)

        # ── Background styling ──
        self.setStyleSheet(f"""
            #topStatusBar {{
                background-color: {self.DARK_BG};
                border-bottom: 1px solid {self.BORDER_COLOR};
            }}
        """)

    def _separator(self):
        """Tạo separator dọc mỏng giữa các section."""
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"color: {self.BORDER_COLOR};")
        return sep

    def _start_clock(self):
        """Khởi chạy đồng hồ UTC cập nhật mỗi giây."""
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start()
        self._update_clock()

    # ═══════ PUBLIC UPDATE METHODS ═══════

    def update_battery(self, voltage: float, percent: int):
        """Cập nhật hiển thị pin Lipo 6S."""
        self.lbl_batt_volt.setText(f"{voltage:.1f}V")
        self.lbl_batt_perc.setText(f"{percent}%")
        self.bar_battery_volt.setValue(percent)

        if percent > 50:
            color = self.ACCENT_GREEN
        elif percent > 20:
            color = self.ACCENT_YELLOW
        else:
            color = self.ACCENT_RED

        self.lbl_batt_volt.setStyleSheet(f"color: {color}; padding: 0 4px;")
        self.lbl_batt_perc.setStyleSheet(f"color: {color}; padding: 0 4px;")
        self.bar_battery_volt.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 3px;
                background-color: #1a1a2e;
            }}
            QProgressBar::chunk {{
                border-radius: 2px;
                background-color: {color};
            }}
        """)

    def update_connection(self, is_connected: bool):
        """Cập nhật trạng thái WiFi."""
        if is_connected:
            self.lbl_wifi_icon.setText("📶 Đã kết nối")
            self.lbl_wifi_icon.setStyleSheet(f"color: {self.ACCENT_GREEN}; padding: 0 6px;")
        else:
            self.lbl_wifi_icon.setText("📶 Mất kết nối")
            self.lbl_wifi_icon.setStyleSheet(f"color: {self.MUTED}; padding: 0 6px;")

    def update_ping(self, rtt_ms: int):
        """Cập nhật ping RTT với màu theo chất lượng."""
        self.lbl_ping.setText(f"🏓 {rtt_ms}ms")
        if rtt_ms <= 50:
            color = self.ACCENT_GREEN
        elif rtt_ms <= 150:
            color = self.ACCENT_YELLOW
        elif rtt_ms <= 300:
            color = "#FF9800"  # cam
        else:
            color = self.ACCENT_RED
        self.lbl_ping.setStyleSheet(f"color: {color}; padding: 0 6px;")

    def update_gps(self, fix_type: int, num_sat: int, hdop: float = 0.0):
        """Cập nhật thông tin GPS."""
        fix_text = "No Fix" if fix_type == 0 else ("2D" if fix_type == 1 else "3D")
        self.lbl_gps.setText(f"🛰 {fix_text} {num_sat}SVs HDOP:{hdop:.1f}")

        if fix_type >= 2 and num_sat >= 8:
            color = self.ACCENT_GREEN
        elif fix_type >= 1 and num_sat >= 4:
            color = self.ACCENT_YELLOW
        else:
            color = self.ACCENT_RED
        self.lbl_gps.setStyleSheet(f"color: {color}; padding: 0 6px;")

    def update_flight_mode(self, mode_text: str, color: str = None):
        """Cập nhật trạng thái bay / flight mode."""
        self.lbl_flight_mode.setText(mode_text)
        c = color or self.TEXT_COLOR
        self.lbl_flight_mode.setStyleSheet(f"color: {c}; padding: 0 6px; font-weight: bold;")

    def update_armed_status(self, is_armed: bool):
        """Cập nhật trạng thái ARM/DISARM."""
        if is_armed:
            self.lbl_flight_mode.setText("🔴 ARMED")
            self.lbl_flight_mode.setStyleSheet(
                f"color: {self.ACCENT_RED}; padding: 0 6px; font-weight: bold;"
            )
        else:
            self.lbl_flight_mode.setText("🟢 DISARMED")
            self.lbl_flight_mode.setStyleSheet(
                f"color: {self.ACCENT_GREEN}; padding: 0 6px; font-weight: bold;"
            )

    # ═══════ PRIVATE ═══════

    def _update_clock(self):
        """Cập nhật đồng hồ UTC."""
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.lbl_clock.setText(f"{now} UTC")
