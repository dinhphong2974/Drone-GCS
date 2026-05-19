"""
gamepad_tab.py - Virtual drone gamepad page.

Mục tiêu:
- Mô phỏng tay cầm điều khiển drone thật
- Điều khiển cơ bản: throttle, pitch, roll, yaw
- Tốc độ tăng ga được giới hạn theo speed mode để cất cánh/hạ cánh mượt
- Hiển thị RC channels, throttle live, ước lượng motor output và lift-off zone
- Có nút emergency stop riêng, không trùng chức năng ARM/Takeoff/RTH
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QRadialGradient
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QButtonGroup, QSizePolicy, QProgressBar
)


from core.utils import clamp as _clamp


class AnalogStick(QWidget):
    """Thumbstick ảo cho throttle/yaw hoặc pitch/roll."""

    valueChanged = Signal(float, float)

    def __init__(self, title: str, subtitle: str, throttle_mode: bool = False, parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._throttle_mode = throttle_mode
        self._x = 0.0
        self._y = 0.0 if throttle_mode else 0.0
        self._pressed = False
        self.setMinimumSize(250, 250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)

    def sizeHint(self):
        return self.minimumSize()

    def set_values(self, x: float, y: float, emit: bool = False):
        if self._throttle_mode:
            self._x = _clamp(x, -1.0, 1.0)
            self._y = _clamp(y, 0.0, 1.0)
        else:
            self._x = _clamp(x, -1.0, 1.0)
            self._y = _clamp(y, -1.0, 1.0)
        self.update()
        if emit:
            self.valueChanged.emit(self._x, self._y)

    def normalized_values(self) -> tuple[float, float]:
        return self._x, self._y

    def _radius(self) -> float:
        return min(self.width(), self.height()) * 0.34

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _apply_position(self, pos: QPointF):
        center = self._center()
        radius = self._radius()
        dx = (pos.x() - center.x()) / radius
        dy = (center.y() - pos.y()) / radius
        dx = _clamp(dx, -1.0, 1.0)
        dy = _clamp(dy, -1.0, 1.0)

        if self._throttle_mode:
            self._x = dx
            self._y = _clamp((dy + 1.0) / 2.0, 0.0, 1.0)
        else:
            self._x = dx
            self._y = dy

        self.update()
        self.valueChanged.emit(self._x, self._y)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._apply_position(event.position())

    def mouseMoveEvent(self, event):
        if self._pressed:
            self._apply_position(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            if self._throttle_mode:
                self._x = 0.0
            else:
                self._x = 0.0
                self._y = 0.0
            self.update()
            self.valueChanged.emit(self._x, self._y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = self._center()
        radius = self._radius()
        outer = radius + 18

        background = QRadialGradient(center, outer)
        background.setColorAt(0.0, QColor(52, 58, 110, 170))
        background.setColorAt(0.65, QColor(24, 28, 52, 185))
        background.setColorAt(1.0, QColor(12, 16, 28, 220))
        painter.setPen(QPen(QColor(90, 95, 160, 150), 2))
        painter.setBrush(QBrush(background))
        painter.drawEllipse(center, outer, outer)

        painter.setPen(QPen(QColor(140, 145, 210, 120), 1))
        painter.drawEllipse(center, radius, radius)
        painter.drawLine(center.x() - radius, center.y(), center.x() + radius, center.y())
        painter.drawLine(center.x(), center.y() - radius, center.x(), center.y() + radius)

        painter.setPen(QPen(QColor(120, 125, 180, 80), 1, Qt.DashLine))
        painter.drawLine(center.x() - radius, center.y() - radius, center.x() + radius, center.y() + radius)
        painter.drawLine(center.x() - radius, center.y() + radius, center.x() + radius, center.y() - radius)

        if self._throttle_mode:
            knob_x = center.x() + self._x * radius
            knob_y = center.y() - ((self._y * 2.0) - 1.0) * radius
            x_text = f"X:{self._x:+.2f}"
            y_text = f"THR:{int(self._y * 100):02d}%"
        else:
            knob_x = center.x() + self._x * radius
            knob_y = center.y() - self._y * radius
            x_text = f"X:{self._x:+.2f}"
            y_text = f"Y:{self._y:+.2f}"

        knob_center = QPointF(knob_x, knob_y)
        knob_gradient = QRadialGradient(knob_center, 32)
        knob_gradient.setColorAt(0.0, QColor(170, 160, 255, 255))
        knob_gradient.setColorAt(0.6, QColor(106, 96, 255, 255))
        knob_gradient.setColorAt(1.0, QColor(56, 50, 148, 255))
        painter.setPen(QPen(QColor(210, 210, 255, 120), 2))
        painter.setBrush(QBrush(knob_gradient))
        painter.drawEllipse(knob_center, 22, 22)

        painter.setPen(QPen(QColor(230, 230, 255, 220), 1))
        painter.setFont(QFont("Consolas", 9, QFont.Bold))
        painter.drawText(0, 18, self.width(), 18, Qt.AlignCenter, self._title)

        painter.setFont(QFont("Consolas", 8))
        painter.setPen(QPen(QColor(150, 160, 220, 200), 1))
        painter.drawText(0, self.height() - 34, self.width(), 14, Qt.AlignCenter, x_text)
        painter.drawText(0, self.height() - 18, self.width(), 14, Qt.AlignCenter, y_text)

        painter.setPen(QPen(QColor(130, 140, 180, 180), 1))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(0, self.height() - 48, self.width(), 14, Qt.AlignCenter, self._subtitle)


class GamepadTab(QWidget):
    """Gamepad page để điều khiển drone thủ công bằng RC channels."""

    enabled_changed = Signal(bool)
    flight_mode_changed = Signal(str)
    speed_mode_changed = Signal(int)
    emergency_stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gamepad_enabled = False
        self._connected = False
        self._armed = False
        self._arming_requested = False
        self._fc_state = "IDLE"
        self._flight_mode = "MANUAL"
        self._hold_pos = False
        self._speed_mode = 60
        self._left_x = 0.0
        self._left_throttle = 0.0
        self._right_x = 0.0
        self._right_y = 0.0
        self._blocked_reason = ""
        self._preview_channels = [1500] * 8
        self._last_rc_ack_ts: float | None = None

        # ── Keyboard control state ──
        self._pressed_keys: set = set()
        # Throttle step (normalized 0-1) per tick, matches GamepadController.THROTTLE_STEPS
        self._THROTTLE_KB_STEPS = {30: 0.008, 60: 0.016, 100: 0.026}
        # Stick ramp: 0→1.0 in ~350ms at 20Hz tick rate
        self._STICK_RAMP_STEP = 0.15

        self._setup_ui()
        self._refresh_ui()
        self.setFocusPolicy(Qt.StrongFocus)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        shell = QFrame()
        shell.setObjectName("gamepadShell")
        shell.setStyleSheet("""
            QFrame#gamepadShell {
                background-color: #090d16;
                border: 1px solid #1a2332;
                border-radius: 18px;
            }
        """)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(18, 18, 18, 18)
        shell_layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        lbl_title = QLabel("Virtual Gamepad Controller")
        lbl_title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        lbl_title.setStyleSheet("color: #E8ECFF;")
        lbl_desc = QLabel("Tay cầm ảo cho drone: throttle tăng từ từ, stick trái/phải, emergency stop")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #8f96b8; font-size: 11px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_desc)
        header.addLayout(title_box, 1)

        self.btn_enable = QPushButton("▶ BẬT GAMEPAD")
        self.btn_enable.setCursor(Qt.PointingHandCursor)
        self.btn_enable.setMinimumHeight(44)
        self.btn_enable.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                min-width: 140px;
            }
            QPushButton:hover { background-color: #43A047; }
            QPushButton:pressed { background-color: #2E7D32; }
            QPushButton:disabled { background-color: #41524a; color: #96a39d; }
        """)
        self.btn_enable.clicked.connect(self._toggle_gamepad)
        header.addWidget(self.btn_enable)

        # Thêm nút ARM/DISARM chuyên dụng cho Gamepad
        self.btn_arm_toggle = QPushButton("ARM MOTOR")
        self.btn_arm_toggle.setCursor(Qt.PointingHandCursor)
        self.btn_arm_toggle.setMinimumHeight(44)
        self.btn_arm_toggle.setCheckable(True)
        self.btn_arm_toggle.setEnabled(False)  # Chờ bật khi Gamepad ON
        self.btn_arm_toggle.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                min-width: 120px;
            }
            QPushButton:checked { background-color: #1976D2; }
            QPushButton:hover { opacity: 0.8; }
            QPushButton:disabled { background-color: #4a2828; color: #916868; }
        """)
        self.btn_arm_toggle.clicked.connect(self._on_arm_toggled)
        header.addWidget(self.btn_arm_toggle)
        
        shell_layout.addLayout(header)

        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #0d111d;
                border: 1px solid #1d2940;
                border-radius: 12px;
            }
        """)
        status_layout = QGridLayout(status_frame)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setHorizontalSpacing(12)
        status_layout.setVerticalSpacing(8)

        self.lbl_connection = self._make_status_value("Disconnected", "#F44336")
        self.lbl_gamepad_state = self._make_status_value("OFF", "#9ca3af")
        self.lbl_fc_state = self._make_status_value("IDLE", "#E0E0E0")
        self.lbl_mode = self._make_status_value("MANUAL", "#4FC3F7")
        self.lbl_speed = self._make_status_value("60%", "#FFD54F")
        self.lbl_arm = self._make_status_value("DISARMED", "#F44336")
        self.lbl_rc_ack = self._make_status_value("No ACK", "#F44336")
        self.lbl_rc_ack_age = self._make_status_value("--", "#9ca3af")

        status_layout.addWidget(QLabel("Connection"), 0, 0)
        status_layout.addWidget(self.lbl_connection, 0, 1)
        status_layout.addWidget(QLabel("Gamepad"), 0, 2)
        status_layout.addWidget(self.lbl_gamepad_state, 0, 3)
        status_layout.addWidget(QLabel("FC State"), 0, 4)
        status_layout.addWidget(self.lbl_fc_state, 0, 5)

        status_layout.addWidget(QLabel("Flight Mode"), 1, 0)
        status_layout.addWidget(self.lbl_mode, 1, 1)
        status_layout.addWidget(QLabel("Speed Mode"), 1, 2)
        status_layout.addWidget(self.lbl_speed, 1, 3)
        status_layout.addWidget(QLabel("ARM"), 1, 4)
        status_layout.addWidget(self.lbl_arm, 1, 5)

        status_layout.addWidget(QLabel("RC ACK"), 2, 0)
        status_layout.addWidget(self.lbl_rc_ack, 2, 1)
        status_layout.addWidget(QLabel("ACK Age"), 2, 2)
        status_layout.addWidget(self.lbl_rc_ack_age, 2, 3)

        shell_layout.addWidget(status_frame)

        control_row = QHBoxLayout()
        control_row.setSpacing(14)

        self.left_stick = AnalogStick("THROTTLE + YAW", "Giữ ga bằng tay, xoay bằng x-axis", throttle_mode=True)
        self.right_stick = AnalogStick("PITCH + ROLL", "Tiến / lùi / trái / phải", throttle_mode=False)
        self.left_stick.valueChanged.connect(self._on_left_stick_changed)
        self.right_stick.valueChanged.connect(self._on_right_stick_changed)
        control_row.addWidget(self.left_stick, 1)

        center_panel = QFrame()
        center_panel.setStyleSheet("""
            QFrame {
                background-color: #0d111d;
                border: 1px solid #1d2940;
                border-radius: 12px;
            }
        """)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(10)

        mode_label = QLabel("Flight Mode")
        mode_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        mode_label.setStyleSheet("color: #b8c0e0;")
        center_layout.addWidget(mode_label)

        mode_row = QHBoxLayout()
        self.btn_angle = QPushButton("MANUAL")
        self.btn_althold = QPushButton("DIRECT")
        for btn in (self.btn_angle, self.btn_althold):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(36)
        self.btn_angle.clicked.connect(lambda: self._set_flight_mode("MANUAL"))
        self.btn_althold.clicked.connect(lambda: self._set_flight_mode("DIRECT"))
        mode_row.addWidget(self.btn_angle)
        mode_row.addWidget(self.btn_althold)
        center_layout.addLayout(mode_row)

        speed_label = QLabel("Speed Mode")
        speed_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        speed_label.setStyleSheet("color: #b8c0e0;")
        center_layout.addWidget(speed_label)

        speed_row = QHBoxLayout()
        self._speed_group = QButtonGroup(self)
        for value in (30, 60, 100):
            btn = QPushButton(f"{value}%")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(34)
            btn.clicked.connect(lambda checked=False, v=value: self._set_speed_mode(v))
            self._speed_group.addButton(btn, value)
            speed_row.addWidget(btn)
            setattr(self, f"btn_speed_{value}", btn)
        center_layout.addLayout(speed_row)

        self.btn_center_sticks = QPushButton("Center Sticks")
        self.btn_center_sticks.setCursor(Qt.PointingHandCursor)
        self.btn_center_sticks.clicked.connect(self.reset_sticks)
        center_layout.addWidget(self.btn_center_sticks)

        quick_text = QLabel(
            "Quick actions\n"
            "- Gamepad là manual RC thuần, không bật NAV mode\n"
            "- Mission Control giữ các chế độ auto / safety riêng\n"
            "- Throttle tăng dần để nhìn rõ điểm lift-off"
        )
        quick_text.setWordWrap(True)
        quick_text.setStyleSheet("color: #9aa3c7; font-size: 11px; line-height: 1.35;")
        center_layout.addWidget(quick_text)

        kb_legend = QLabel(
            "⌨ Keyboard Controls\n"
            "W/S: Throttle ↑↓ (giữ khi nhả)\n"
            "A/D: Yaw ←→ (về center)\n"
            "↑↓←→: Pitch/Roll (về center)"
        )
        kb_legend.setWordWrap(True)
        kb_legend.setStyleSheet(
            "color: #7fd4ff; font-size: 11px; line-height: 1.35;"
            "background-color: #0a0f1a; border: 1px solid #1d2940;"
            "border-radius: 6px; padding: 8px;"
        )
        center_layout.addWidget(kb_legend)

        self.btn_hold_pos = QPushButton("\U0001f6e1 HOLD POS OFF")
        self.btn_hold_pos.setCheckable(True)
        self.btn_hold_pos.setCursor(Qt.PointingHandCursor)
        self.btn_hold_pos.setMinimumHeight(44)
        self.btn_hold_pos.setStyleSheet("""
            QPushButton {
                background-color: #1a2332;
                color: #9ca3af;
                border: 2px solid #2d3a4f;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:checked {
                background-color: #1B5E20;
                color: #A5D6A7;
                border: 2px solid #4CAF50;
            }
            QPushButton:hover { border-color: #4FC3F7; }
        """)
        self.btn_hold_pos.toggled.connect(self._on_hold_pos_toggled)
        center_layout.addWidget(self.btn_hold_pos)

        self.btn_emergency = QPushButton("\u26d4 EMERGENCY STOP")
        self.btn_emergency.setCursor(Qt.PointingHandCursor)
        self.btn_emergency.setMinimumHeight(48)
        self.btn_emergency.setStyleSheet("""
            QPushButton {
                background-color: #E53935;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #EF5350; }
            QPushButton:pressed { background-color: #C62828; }
        """)
        self.btn_emergency.clicked.connect(self.emergency_stop_requested.emit)
        center_layout.addWidget(self.btn_emergency)
        center_layout.addStretch(1)

        control_row.addWidget(center_panel, 1)
        control_row.addWidget(self.right_stick, 1)
        shell_layout.addLayout(control_row)

        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet("""
            QFrame {
                background-color: #0d111d;
                border: 1px solid #1d2940;
                border-radius: 12px;
            }
        """)
        telemetry_layout = QVBoxLayout(telemetry_frame)
        telemetry_layout.setContentsMargins(12, 12, 12, 12)
        telemetry_layout.setSpacing(8)

        heading_row = QHBoxLayout()
        heading = QLabel("RC Preview & Motor Speed")
        heading.setFont(QFont("Segoe UI", 10, QFont.Bold))
        heading.setStyleSheet("color: #b8c0e0;")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        self.lbl_lift_hint = QLabel("Lift-off zone: 1450-1600 μs")
        self.lbl_lift_hint.setStyleSheet("color: #FFD54F; font-weight: bold;")
        heading_row.addWidget(self.lbl_lift_hint)
        telemetry_layout.addLayout(heading_row)

        throttle_row = QHBoxLayout()
        self.lbl_throttle_live = QLabel("Throttle Live: 1000 μs")
        self.lbl_throttle_live.setFont(QFont("Consolas", 11, QFont.Bold))
        self.lbl_throttle_live.setStyleSheet("color: #00ff88;")
        throttle_row.addWidget(self.lbl_throttle_live)
        throttle_row.addStretch(1)
        self.lbl_motor_est = QLabel("Estimated motor output: 0%")
        self.lbl_motor_est.setFont(QFont("Consolas", 11, QFont.Bold))
        self.lbl_motor_est.setStyleSheet("color: #7fd4ff;")
        throttle_row.addWidget(self.lbl_motor_est)
        telemetry_layout.addLayout(throttle_row)

        self.bar_throttle = QProgressBar()
        self.bar_throttle.setRange(1000, 2000)
        self.bar_throttle.setValue(1000)
        self.bar_throttle.setTextVisible(True)
        self.bar_throttle.setFormat("Throttle %v μs")
        self.bar_throttle.setStyleSheet("""
            QProgressBar {
                border: 1px solid #25314a;
                border-radius: 5px;
                background-color: #121826;
                text-align: center;
                color: #e5ecff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                border-radius: 4px;
                background-color: #4CAF50;
            }
        """)
        telemetry_layout.addWidget(self.bar_throttle)

        self._motor_bars = []
        motor_row = QGridLayout()
        motor_row.setHorizontalSpacing(8)
        motor_row.setVerticalSpacing(8)
        for index in range(4):
            label = QLabel(f"CH {index + 1}")
            label.setStyleSheet("color: #9aa3c7; font-size: 10px;")
            bar = QProgressBar()
            bar.setRange(1000, 2000)
            bar.setValue(1000)
            bar.setTextVisible(False)
            bar.setMaximumHeight(14)
            bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #25314a;
                    border-radius: 4px;
                    background-color: #121826;
                }
                QProgressBar::chunk {
                    border-radius: 3px;
                    background-color: #7c6cff;
                }
            """)
            value = QLabel("1000")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value.setStyleSheet("color: #cfd6f3; font-family: Consolas; font-weight: bold;")
            self._motor_bars.append((bar, value))
            motor_row.addWidget(label, index, 0)
            motor_row.addWidget(bar, index, 1)
            motor_row.addWidget(value, index, 2)
        telemetry_layout.addLayout(motor_row)

        shell_layout.addWidget(telemetry_frame)
        root.addWidget(shell)

        self._style_buttons()

    def _make_status_value(self, text: str, color: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(f"color: {color}; font-weight: bold;")
        return label

    def _style_buttons(self):
        base = """
            QPushButton {
                background-color: #12182a;
                color: #d9def3;
                border: 1px solid #24314b;
                border-radius: 7px;
                padding: 8px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #18213a;
                border-color: #42577d;
            }
            QPushButton:pressed {
                background-color: #0e1321;
            }
            QPushButton:checked {
                background-color: #273664;
                border-color: #4FC3F7;
                color: #ffffff;
            }
            QPushButton:disabled {
                background-color: #10131c;
                color: #4b5267;
                border-color: #20283b;
            }
        """
        for btn in (self.btn_angle, self.btn_althold, self.btn_center_sticks):
            btn.setStyleSheet(base)
        for name in ("btn_speed_30", "btn_speed_60", "btn_speed_100"):
            getattr(self, name).setStyleSheet(base)

    def _refresh_ui(self):
        self._set_flight_mode(self._flight_mode, emit=False)
        self._set_speed_mode(self._speed_mode, emit=False)
        self.set_connection_status(False, "Disconnected")
        self.set_armed(False)
        self.update_rc_preview([1500] * 8, 1000, 0, lift_off=False)
        self._update_rc_ack_label()

    def _restore_connection_label(self):
        if self._connected:
            self.lbl_connection.setText("Connected")
            self.lbl_connection.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.lbl_connection.setText("Disconnected")
            self.lbl_connection.setStyleSheet("color: #F44336; font-weight: bold;")

    def _toggle_gamepad(self):
        self._set_gamepad_enabled(not self._gamepad_enabled, emit=True)

    def _set_gamepad_enabled(self, enabled: bool, emit: bool = False):
        self._gamepad_enabled = enabled
        self.btn_enable.setText("■ TẮT GAMEPAD" if enabled else "▶ BẬT GAMEPAD")
        self.btn_enable.setStyleSheet("""
            QPushButton {
                background-color: #E53935;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                min-width: 140px;
            }
            QPushButton:hover { background-color: #EF5350; }
            QPushButton:pressed { background-color: #C62828; }
            QPushButton:disabled { background-color: #41524a; color: #96a39d; }
        """ if enabled else """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 10px 18px;
                min-width: 140px;
            }
            QPushButton:hover { background-color: #43A047; }
            QPushButton:pressed { background-color: #2E7D32; }
            QPushButton:disabled { background-color: #41524a; color: #96a39d; }
        """)
        
        self.btn_arm_toggle.setEnabled(enabled)
        if not enabled:
            self.btn_arm_toggle.setChecked(False)
            self._on_arm_toggled(False)
            self._pressed_keys.clear()  # Tránh stale keys khi re-enable
            # Reset HOLD POS
            self._hold_pos = False
            self.btn_hold_pos.blockSignals(True)
            self.btn_hold_pos.setChecked(False)
            self.btn_hold_pos.setText("\U0001f6e1 HOLD POS OFF")
            self.btn_hold_pos.blockSignals(False)
            
        self.lbl_gamepad_state.setText("ON" if enabled else "OFF")
        self.lbl_gamepad_state.setStyleSheet(
            f"color: {'#4CAF50' if enabled else '#9ca3af'}; font-weight: bold;"
        )
        if enabled:
            self.setFocus()  # Grab keyboard focus for gamepad controls
        if emit:
            self.enabled_changed.emit(enabled)

    def _on_arm_toggled(self, checked: bool):
        self._arming_requested = checked
        self.btn_arm_toggle.setText("DISARM MOTOR" if checked else "ARM MOTOR")
        self.btn_arm_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {'#1976D2' if checked else '#d32f2f'};
                color: white; font-weight: bold; border-radius: 8px;
                padding: 10px 18px;
                min-width: 120px;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
        """)
        # Đặt lại thanh ga về 0 khi chờ DISARM để an toàn
        if not checked:
            self.left_stick.set_values(0.0, 0.0, emit=True)

    def _set_flight_mode(self, mode: str, emit: bool = True):
        self._flight_mode = mode
        self.btn_angle.setChecked(mode == "MANUAL")
        self.btn_althold.setChecked(mode == "DIRECT")
        # Đồng bộ 2 chiều: DIRECT ↔ HOLD POS
        self._hold_pos = (mode == "DIRECT")
        self.btn_hold_pos.blockSignals(True)
        self.btn_hold_pos.setChecked(self._hold_pos)
        self.btn_hold_pos.setText(
            "\U0001f6e1 HOLD POS ON" if self._hold_pos else "\U0001f6e1 HOLD POS OFF"
        )
        self.btn_hold_pos.blockSignals(False)
        self.lbl_mode.setText(mode)
        self.lbl_mode.setStyleSheet(
            f"color: {'#4FC3F7' if mode == 'MANUAL' else '#FFD54F'}; font-weight: bold;"
        )
        if emit:
            self.flight_mode_changed.emit(mode)

    def _on_hold_pos_toggled(self, checked: bool):
        """Toggle HOLD POS → đồng bộ flight mode."""
        self._hold_pos = checked
        self.btn_hold_pos.setText(
            "\U0001f6e1 HOLD POS ON" if checked else "\U0001f6e1 HOLD POS OFF"
        )
        # Đồng bộ ngược → flight mode buttons
        self._set_flight_mode("DIRECT" if checked else "MANUAL")

    def _set_speed_mode(self, speed: int, emit: bool = True):
        self._speed_mode = speed
        self.btn_speed_30.setChecked(speed == 30)
        self.btn_speed_60.setChecked(speed == 60)
        self.btn_speed_100.setChecked(speed == 100)
        self.lbl_speed.setText(f"{speed}%")
        self.lbl_speed.setStyleSheet(
            f"color: {'#FFD54F' if speed == 30 else ('#FFB74D' if speed == 60 else '#FF8A65')}; font-weight: bold;"
        )
        if emit:
            self.speed_mode_changed.emit(speed)

    def _on_left_stick_changed(self, x: float, y: float):
        self._left_x = x
        self._left_throttle = y

    def _on_right_stick_changed(self, x: float, y: float):
        self._right_x = x
        self._right_y = y

    def is_gamepad_enabled(self) -> bool:
        return self._gamepad_enabled

    def get_control_state(self) -> dict:
        return {
            "enabled": self._gamepad_enabled,
            "connected": self._connected,
            "fc_state": self._fc_state,
            "flight_mode": self._flight_mode,
            "speed_mode": self._speed_mode,
            "left_x": self._left_x,
            "left_throttle": self._left_throttle,
            "right_x": self._right_x,
            "right_y": self._right_y,
            "blocked_reason": self._blocked_reason,
            "is_arming_requested": self._arming_requested,
            "hold_pos": self._hold_pos,
        }

    def set_connection_status(self, connected: bool, message: str = ""):
        self._connected = connected
        self.lbl_connection.setText(message or ("Connected" if connected else "Disconnected"))
        self.lbl_connection.setStyleSheet(
            f"color: {'#4CAF50' if connected else '#F44336'}; font-weight: bold;"
        )
        if not connected:
            self._last_rc_ack_ts = None
            self._update_rc_ack_label()
        self.btn_enable.setEnabled(connected)
        self.left_stick.setEnabled(connected)
        self.right_stick.setEnabled(connected)
        self.btn_center_sticks.setEnabled(connected)
        self.btn_angle.setEnabled(connected)
        self.btn_althold.setEnabled(connected)
        self.btn_speed_30.setEnabled(connected)
        self.btn_speed_60.setEnabled(connected)
        self.btn_speed_100.setEnabled(connected)
        self.btn_emergency.setEnabled(connected)
        self.btn_hold_pos.setEnabled(connected)
        if not connected:
            self._set_gamepad_enabled(False, emit=False)
            self.reset_sticks()

    def set_fc_state(self, state: str):
        self._fc_state = state or "IDLE"
        self.lbl_fc_state.setText(self._fc_state)
        color = "#00E676" if self._fc_state == "ARMED" else ("#FFD54F" if self._fc_state != "IDLE" else "#E0E0E0")
        self.lbl_fc_state.setStyleSheet(f"color: {color}; font-weight: bold;")

    def set_armed(self, is_armed: bool):
        self._armed = is_armed
        self.lbl_arm.setText("ARMED" if is_armed else "DISARMED")
        self.lbl_arm.setStyleSheet(
            f"color: {'#00E676' if is_armed else '#F44336'}; font-weight: bold;"
        )

    def set_blocked_reason(self, reason: str):
        self._blocked_reason = reason
        if reason:
            self.lbl_connection.setText(reason)
            self.lbl_connection.setStyleSheet("color: #FFD54F; font-weight: bold;")
        else:
            self._restore_connection_label()

    def reset_sticks(self):
        self.left_stick.set_values(0.0, 0.0, emit=True)
        self.right_stick.set_values(0.0, 0.0, emit=True)

    # ══════════════════════════════════════════════
    # KEYBOARD INPUT — Điều khiển bằng bàn phím
    # ══════════════════════════════════════════════

    def keyPressEvent(self, event):
        """Nhận phím điều khiển gamepad (WASD + Arrow keys)."""
        if event.isAutoRepeat():
            return
        key = event.key()
        if key in (Qt.Key_W, Qt.Key_S, Qt.Key_A, Qt.Key_D,
                   Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            self._pressed_keys.add(key)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Xử lý nhả phím: throttle giữ, stick trở về center."""
        if event.isAutoRepeat():
            return
        key = event.key()
        if key in self._pressed_keys:
            self._pressed_keys.discard(key)
            # Yaw (A/D): trở về center khi nhả
            if key in (Qt.Key_A, Qt.Key_D):
                self._left_x = 0.0
                self.left_stick.set_values(self._left_x, self._left_throttle)
            # Pitch (Up/Down): trở về center khi nhả
            elif key in (Qt.Key_Up, Qt.Key_Down):
                self._right_y = 0.0
                self.right_stick.set_values(self._right_x, self._right_y)
            # Roll (Left/Right): trở về center khi nhả
            elif key in (Qt.Key_Left, Qt.Key_Right):
                self._right_x = 0.0
                self.right_stick.set_values(self._right_x, self._right_y)
            # Throttle (W/S): KHÔNG reset — giữ nguyên vị trí (Mode 2)
        else:
            super().keyReleaseEvent(event)

    def update_keyboard_input(self):
        """Cập nhật giá trị stick từ phím đang nhấn. Gọi mỗi tick 20Hz."""
        if not self._pressed_keys:
            return

        step = self._THROTTLE_KB_STEPS.get(self._speed_mode, 0.016)
        ramp = self._STICK_RAMP_STEP

        # Throttle (W/S) — tăng/giảm dần, giữ khi nhả
        if Qt.Key_W in self._pressed_keys:
            self._left_throttle = min(1.0, self._left_throttle + step)
        if Qt.Key_S in self._pressed_keys:
            self._left_throttle = max(0.0, self._left_throttle - step)

        # Yaw (A/D) — ramp khi giữ, về center khi nhả
        if Qt.Key_A in self._pressed_keys:
            self._left_x = max(-1.0, self._left_x - ramp)
        elif Qt.Key_D in self._pressed_keys:
            self._left_x = min(1.0, self._left_x + ramp)

        # Pitch (Up/Down) — ramp khi giữ, về center khi nhả
        if Qt.Key_Up in self._pressed_keys:
            self._right_y = min(1.0, self._right_y + ramp)
        elif Qt.Key_Down in self._pressed_keys:
            self._right_y = max(-1.0, self._right_y - ramp)

        # Roll (Left/Right) — ramp khi giữ, về center khi nhả
        if Qt.Key_Left in self._pressed_keys:
            self._right_x = max(-1.0, self._right_x - ramp)
        elif Qt.Key_Right in self._pressed_keys:
            self._right_x = min(1.0, self._right_x + ramp)

        # Đồng bộ visual feedback lên AnalogStick widgets
        self.left_stick.set_values(self._left_x, self._left_throttle)
        self.right_stick.set_values(self._right_x, self._right_y)

    def update_rc_preview(
        self,
        channels: list[int],
        throttle_live: int,
        motor_pct: int,
        lift_off: bool = False,
        commanded_throttle: int | None = None,
    ):
        self._preview_channels = channels[:8]
        display_throttle = throttle_live if commanded_throttle is None else commanded_throttle
        self.lbl_throttle_live.setText(f"Throttle Live: {display_throttle} μs")
        self.lbl_motor_est.setText(f"Estimated motor output: {motor_pct}%")
        self.lbl_lift_hint.setText("Lift-off reached" if lift_off else "Lift-off zone: 1450-1600 μs")
        self.lbl_lift_hint.setStyleSheet(
            f"color: {'#4CAF50' if lift_off else '#FFD54F'}; font-weight: bold;"
        )
        self.bar_throttle.setValue(throttle_live)
        self._update_rc_ack_label()

        for index, (bar, value) in enumerate(self._motor_bars):
            channel_value = channels[index] if index < len(channels) else 1000
            bar.setValue(channel_value)
            value.setText(str(channel_value))

    def update_motor_feedback(self, motor_values: list[int]):
        for index, (bar, value) in enumerate(self._motor_bars):
            if index < len(motor_values):
                motor_value = int(motor_values[index])
                bar.setValue(motor_value)
                value.setText(str(motor_value))

    def mark_rc_ack(self):
        self._last_rc_ack_ts = time.monotonic()
        self._update_rc_ack_label()

    def _update_rc_ack_label(self):
        if self._last_rc_ack_ts is None:
            self.lbl_rc_ack.setText("No ACK")
            self.lbl_rc_ack.setStyleSheet("color: #F44336; font-weight: bold;")
            self.lbl_rc_ack_age.setText("--")
            self.lbl_rc_ack_age.setStyleSheet("color: #9ca3af; font-weight: bold;")
            return

        age = time.monotonic() - self._last_rc_ack_ts
        self.lbl_rc_ack.setText("RC OK")
        if age <= 0.5:
            color = "#00E676"
        elif age <= 1.5:
            color = "#FFD54F"
        else:
            color = "#F44336"
        self.lbl_rc_ack.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.lbl_rc_ack_age.setText(f"{age:.1f}s")
        self.lbl_rc_ack_age.setStyleSheet("color: #b9c2e0; font-weight: bold;")
