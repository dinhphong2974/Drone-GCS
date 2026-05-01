"""
LeftToolbar — Thanh công cụ dọc 48px bên trái với các nút điều khiển.

Chứa: Toggle panel, Locate, ARM/DISARM, Takeoff, RTH, Settings.
Các nút flight control (ARM, Takeoff, RTH) được GCSApp kết nối signal.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QFrame, QToolTip
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QCursor


class LeftToolbar(QWidget):
    """
    Thanh icon dọc cố định 48px — chứa quick-action buttons.

    Signals:
        locate_clicked: Yêu cầu center map vào drone
        toggle_left_panel: Yêu cầu ẩn/hiện left panel

    Widget ownership cho GCSApp:
        btn_arm, btn_takeoff, btn_rth — flight control
        btn_settings — mở ConfigTab dialog
    """

    # ═══════ SIGNALS ═══════
    locate_clicked = Signal()
    toggle_left_panel = Signal()

    # ═══════ STYLE CONSTANTS ═══════
    DARK_BG = "#080c14"
    BORDER_COLOR = "#1a2332"
    HOVER_GLOW = "rgba(0, 255, 136, 0.15)"
    ICON_SIZE = 20
    BTN_SIZE = 40

    # Base button style
    _BTN_STYLE = """
        QPushButton {{
            background-color: transparent;
            color: #c0c8d8;
            border: 1px solid transparent;
            border-radius: 6px;
            font-size: {icon_size}px;
            min-width: {btn_size}px;
            min-height: {btn_size}px;
            max-width: {btn_size}px;
            max-height: {btn_size}px;
        }}
        QPushButton:hover {{
            background-color: {hover};
            border: 1px solid rgba(0, 255, 136, 0.3);
        }}
        QPushButton:pressed {{
            background-color: rgba(0, 255, 136, 0.25);
        }}
    """

    _BTN_DANGER_STYLE = """
        QPushButton {{
            background-color: rgba(255, 68, 68, 0.15);
            color: #ff4444;
            border: 1px solid rgba(255, 68, 68, 0.3);
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            min-width: {btn_size}px;
            min-height: {btn_size}px;
            max-width: {btn_size}px;
            max-height: {btn_size}px;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 68, 68, 0.3);
            border: 1px solid rgba(255, 68, 68, 0.6);
        }}
        QPushButton:pressed {{
            background-color: rgba(255, 68, 68, 0.4);
        }}
        QPushButton:disabled {{
            background-color: rgba(80, 80, 80, 0.2);
            color: #555;
            border: 1px solid #333;
        }}
    """

    _BTN_ACTION_STYLE = """
        QPushButton {{
            background-color: rgba(255, 152, 0, 0.15);
            color: #FF9800;
            border: 1px solid rgba(255, 152, 0, 0.3);
            border-radius: 6px;
            font-size: {icon_size}px;
            min-width: {btn_size}px;
            min-height: {btn_size}px;
            max-width: {btn_size}px;
            max-height: {btn_size}px;
        }}
        QPushButton:hover {{
            background-color: rgba(255, 152, 0, 0.3);
            border: 1px solid rgba(255, 152, 0, 0.6);
        }}
        QPushButton:pressed {{
            background-color: rgba(255, 152, 0, 0.4);
        }}
        QPushButton:disabled {{
            background-color: rgba(80, 80, 80, 0.2);
            color: #555;
            border: 1px solid #333;
        }}
    """

    _BTN_SUCCESS_STYLE = """
        QPushButton {{
            background-color: rgba(0, 255, 136, 0.1);
            color: #00ff88;
            border: 1px solid rgba(0, 255, 136, 0.3);
            border-radius: 6px;
            font-size: {icon_size}px;
            min-width: {btn_size}px;
            min-height: {btn_size}px;
            max-width: {btn_size}px;
            max-height: {btn_size}px;
        }}
        QPushButton:hover {{
            background-color: rgba(0, 255, 136, 0.25);
            border: 1px solid rgba(0, 255, 136, 0.5);
        }}
        QPushButton:pressed {{
            background-color: rgba(0, 255, 136, 0.35);
        }}
        QPushButton:disabled {{
            background-color: rgba(80, 80, 80, 0.2);
            color: #555;
            border: 1px solid #333;
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(48)
        self.setObjectName("leftToolbar")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignTop)

        # ── Navigation Buttons ──
        self.btn_menu = self._make_btn("☰", "Toggle Panel trái")
        self.btn_menu.clicked.connect(self.toggle_left_panel.emit)
        layout.addWidget(self.btn_menu)

        self.btn_locate = self._make_btn("🏠", "Định vị Drone trên bản đồ")
        self.btn_locate.clicked.connect(self.locate_clicked.emit)
        layout.addWidget(self.btn_locate)

        self.btn_waypoints = self._make_btn("📍", "Chế độ Waypoint")
        layout.addWidget(self.btn_waypoints)

        self.btn_settings = self._make_btn("⚙", "Cài đặt")
        layout.addWidget(self.btn_settings)

        # ── Separator ──
        layout.addWidget(self._separator())

        # ── Flight Control Buttons (đặc biệt, to hơn) ──
        self.btn_arm = self._make_btn(
            "ARM", "ARM / DISARM drone",
            style_template=self._BTN_DANGER_STYLE
        )
        self.btn_arm.setFont(QFont("Consolas", 8, QFont.Bold))
        layout.addWidget(self.btn_arm)

        self.btn_takeoff = self._make_btn(
            "🚀", "Cất cánh tự động",
            style_template=self._BTN_ACTION_STYLE
        )
        layout.addWidget(self.btn_takeoff)

        self.btn_rth = self._make_btn(
            "🏡", "Return To Home",
            style_template=self._BTN_SUCCESS_STYLE
        )
        layout.addWidget(self.btn_rth)

        # ── Spacer đẩy xuống đáy ──
        layout.addStretch(1)

        # ── Disconnect button ở cuối ──
        self.btn_disconnect = QPushButton("🔌")
        self.btn_disconnect.setToolTip("Kết nối / Ngắt kết nối")
        self.btn_disconnect.setFixedSize(self.BTN_SIZE, self.BTN_SIZE)
        self.btn_disconnect.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_disconnect.setStyleSheet(
            self._BTN_STYLE.format(
                icon_size=self.ICON_SIZE, btn_size=self.BTN_SIZE,
                hover=self.HOVER_GLOW
            )
        )
        layout.addWidget(self.btn_disconnect)

        # ── Background styling ──
        self.setStyleSheet(f"""
            #leftToolbar {{
                background-color: {self.DARK_BG};
                border-right: 1px solid {self.BORDER_COLOR};
            }}
        """)

    def _make_btn(self, text: str, tooltip: str, style_template: str = None) -> QPushButton:
        """Tạo nút icon chuẩn 40×40px."""
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(self.BTN_SIZE, self.BTN_SIZE)
        btn.setCursor(QCursor(Qt.PointingHandCursor))

        template = style_template or self._BTN_STYLE
        btn.setStyleSheet(
            template.format(
                icon_size=self.ICON_SIZE,
                btn_size=self.BTN_SIZE,
                hover=self.HOVER_GLOW
            )
        )
        return btn

    def _separator(self):
        """Tạo separator ngang mỏng."""
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedWidth(36)
        sep.setStyleSheet(f"color: {self.BORDER_COLOR};")
        return sep

    # ═══════ PUBLIC METHODS ═══════

    def set_arm_state(self, is_armed: bool):
        """Cập nhật giao diện nút ARM theo trạng thái."""
        if is_armed:
            self.btn_arm.setText("DISARM")
            self.btn_arm.setStyleSheet(
                self._BTN_DANGER_STYLE.format(
                    btn_size=self.BTN_SIZE, icon_size=self.ICON_SIZE
                )
            )
            self.btn_arm.setToolTip("DISARM drone")
        else:
            self.btn_arm.setText("ARM")
            self.btn_arm.setStyleSheet(
                self._BTN_DANGER_STYLE.format(
                    btn_size=self.BTN_SIZE, icon_size=self.ICON_SIZE
                )
            )
            self.btn_arm.setToolTip("ARM drone")

    def set_takeoff_state(self, state: str):
        """
        Cập nhật nút Takeoff dựa trên flight state.

        States: IDLE, TAKING_OFF, HOLDING, MANUAL_*, ABORTING
        """
        if state == "IDLE":
            self.btn_takeoff.setText("🚀")
            self.btn_takeoff.setToolTip("Cất cánh tự động")
            self.btn_takeoff.setStyleSheet(
                self._BTN_ACTION_STYLE.format(
                    icon_size=self.ICON_SIZE, btn_size=self.BTN_SIZE
                )
            )
            self.btn_takeoff.setEnabled(True)
        else:
            # Đang bay → nút ABORT
            self.btn_takeoff.setText("⛔")
            self.btn_takeoff.setToolTip("ABORT — Dừng bay ngay lập tức")
            self.btn_takeoff.setStyleSheet(
                self._BTN_DANGER_STYLE.format(
                    icon_size=self.ICON_SIZE, btn_size=self.BTN_SIZE
                )
            )

    def set_enabled_flight_controls(self, enabled: bool):
        """Bật/tắt tất cả nút flight control."""
        self.btn_arm.setEnabled(enabled)
        self.btn_takeoff.setEnabled(enabled)
        self.btn_rth.setEnabled(enabled)
