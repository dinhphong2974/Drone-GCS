"""
main.py - Điểm khởi chạy ứng dụng Drone Ground Control Station.

File này CHỈ đóng vai trò:
1. Khởi tạo cửa sổ giao diện (MainWindow)
2. Kết nối Signal/Slot giữa các module (WifiWorker ↔ UI)
3. Quản lý vòng đời ứng dụng (mở/đóng kết nối)

Kiến trúc module:
    main.py → khởi tạo + điều phối Signal/Slot
    ui/main_window.py → cửa sổ chính (Single-Screen Mission Control)
    ui/widgets/ → TopStatusBar, LeftToolbar, LeftPanel, RightPanel
    ui/map_panel.py → bản đồ Leaflet + waypoint overlay
    ui/config_tab.py → cấu hình (QDialog)
    ui/emergency_overlay.py → overlay cảnh báo khẩn cấp
    comm/wifi_client.py → kết nối TCP thô
    comm/wifi_worker.py → QThread chạy ngầm
    comm/msp_parser.py → giải mã giao thức MSP
    core/drone_state.py → trạng thái drone chia sẻ
    core/flight_controller.py → state machine bay tự động
"""

import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout,
                                QHBoxLayout, QLineEdit, QPushButton, QLabel,
                                QMessageBox, QDoubleSpinBox)
from ui.main_window import MainWindow
from ui.emergency_overlay import EmergencyOverlay
from comm.wifi_worker import WifiWorker
from core.drone_state import DroneState
from core.flight_controller import FlightController
from core.gamepad_controller import GamepadController
from core.utils import clamp as _clamp
from ui.map_panel import haversine_distance

# ── Thông số pin Lipo 6S ──
LIPO_6S_MIN_VOLTAGE = 19.8  # Điện áp rỗng (V)
LIPO_6S_MAX_VOLTAGE = 25.2  # Điện áp đầy (V)


class ConnectionDialog(QDialog):
    """Cửa sổ cấu hình kết nối Wifi tới ESP32."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kết nối ESP32 - Wifi")
        self.setFixedSize(320, 150)
        self.setup_ui()

        self.selected_ip = None
        self.selected_port = None
        self.is_mock_selected = False

    def setup_ui(self):
        """Xây dựng giao diện dialog nhập IP/Port."""
        layout = QVBoxLayout(self)

        # Nhập IP của ESP32
        h_ip = QHBoxLayout()
        h_ip.addWidget(QLabel("IP ESP32:"))
        self.input_ip = QLineEdit("192.168.4.1")  # IP mặc định của ESP32 AP
        h_ip.addWidget(self.input_ip)
        layout.addLayout(h_ip)

        # Nhập Port giao tiếp
        h_port = QHBoxLayout()
        h_port.addWidget(QLabel("Port TCP:"))
        self.input_port = QLineEdit("8080")
        h_port.addWidget(self.input_port)
        layout.addLayout(h_port)

        # Các nút bấm
        h_btns = QHBoxLayout()
        self.btn_connect = QPushButton("🛜 Kết Nối Wifi")
        self.btn_connect.clicked.connect(self.accept_connection)

        self.btn_mock = QPushButton("🧪 Mock Test")
        self.btn_mock.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_mock.clicked.connect(self.accept_mock)

        h_btns.addWidget(self.btn_connect)
        h_btns.addWidget(self.btn_mock)
        layout.addLayout(h_btns)

    def accept_connection(self):
        """Xác nhận kết nối thật: validate IP và Port trước khi đóng dialog."""
        ip = self.input_ip.text().strip()
        port = self.input_port.text().strip()
        if ip and port.isdigit():
            self.selected_ip = ip
            self.selected_port = port
            self.is_mock_selected = False
            self.accept()
        else:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập IP và Port hợp lệ!")

    def accept_mock(self):
        """Chọn chế độ giả lập (Mock Test) để test UI không cần phần cứng."""
        self.is_mock_selected = True
        self.accept()


class TakeoffDialog(QDialog):
    """
    Dialog nhập độ cao mong muốn khi cất cánh.

    Cho phép người dùng chọn độ cao (1-50m) trước khi drone cất cánh.
    Kết hợp GPS BZ 251 để giữ vị trí chính xác (Position Hold).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚀 Cấu hình Takeoff")
        self.setFixedSize(380, 200)
        self.target_altitude = 3.0  # Mặc định 3m
        self._setup_ui()

    def _setup_ui(self):
        """Xây dựng giao diện dialog nhập độ cao."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Tiêu đề
        lbl_title = QLabel("⚠️ Drone sẽ tự động ARM, cất cánh và giữ vị trí.\n"
                          "Đảm bảo khu vực an toàn trước khi tiếp tục!")
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet("color: #FFD54F; font-weight: bold; font-size: 12px; border: none;")
        layout.addWidget(lbl_title)

        # Nhập độ cao
        alt_layout = QHBoxLayout()
        lbl_alt = QLabel("Độ cao mục tiêu:")
        lbl_alt.setStyleSheet("font-weight: bold; font-size: 13px;")
        alt_layout.addWidget(lbl_alt)

        self.spin_altitude = QDoubleSpinBox()
        self.spin_altitude.setRange(1.0, 50.0)
        self.spin_altitude.setValue(3.0)
        self.spin_altitude.setSuffix(" mét")
        self.spin_altitude.setDecimals(1)
        self.spin_altitude.setSingleStep(0.5)
        self.spin_altitude.setStyleSheet(
            "QDoubleSpinBox { background-color: #252540; color: #d0d0e8; "
            "border: 1px solid #2a2a4a; border-radius: 6px; padding: 8px; "
            "font-size: 16px; font-weight: bold; }"
        )
        alt_layout.addWidget(self.spin_altitude)
        layout.addLayout(alt_layout)

        # Thông tin GPS
        self.lbl_gps_info = QLabel("📡 GPS: Đang chờ dữ liệu...")
        self.lbl_gps_info.setStyleSheet("color: #808098; font-size: 11px;")
        layout.addWidget(self.lbl_gps_info)

        # Nút xác nhận
        btn_layout = QHBoxLayout()

        btn_cancel = QPushButton("❌ Hủy")
        btn_cancel.setStyleSheet(
            "QPushButton { background-color: #F44336; color: white; font-weight: bold; "
            "border-radius: 6px; padding: 10px; font-size: 13px; }"
            "QPushButton:hover { background-color: #E53935; }"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_confirm = QPushButton("🚀 Cất cánh")
        btn_confirm.setEnabled(False)  # v3 FIX T3: Disable cho đến khi GPS OK
        btn_confirm.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-weight: bold; "
            "border-radius: 6px; padding: 10px; font-size: 13px; }"
            "QPushButton:hover { background-color: #43A047; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm = btn_confirm  # v3: Giữ reference để enable/disable
        btn_layout.addWidget(btn_confirm)

        layout.addLayout(btn_layout)

    def _on_confirm(self):
        """Lưu độ cao đã chọn và đóng dialog."""
        self.target_altitude = self.spin_altitude.value()
        self.accept()

    def update_gps_info(self, fix_type: int, num_sat: int, lat: float, lon: float):
        """
        Cập nhật thông tin GPS hiện tại trên dialog.

        Args:
            fix_type: 0=No fix, 1=2D, 2=3D
            num_sat: Số vệ tinh
            lat, lon: Tọa độ hiện tại
        """
        fix_text = "No Fix" if fix_type == 0 else ("2D" if fix_type == 1 else "3D ✓")
        color = "#4CAF50" if fix_type >= 2 else "#F44336"
        self.lbl_gps_info.setText(
            f"📡 GPS: {fix_text} | {num_sat} sats | ({lat:.6f}, {lon:.6f})"
        )
        self.lbl_gps_info.setStyleSheet(f"color: {color}; font-size: 11px;")

        # v3 FIX T3: Chỉ cho nhấn Cất cánh khi GPS 3D Fix + 6+ sats
        self.btn_confirm.setEnabled(fix_type >= 2 and num_sat >= 6)


class GCSApp(MainWindow):
    """
    Lớp ứng dụng chính — kế thừa MainWindow và thêm logic điều phối.

    MainWindow xây dựng UI layout, GCSApp kết nối Signal/Slot:
    - WifiWorker.connection_status → handle_connection_status
    - WifiWorker.telemetry_data → update_telemetry_ui
    - FlightController.state_changed → _on_flight_state_changed
    - FlightController.mode_activated → emergency overlay
    - btn_disconnect.clicked → toggle_connection
    """

    def __init__(self):
        super().__init__()

        # Gắn sự kiện cho nút kết nối/ngắt kết nối
        self.btn_disconnect.clicked.connect(self.toggle_connection)

        self.worker: WifiWorker | None = None

        # ── Trạng thái drone chia sẻ ──
        self.drone_state = DroneState()

        # ── Flight Controller (state machine bay tự động) ──
        self.flight_controller = FlightController(self.drone_state, parent=self)
        self.flight_controller.status_update.connect(self._on_flight_status)
        self.flight_controller.takeoff_complete.connect(self._on_takeoff_complete)
        self.flight_controller.error_occurred.connect(self._on_flight_error)
        self.flight_controller.state_changed.connect(self._on_flight_state_changed)
        self.flight_controller.mode_activated.connect(self._on_mode_activated)

        # ── Emergency Overlay (cảnh báo khẩn cấp) ──
        self.emergency_overlay = EmergencyOverlay(self)
        self.emergency_overlay.btn_emergency_disarm.clicked.connect(self._emergency_force_disarm)
        self.emergency_overlay.btn_emergency_safe_land.clicked.connect(self._emergency_force_safe_land)

        # ── Gamepad page (virtual manual RC) ──
        self._gamepad_ctrl = GamepadController()
        self._gamepad_rc_timer = QTimer(self)
        self._gamepad_rc_timer.setInterval(50)
        self._gamepad_rc_timer.timeout.connect(self._tick_gamepad_rc)
        self.gamepad_tab.enabled_changed.connect(self._on_gamepad_enabled_changed)
        self.gamepad_tab.flight_mode_changed.connect(self._on_gamepad_flight_mode_changed)
        self.gamepad_tab.speed_mode_changed.connect(self._on_gamepad_speed_mode_changed)
        self.gamepad_tab.emergency_stop_requested.connect(self._on_gamepad_emergency_stop)

        # ── Kết nối nút điều khiển bay (từ LeftToolbar) ──
        tb = self.left_toolbar
        tb.btn_arm.clicked.connect(self._on_toolbar_arm_clicked)
        tb.btn_takeoff.clicked.connect(self._confirm_takeoff)
        tb.btn_manual_takeoff.clicked.connect(self._confirm_manual_takeoff)
        tb.btn_rth.clicked.connect(self.flight_controller.rth)

        # ── Kết nối nút mission (từ MapPanel) ──
        mt = self.map_panel
        mt.btn_upload.clicked.connect(self._upload_mission)
        mt.btn_start_mission_tab.clicked.connect(self._start_mission)
        mt.btn_stop_mission.clicked.connect(self._stop_mission)

        # ── Cờ cảnh báo khoảng cách (tránh hiện dialog lặp) ──
        self._distance_warning_shown = False

        # ── Cờ chống xử lý disconnect trùng lặp ──
        self._disconnect_handled = False

        # ── Timer phát hiện mất PONG (ping timeout) ──
        self._ping_timeout_timer = QTimer(self)
        self._ping_timeout_timer.setInterval(3000)
        self._ping_timeout_timer.setSingleShot(True)
        self._ping_timeout_timer.timeout.connect(self._on_ping_timeout)

        # Khởi chạy ở trạng thái chưa có mạng
        self.set_ui_state_na()

    # ══════════════════════════════════════════════
    # QUẢN LÝ KẾT NỐI
    # ══════════════════════════════════════════════

    def toggle_connection(self):
        """Xử lý nút bấm Top Bar: Mở bảng kết nối hoặc ngắt kết nối an toàn."""
        if self.worker is not None:
            # Đang có kết nối → NGẮT KẾT NỐI
            self._disconnect_handled = True  # Chặn handle_connection_status xử lý trùng
            self.flight_controller.abort()  # Dừng bay tự động nếu đang chạy
            self.flight_controller.set_worker(None)
            self.worker.stop()
            self.worker.wait(3000)  # Chờ tối đa 3s cho thread dọn dẹp (tránh đơ)
            self.worker = None
            self._gamepad_rc_timer.stop()
            self.drone_state.reset()
            self.set_ui_state_na()
            self.emergency_overlay.hide_overlay()
            self.setWindowTitle("Drone Ground Station - Đã ngắt kết nối")
            # Không hiện QMessageBox — người dùng đã tự nhấn nút, title bar đủ thông tin
        else:
            # Chưa có kết nối → MỞ DIALOG KẾT NỐI
            self._disconnect_handled = False
            dialog = ConnectionDialog(self)
            if dialog.exec() == QDialog.Accepted:
                self.start_connection(dialog.selected_ip, dialog.selected_port, dialog.is_mock_selected)

    def start_connection(self, ip, port, is_mock):
        """
        Khởi tạo WifiWorker và kết nối Signal/Slot.

        Đây là điểm duy nhất kết nối các module lại với nhau.
        """
        self.worker = WifiWorker(ip=ip, port=port, is_mock=is_mock)

        # Kết nối Signal từ worker tới các slot xử lý trên UI
        self.worker.connection_status.connect(self.handle_connection_status)
        self.worker.telemetry_data.connect(self.update_telemetry_ui)
        self.worker.ping_updated.connect(self._on_ping_updated)
        self.worker.command_acked.connect(self._on_command_acked)

        self.gamepad_tab.set_connection_status(True, f"Connected: {ip}:{port}")

        # Cấp worker cho FlightController để gửi lệnh
        self.flight_controller.set_worker(self.worker)

        # Khởi chạy thread ngầm
        self.worker.start()

        self._distance_warning_shown = False
        self._disconnect_handled = False

    # ══════════════════════════════════════════════
    # SLOT: XỬ LÝ TÍN HIỆU TỪ WORKER
    # ══════════════════════════════════════════════

    def handle_connection_status(self, success: bool, message: str):
        """Slot xử lý tín hiệu trạng thái mạng từ WifiWorker."""
        if success:
            self.setWindowTitle(f"Drone Ground Station - {message}")
            self.drone_state.is_connected = True
            self.enable_ui_components()
            self.gamepad_tab.set_connection_status(True, message)
        else:
            # Guard: nếu toggle_connection() đã cleanup rồi → bỏ qua
            if self._disconnect_handled or self.worker is None:
                return
            self._disconnect_handled = True
            # Kết nối thất bại HOẶC bị đứt giữa chừng
            self.flight_controller.abort()
            self.flight_controller.set_worker(None)
            self._gamepad_rc_timer.stop()
            self.gamepad_tab.set_connection_status(False, "Disconnected")
            self.worker = None
            self.drone_state.reset()
            self.set_ui_state_na()
            self.emergency_overlay.hide_overlay()
            self.setWindowTitle("Drone Ground Station - Mất kết nối")
            QMessageBox.warning(self, "Cảnh báo Mạng", message)

    def update_telemetry_ui(self, data: dict):
        """
        Slot cập nhật dữ liệu telemetry từ FC lên giao diện.

        Nhận dict đã giải mã từ WifiWorker qua Signal,
        chỉ cập nhật các trường có dữ liệu mới.

        Widget mapping (v2 Mission Control):
            left_panel.val_*  ← telemetry values
            top_bar           ← battery, GPS summary, flight mode
            map_panel         ← drone position on map
        """
        lp = self.left_panel

        # ── Cập nhật điện áp pin Lipo 6S ──
        if "voltage" in data:
            v = data["voltage"]
            self.drone_state.voltage = v
            percent = int(((v - LIPO_6S_MIN_VOLTAGE) / (LIPO_6S_MAX_VOLTAGE - LIPO_6S_MIN_VOLTAGE)) * 100)
            percent = max(0, min(100, percent))
            self.top_bar.update_battery(v, percent)

        if "current" in data:
            self.drone_state.current = data["current"]
            lp.val_current.setText(f"{data['current']:.1f} A")
            lp.val_current.setStyleSheet("color: #00ff88; font-weight: bold;")

        # ── Cập nhật góc nghiêng + đồng bộ vào drone_state ──
        if "roll" in data:
            self.drone_state.roll = data["roll"]
            lp.val_roll.setText(f"{data['roll']:.1f}°")
        if "pitch" in data:
            self.drone_state.pitch = data["pitch"]
            lp.val_pitch.setText(f"{data['pitch']:.1f}°")
        if "yaw" in data:
            self.drone_state.yaw = data["yaw"]
            lp.val_yaw.setText(f"{data['yaw']:.1f}°")

        # ── Cập nhật Attitude 3D Widget (Panda3D) + Instruments ──
        if any(k in data for k in ("roll", "pitch", "yaw")):
            lp.widget_3d_attitude.update_attitude(
                self.drone_state.roll,
                self.drone_state.pitch,
                self.drone_state.yaw,
            )
            # Cập nhật Compass + ADI instruments
            lp.update_instruments(
                self.drone_state.yaw,
                self.drone_state.roll,
                self.drone_state.pitch,
            )

        # ── Cập nhật độ cao từ barometer (MSP_ALTITUDE) ──
        if "altitude" in data:
            alt = data["altitude"]
            self.drone_state.altitude = alt
            lp.val_alt.setText(f"{alt:.1f} m")
            lp.val_alt.setStyleSheet("color: #2196F3; font-weight: bold;")

        if "vario" in data:
            self.drone_state.vario = data["vario"]
            lp.val_vario.setText(f"{data['vario']:.1f} m/s")

        # ── Cập nhật trạng thái ARM từ FC (MSP_STATUS) ──
        if "is_armed" in data:
            self.drone_state.is_armed = data["is_armed"]
            self.top_bar.update_armed_status(data["is_armed"])
            self.left_toolbar.set_arm_state(data["is_armed"])
            self.gamepad_tab.set_armed(data["is_armed"])
            if data["is_armed"] and not self.flight_controller.is_active:
                self.gamepad_tab.set_fc_state("ARMED")
            elif not data["is_armed"]:
                self.gamepad_tab.set_fc_state("IDLE")

            disarm_in_progress = self.flight_controller.state in (
                "FORCE_DISARMING",
                "DISARMING",
                "NAV_OFF_BEFORE_DISARM",
            )

            if data["is_armed"]:
                lp.val_armed.setText("ARMED")
                lp.val_armed.setStyleSheet("color: #ff4444; font-weight: bold;")

                if disarm_in_progress:
                    if self.emergency_overlay.isVisible():
                        self.emergency_overlay.hide_overlay()
                elif not self.emergency_overlay.isVisible():
                    self.emergency_overlay.show_with_mode("Armed")

                if not self.drone_state.has_home and self.drone_state.latitude != 0.0:
                    self.drone_state.home_lat = self.drone_state.latitude
                    self.drone_state.home_lon = self.drone_state.longitude
                    self.drone_state.has_home = True
                    self.map_panel.update_home_position(
                        self.drone_state.home_lat, self.drone_state.home_lon
                    )
            else:
                lp.val_armed.setText("DISARMED")
                lp.val_armed.setStyleSheet("color: #00ff88; font-weight: bold;")

                if self.emergency_overlay.isVisible() and not self.flight_controller.is_active:
                    self.emergency_overlay.hide_overlay()

        if "flight_mode_flags" in data:
            self.drone_state.flight_mode_flags = data["flight_mode_flags"]

        # ── Motor telemetry → Gamepad feedback ──
        if "motor1" in data or "motor2" in data or "motor3" in data or "motor4" in data:
            motors = [
                int(data.get("motor1", 1000)),
                int(data.get("motor2", 1000)),
                int(data.get("motor3", 1000)),
                int(data.get("motor4", 1000)),
            ]
            for index, motor_value in enumerate(motors, start=1):
                motor_label = getattr(lp, f"val_motor{index}", None)
                motor_bar = getattr(lp, f"bar_motor{index}", None)
                if motor_label is not None:
                    motor_label.setText(str(motor_value))
                if motor_bar is not None:
                    motor_bar.setValue(motor_value)
            self.gamepad_tab.update_motor_feedback(motors)

        # ══════════════════════════════════════════════
        # CẬP NHẬT GPS DATA (từ GPS BZ 251 qua MSP_RAW_GPS)
        # ══════════════════════════════════════════════

        if "gps_fix_type" in data:
            self.drone_state.gps_fix_type = data["gps_fix_type"]
            fix_text = "No Fix" if data["gps_fix_type"] == 0 else (
                "2D" if data["gps_fix_type"] == 1 else "3D ✓"
            )
            fix_color = "#00ff88" if data["gps_fix_type"] >= 2 else "#ff4444"
            lp.val_gps_fix.setText(fix_text)
            lp.val_gps_fix.setStyleSheet(f"color: {fix_color}; font-weight: bold;")

        if "gps_num_sat" in data:
            self.drone_state.gps_num_sat = data["gps_num_sat"]
            lp.val_sats.setText(str(data["gps_num_sat"]))
            sat_color = "#00ff88" if data["gps_num_sat"] >= 6 else "#ffd700"
            lp.val_sats.setStyleSheet(f"color: {sat_color}; font-weight: bold;")

        if "gps_hdop" in data:
            self.drone_state.gps_hdop = data["gps_hdop"]
            lp.val_gps_accuracy.setText(f"{data['gps_hdop']:.2f}")
            acc_color = "#00ff88" if data["gps_hdop"] < 2.5 else ("#ffd700" if data["gps_hdop"] < 5.0 else "#ff4444")
            lp.val_gps_accuracy.setStyleSheet(f"color: {acc_color}; font-weight: bold;")

        # Cập nhật GPS summary trên top bar
        if "gps_fix_type" in data or "gps_num_sat" in data or "gps_hdop" in data:
            self.top_bar.update_gps(
                self.drone_state.gps_fix_type,
                self.drone_state.gps_num_sat,
                self.drone_state.gps_hdop
            )

        if "latitude" in data:
            self.drone_state.latitude = data["latitude"]
            lp.val_lat.setText(f"{data['latitude']:.6f}")
            lp.val_lat.setStyleSheet("color: #2196F3; font-weight: bold;")

        if "longitude" in data:
            self.drone_state.longitude = data["longitude"]
            lp.val_lon.setText(f"{data['longitude']:.6f}")
            lp.val_lon.setStyleSheet("color: #2196F3; font-weight: bold;")

        if "ground_speed" in data:
            self.drone_state.ground_speed = data["ground_speed"]
            lp.val_spd.setText(f"{data['ground_speed']:.1f} m/s")
            lp.val_spd.setStyleSheet("color: #2196F3; font-weight: bold;")

        if "gps_altitude" in data:
            self.drone_state.gps_altitude = data["gps_altitude"]

        # ── Cập nhật vị trí drone trên bản đồ (real-time, no reload) ──
        if "latitude" in data and "longitude" in data:
            lat = data["latitude"]
            lon = data["longitude"]
            self.drone_state.record_gps_history()
            heading = self.drone_state.yaw
            if lat != 0.0 or lon != 0.0:
                self.map_panel.update_drone_position(lat, lon, heading)
                self._check_distance_safety()

        # ══════════════════════════════════════════════
        # CẬP NHẬT LiDAR DATA (từ MTF-02 qua MSP_SONAR_ALTITUDE)
        # ══════════════════════════════════════════════

        if "surface_altitude" in data:
            s_alt = data["surface_altitude"]
            self.drone_state.surface_altitude = s_alt
            self.drone_state.has_valid_surface = s_alt >= 0

            if s_alt >= 0:
                lp.val_surface_alt.setText(f"{s_alt:.2f} m")
                lp.val_surface_alt.setStyleSheet("color: #00E676; font-weight: bold;")
            else:
                lp.val_surface_alt.setText("Out of Range")
                lp.val_surface_alt.setStyleSheet("color: #808098; font-weight: bold;")

        if "surface_quality" in data:
            s_qual = data["surface_quality"]
            self.drone_state.surface_quality = s_qual
            qual_color = "#00E676" if s_qual > 100 else ("#ffd700" if s_qual > 0 else "#ff4444")
            lp.val_lidar_qual.setText(str(s_qual))
            lp.val_lidar_qual.setStyleSheet(f"color: {qual_color}; font-weight: bold;")

        # ══════════════════════════════════════════════
        # CẬP NHẬT SENSOR STATE (từ MSP_STATUS_EX)
        # ══════════════════════════════════════════════

        if "sensor_opflow" in data:
            self.drone_state.sensor_opflow = data["sensor_opflow"]
            if data["sensor_opflow"]:
                lp.val_opflow.setText("✅ Active")
                lp.val_opflow.setStyleSheet("color: #00E676; font-weight: bold;")
            else:
                lp.val_opflow.setText("⚠️ Inactive")
                lp.val_opflow.setStyleSheet("color: #ffd700; font-weight: bold;")

        if "sensor_rangefinder" in data:
            self.drone_state.sensor_rangefinder = data["sensor_rangefinder"]
        if "sensor_mag" in data:
            self.drone_state.sensor_mag = data["sensor_mag"]
        if "sensor_gps" in data:
            self.drone_state.sensor_gps = data["sensor_gps"]
        if "sensor_baro" in data:
            self.drone_state.sensor_baro = data["sensor_baro"]

        # ══════════════════════════════════════════════
        # CẬP NHẬT RSSI + POWER + DISTANCE (BUG-3/4 FIX)
        # ══════════════════════════════════════════════

        if "rssi" in data:
            rssi = data["rssi"]
            lp.val_rssi.setText(f"{rssi}")
            rssi_color = "#00ff88" if rssi > 50 else ("#ffd700" if rssi > 20 else "#ff4444")
            lp.val_rssi.setStyleSheet(f"color: {rssi_color}; font-weight: bold;")

        # BUG-4 FIX: Tính công suất P = V × I
        if self.drone_state.voltage > 0 and self.drone_state.current > 0:
            power = self.drone_state.voltage * self.drone_state.current
            lp.val_power.setText(f"{power:.1f} W")
            pwr_color = "#00ff88" if power < 100 else ("#ffd700" if power < 300 else "#ff4444")
            lp.val_power.setStyleSheet(f"color: {pwr_color}; font-weight: bold;")

        # BUG-3 FIX: Cập nhật khoảng cách drone → Home trên LeftPanel
        if self.drone_state.has_home and self.drone_state.latitude != 0.0:
            dist = haversine_distance(
                self.drone_state.home_lat, self.drone_state.home_lon,
                self.drone_state.latitude, self.drone_state.longitude
            )
            if dist < 1000:
                lp.val_distance.setText(f"{dist:.0f} m")
            else:
                lp.val_distance.setText(f"{dist/1000:.2f} km")
            dist_color = "#00ff88" if dist < 50 else ("#ffd700" if dist < 200 else "#ff4444")
            lp.val_distance.setStyleSheet(f"color: {dist_color}; font-weight: bold;")
    # ══════════════════════════════════════════════
    # QUẢN LÝ TRẠNG THÁI UI
    # ══════════════════════════════════════════════

    def set_ui_state_na(self):
        """Trạng thái mất mạng: Khóa giao diện và reset telemetry labels."""
        lp = self.left_panel

        labels_to_na = [
            lp.val_armed, lp.val_alt, lp.val_lat, lp.val_lon,
            lp.val_roll, lp.val_pitch, lp.val_yaw,
            lp.val_gps_fix, lp.val_sats, lp.val_gps_accuracy, lp.val_spd,
            lp.val_surface_alt, lp.val_lidar_qual, lp.val_opflow,
            lp.val_current, lp.val_vario, lp.val_rssi, lp.val_distance,
            lp.val_power
        ]
        for lbl in labels_to_na:
            lbl.setText("N/A")
            lbl.setStyleSheet("color: #3a3a4a;")

        # Reset top bar
        self.top_bar.update_battery(0, 0)
        self.top_bar.update_connection(False)
        self.top_bar.update_flight_mode("⏸ IDLE", "#808098")
        self.gamepad_tab.set_connection_status(False, "Disconnected")
        self.gamepad_tab.set_armed(False)
        self.gamepad_tab.update_rc_preview([1500] * 8, 1000, 0, lift_off=False)

        # Reset ping
        self.top_bar.lbl_ping.setText("🏓 ---ms")
        self.top_bar.lbl_ping.setStyleSheet("color: #808098;")
        self._ping_timeout_timer.stop()
        self._gamepad_rc_timer.stop()

        # Disable flight controls
        self.left_toolbar.set_enabled_flight_controls(False)
        self.left_toolbar.set_takeoff_state("IDLE")
        self.map_panel.setEnabled(False)

        # Reset home tracking
        self.drone_state.has_home = False

        # Log
        self.command_log.append_log("SYS", "Đã ngắt kết nối")

    def enable_ui_components(self):
        """Trạng thái có mạng: Mở khóa giao diện."""
        lp = self.left_panel

        self.left_toolbar.set_enabled_flight_controls(True)
        self.map_panel.setEnabled(True)
        lp.val_armed.setStyleSheet("color: #ff4444;")
        lp.val_gps_fix.setStyleSheet("color: #00ff88;")

        self.top_bar.update_connection(True)
        self.gamepad_tab.set_connection_status(True, "Connected")
        self.command_log.append_log("SYS", "Đã kết nối thành công")

    # ══════════════════════════════════════════════
    # VÒNG ĐỜI ỨNG DỤNG
    # ══════════════════════════════════════════════

    def closeEvent(self, event):
        """Đảm bảo ngắt kết nối an toàn khi người dùng đóng cửa sổ."""
        self._ping_timeout_timer.stop()
        self._gamepad_rc_timer.stop()
        if self.flight_controller.is_active:
            self.flight_controller.abort()
        if self.worker:
            self.worker.stop()
            self.worker.wait(2000)  # Chờ thread dọn xong trước khi đóng app
        event.accept()

    def resizeEvent(self, event):
        """Cập nhật vị trí emergency overlay khi resize cửa sổ."""
        super().resizeEvent(event)
        if hasattr(self, 'emergency_overlay') and self.emergency_overlay.isVisible():
            self.emergency_overlay._update_position()

    # ══════════════════════════════════════════════
    # SLOT: FLIGHT CONTROLLER
    # ══════════════════════════════════════════════

    def _confirm_takeoff(self):
        """Hiện dialog nhập độ cao trước khi cất cánh tự động."""
        dialog = TakeoffDialog(self)

        # Cập nhật thông tin GPS hiện tại lên dialog
        dialog.update_gps_info(
            self.drone_state.gps_fix_type,
            self.drone_state.gps_num_sat,
            self.drone_state.latitude,
            self.drone_state.longitude
        )

        if dialog.exec() == QDialog.Accepted:
            target_alt = dialog.target_altitude
            self.flight_controller.takeoff_and_hold(target_alt)

    def _confirm_manual_takeoff(self):
        """Hiện dialog nhập độ cao rồi gọi manual takeoff."""
        dialog = TakeoffDialog(self)
        dialog.setWindowTitle("🛩 Cấu hình Manual Takeoff")
        dialog.update_gps_info(
            self.drone_state.gps_fix_type,
            self.drone_state.gps_num_sat,
            self.drone_state.latitude,
            self.drone_state.longitude
        )
        if dialog.exec() == QDialog.Accepted:
            target_alt = dialog.target_altitude
            self.flight_controller.manual_takeoff_and_hold(target_alt)

    def _on_flight_status(self, message: str):
        """Slot: Cập nhật trạng thái bay lên UI."""
        self.top_bar.update_flight_mode(f"✈ {message}", "#2196F3")
        self.command_log.append_log("GCS", message, "#2196F3")

    def _on_takeoff_complete(self):
        """Slot: Cất cánh thành công — cập nhật UI."""
        self.top_bar.update_flight_mode("✅ HOLDING", "#00ff88")
        self.command_log.append_log("GCS", "Takeoff complete — Holding position", "#00ff88")

    def _on_flight_error(self, message: str):
        """
        Slot: Lỗi bay — cập nhật status KHÔNG hiện QMessageBox.

        Lý do bỏ QMessageBox.critical: Dialog modal sẽ CHẶN TOÀN BỘ
        tương tác UI — kể cả nút Emergency overlay.
        """
        self.top_bar.update_flight_mode(f"⚠️ {message}", "#ff4444")
        self.command_log.append_log("ERR", message)

    def _on_flight_state_changed(self, new_state: str):
        """Slot: State machine chuyển trạng thái — cập nhật LeftToolbar."""
        tb = self.left_toolbar
        if new_state == "IDLE":
            tb.set_takeoff_state("IDLE")
            # Reset NAV takeoff button
            try:
                tb.btn_takeoff.clicked.disconnect()
            except RuntimeError:
                pass
            tb.btn_takeoff.clicked.connect(self._confirm_takeoff)
            # Reset Manual takeoff button
            try:
                tb.btn_manual_takeoff.clicked.disconnect()
            except RuntimeError:
                pass
            tb.btn_manual_takeoff.clicked.connect(self._confirm_manual_takeoff)

        elif new_state in ("NAV_OFF_BEFORE_DISARM", "NAV_OFF_BEFORE_SAFE_LAND"):
            self.top_bar.update_flight_mode(f"⏳ {new_state}", "#ffd700")
            self.command_log.append_log("GCS", f"State: {new_state}", "#ffd700")

        elif new_state in ("MANUAL_ANGLE_IDLE", "MANUAL_THROTTLE_RAMP",
                           "MANUAL_CLIMB_ANGLE", "MANUAL_SWITCH_NAV"):
            self.top_bar.update_flight_mode(f"🛩 {new_state}", "#2196F3")
            self.command_log.append_log("GCS", f"State: {new_state}", "#2196F3")
            tb.set_takeoff_state(new_state)
            # Manual takeoff đang chạy → nút manual thành ABORT
            try:
                tb.btn_manual_takeoff.clicked.disconnect()
            except RuntimeError:
                pass
            tb.btn_manual_takeoff.clicked.connect(self.flight_controller.abort)
        else:
            tb.set_takeoff_state(new_state)
            # NAV takeoff đang chạy → nút NAV thành ABORT
            try:
                tb.btn_takeoff.clicked.disconnect()
            except RuntimeError:
                pass
            tb.btn_takeoff.clicked.connect(self.flight_controller.abort)

    def _on_mode_activated(self, mode_name: str):
        """
        Slot: Mode bay được kích hoạt — hiện/ẩn emergency overlay.

        Khi mode_name rỗng "" → ẩn overlay.
        Khi mode_name có nội dung → hiện overlay với tên mode.
        """
        if mode_name:
            self.emergency_overlay.show_with_mode(mode_name)
            self.drone_state.active_mode_name = mode_name
            self.gamepad_tab.set_fc_state(mode_name)
            if self.gamepad_tab.is_gamepad_enabled():
                self.gamepad_tab.set_blocked_reason(f"Autopilot active: {mode_name}")
        else:
            self.emergency_overlay.hide_overlay()
            self.drone_state.active_mode_name = ""
            self.gamepad_tab.set_fc_state("IDLE" if not self.drone_state.is_armed else "ARMED")
            self.gamepad_tab.set_blocked_reason("")

    def _on_ping_updated(self, rtt_ms: int):
        """Slot: Nhận RTT mới từ WifiWorker."""
        self.drone_state.ping_rtt_ms = rtt_ms
        self.top_bar.update_ping(rtt_ms)
        self._ping_timeout_timer.start()

    def _on_ping_timeout(self):
        """Slot: Quá 3 giây không nhận PONG mới."""
        self.top_bar.lbl_ping.setText("🏓 Timeout")
        self.top_bar.lbl_ping.setStyleSheet("color: #ff4444; font-weight: bold;")

    def _on_command_acked(self, ack_type: str):
        """Slot: ESP32 đã xác nhận nhận lệnh."""
        type_labels = {
            "RC": "✓ RC",
            "FS": "✓ Failsafe config",
            "EM": "✓ Emergency cmd",
        }
        label = type_labels.get(ack_type, f"✓ ACK:{ack_type}")
        if ack_type == "RC":
            self.gamepad_tab.mark_rc_ack()
        if ack_type != "RC":
            self.command_log.append_log("ACK", label, "#00E676")

    # ══════════════════════════════════════════════
    # EMERGENCY OVERLAY — NÚT KHẨN CẤP
    # ══════════════════════════════════════════════

    def _emergency_force_disarm(self):
        """Nút DISARM khẩn cấp từ overlay — FORCE tắt motor, bypass state machine."""
        self.flight_controller.force_disarm()
        self.emergency_overlay.hide_overlay()

    def _emergency_force_safe_land(self):
        """Nút Safe Land khẩn cấp từ overlay — FORCE hạ cánh, bypass state machine."""
        self.flight_controller.force_safe_land()

    def _on_toolbar_arm_clicked(self):
        """Toggle ARM/DISARM khi nhấn nút ARM trên LeftToolbar.

        BUG-2 FIX: Trước đây btn_arm chỉ connect cứng vào fc.arm(),
        dẫn đến không thể DISARM khi drone đã ARM. Giờ dùng toggle
        dựa trên drone_state.is_armed.

        Dùng disarm() (soft) thay vì force_disarm() vì đây là thao tác
        bình thường, không phải emergency. disarm() tắt NAV mode 300ms
        trước rồi mới gửi DISARM — an toàn cho INAV.
        """
        if self.drone_state.is_armed:
            self.flight_controller.disarm()
            self.command_log.append_log("GCS", "Toolbar DISARM requested", "#FF9800")
        else:
            self.flight_controller.arm()
            self.command_log.append_log("GCS", "Toolbar ARM requested", "#4CAF50")

    # ══════════════════════════════════════════════
    # GAMEPAD TAB
    # ══════════════════════════════════════════════

    def _on_gamepad_enabled_changed(self, enabled: bool):
        if enabled:
            if not self.worker or not self.drone_state.is_connected:
                self.gamepad_tab.set_blocked_reason("Disconnected")
                self.gamepad_tab._set_gamepad_enabled(False, emit=False)
                self.command_log.append_log("SYS", "Gamepad blocked: no connection", "#FFD54F")
                QMessageBox.warning(self, "Gamepad", "Không thể bật gamepad: chưa kết nối ESP32.")
                return
            if self.flight_controller.is_active:
                self.gamepad_tab.set_blocked_reason(f"Autopilot active: {self.flight_controller.state}")
                self.gamepad_tab._set_gamepad_enabled(False, emit=False)
                self.command_log.append_log("SYS", "Gamepad blocked: autopilot active", "#FFD54F")
                QMessageBox.warning(self, "Gamepad", "Không thể bật gamepad: Autopilot đang chạy.")
                return
            self._gamepad_ctrl.reset_throttle()
            self._gamepad_ctrl.enabled = True
            self._gamepad_rc_timer.start()
            self.gamepad_tab.set_blocked_reason("")
            self.command_log.append_log("SYS", "Gamepad control enabled", "#4FC3F7")
        else:
            self._gamepad_rc_timer.stop()
            self._gamepad_ctrl.enabled = False
            if self.worker and not self.flight_controller.is_active:
                safe_channels = self.flight_controller._safe_channels()
                self.flight_controller.send_manual_rc(safe_channels)
            self.gamepad_tab.set_blocked_reason("")
            self.command_log.append_log("SYS", "Gamepad control disabled", "#4FC3F7")

    def _on_gamepad_flight_mode_changed(self, mode: str):
        self.command_log.append_log("GCS", f"Gamepad mode: {mode}", "#4FC3F7")

    def _on_gamepad_speed_mode_changed(self, speed: int):
        self.command_log.append_log("GCS", f"Gamepad speed: {speed}%", "#FFD54F")

    def _on_gamepad_emergency_stop(self):
        self.flight_controller.force_disarm()
        self.gamepad_tab._set_gamepad_enabled(False, emit=False)
        self._gamepad_rc_timer.stop()
        self.command_log.append_log("ERR", "Gamepad emergency stop", "#F44336")

    def _tick_gamepad_rc(self):
        """Gamepad tick timer — guarded against autonomous modes.

        Phase 3 refactor: computation delegated to GamepadController.
        GCSApp chỉ giữ guard checks + UI feedback.
        """
        if not self.worker or not self.gamepad_tab.is_gamepad_enabled():
            return

        # BUG-3 FIX: Guard — nếu FC đang active (Takeoff/RTH/DISARM...) → KHÔNG gửi RC
        if self.flight_controller.is_active:
            self.gamepad_tab.set_blocked_reason(f"Autopilot active: {self.flight_controller.state}")
            return

        self.gamepad_tab.set_blocked_reason("")
        state = self.gamepad_tab.get_control_state()

        # ── Delegate computation → GamepadController ──
        channels, cur_thr, motor_pct, lift_off = self._gamepad_ctrl.compute_channels(
            state, self.flight_controller,
            surface_altitude=self.drone_state.surface_altitude,
        )

        # ── Auto-DISARM: drone nằm đất + ga min > 2s → tự DISARM ──
        if self._gamepad_ctrl.auto_disarmed:
            # CRITICAL: Gửi frame DISARM TRƯỚC khi tắt gamepad!
            # Không gửi → channels với AUX1=DISARM bị mất, drone vẫn ARM.
            self.flight_controller.send_manual_rc(channels)
            self.command_log.append_log(
                "SYS", "Auto-DISARM: drone on ground + zero throttle > 2s", "#FFD54F"
            )
            self.gamepad_tab._set_gamepad_enabled(False, emit=False)
            self._gamepad_rc_timer.stop()
            self._gamepad_ctrl.reset_throttle()
            return

        self.flight_controller.send_manual_rc(channels)

        # ── UI feedback ──
        target_throttle = int(1000 + (_clamp(state["left_throttle"], 0.0, 1.0) * 1000))
        self.gamepad_tab.update_rc_preview(
            channels,
            cur_thr,
            motor_pct,
            lift_off=lift_off,
            commanded_throttle=target_throttle,
        )

    # ══════════════════════════════════════════════
    # MANUAL RC CONTROL
    # ══════════════════════════════════════════════

    def _send_manual_rc(self):
        """★ TASK-18: Đọc giá trị từ 8 slider và gửi MSP_SET_RAW_RC.

        Thứ tự kênh AETR: [Roll, Pitch, Throttle, Yaw, AUX1, AUX2, AUX3, AUX4]
        Các giá trị PWM đã được clamp 1000-2000 bởi slider limits + pack_set_raw_rc().

        NOTE: Legacy method — hiện không được gọi từ đâu.
        Dùng flight_controller.send_manual_rc() thay vì tạo MSPParser riêng.
        """
        if not self.worker or not hasattr(self, "manual_control_tab"):
            return

        mc = self.manual_control_tab
        channels = [
            mc.slider_roll.value(),       # CH1: Roll
            mc.slider_pitch.value(),      # CH2: Pitch
            mc.slider_throttle.value(),   # CH3: Throttle
            mc.slider_yaw.value(),        # CH4: Yaw
            mc.slider_aux1.value(),       # CH5: AUX1 (ARM)
            mc.slider_aux2.value(),       # CH6: AUX2 (Flight Mode)
            mc.slider_aux3.value(),       # CH7: AUX3 (Safe Land)
            mc.slider_aux4.value(),       # CH8: AUX4 (RTH)
        ]
        # BUG-E FIX: Dùng shared FlightController thay vì tạo MSPParser mới mỗi lần
        self.flight_controller.send_manual_rc(channels)

    def _hold_position(self):
        """★ TASK-19: Kích hoạt ALTHOLD+POSHOLD — giữ vị trí và độ cao hiện tại.

        AUX2=2000 (CH6) bật đồng thời NAV ALTHOLD + NAV POSHOLD trên INAV.
        FC sử dụng Baro + GPS BZ 251 để tự giữ vị trí.

        NOTE: Legacy method — hiện không được gọi từ đâu.
        BUG-F FIX: Dùng send_manual_rc() thay vì truy cập private _channels/_send_rc().
        """
        if not self.worker:
            return

        fc = self.flight_controller
        # BUG-F FIX: Tạo bộ channel qua public API thay vì truy cập private fields
        channels = fc._safe_channels()
        channels[fc.CH_AUX1] = fc.AUX_ARM                    # Giữ ARM
        channels[fc.CH_AUX2] = fc.AUX_NAV_ALTHOLD_POSHOLD    # Bật ALTHOLD+POSHOLD
        channels[fc.CH_THROTTLE] = fc.RC_CENTER               # FC tự điều khiển
        fc.send_manual_rc(channels)
        fc.status_update.emit("HOLD — Giữ vị trí + độ cao (ALTHOLD+POSHOLD)")

    # ══════════════════════════════════════════════
    # MISSION LOGIC
    # ══════════════════════════════════════════════

    def _upload_mission(self):
        """Upload waypoints từ MissionTab xuống FC qua MSP_SET_WP."""
        waypoints = self.map_panel.get_waypoints()
        if not waypoints:
            QMessageBox.warning(self, "Cảnh báo", "Chưa có waypoint nào để upload!")
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận Upload",
            f"Sẽ upload {len(waypoints)} waypoint xuống FC.\n\n"
            "Bạn có chắc chắn?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.flight_controller.upload_mission(waypoints)

    def _start_mission(self):
        """
        Bắt đầu bay mission — Hiện dialog xác nhận với cảnh báo an toàn.

        Logic:
        1. Kiểm tra có waypoint không
        2. Hỏi cấu hình failsafe (RTH hoặc Ignore)
        3. Gửi cấu hình failsafe xuống ESP32
        4. Thông báo kết quả
        """
        waypoints = self.map_panel.get_waypoints()
        if not waypoints:
            QMessageBox.warning(self, "Cảnh báo", "Chưa có waypoint nào! Hãy click trên bản đồ để thêm.")
            return

        # Dialog hỏi bắt đầu bay hay hủy
        msg = QMessageBox(self)
        msg.setWindowTitle("🗺️ Bắt đầu Mission")
        msg.setText(
            f"Drone sẽ bay theo {len(waypoints)} waypoint đã thiết lập.\n\n"
            "Khi drone bay xa, bạn có muốn kích hoạt cơ chế\n"
            "Failsafe (RTH) khi mất kết nối WiFi không?"
        )
        msg.setIcon(QMessageBox.Question)

        btn_yes = msg.addButton("✅ Yes — RTH khi mất WiFi", QMessageBox.YesRole)
        btn_ignore = msg.addButton("⚠️ Ignore — Bay hết rồi Safe Land", QMessageBox.NoRole)
        btn_cancel = msg.addButton("❌ Hủy", QMessageBox.RejectRole)

        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_cancel:
            return

        if clicked == btn_yes:
            # Cấu hình ESP32: Mất WiFi → RTH
            self.flight_controller.send_failsafe_config("rth")
            self.map_panel.val_failsafe_status.setText("RTH khi mất WiFi")
            self.map_panel.val_failsafe_status.setStyleSheet("color: #00ff88; font-weight: bold;")
        elif clicked == btn_ignore:
            # Cấu hình ESP32: Mất WiFi → Không can thiệp, drone bay hết WP rồi Safe Land
            self.flight_controller.send_failsafe_config("ignore")
            self.map_panel.val_failsafe_status.setText("Ignore — Safe Land cuối")
            self.map_panel.val_failsafe_status.setStyleSheet("color: #ffd700; font-weight: bold;")

        # Upload waypoints rồi thông báo sẵn sàng
        self.flight_controller.upload_mission(waypoints)
        self.emergency_overlay.show_with_mode("Mission")

        QMessageBox.information(
            self,
            "Mission Ready",
            "✅ Waypoints đã được upload lên FC.\n\n"
            "Để bắt đầu bay, hãy ARM drone rồi bật mode NAV WP\n"
            "trên remote hoặc qua INAV Configurator."
        )

    def _stop_mission(self):
        """Dừng mission — gửi lệnh Safe Land."""
        reply = QMessageBox.question(
            self,
            "Dừng Mission",
            "Bạn muốn dừng mission và hạ cánh tại chỗ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.flight_controller.safe_land()

    def _check_distance_safety(self):
        """
        Kiểm tra khoảng cách drone → Home.
        Nếu vượt ngưỡng → hiện dialog cảnh báo failsafe.
        """
        if self._distance_warning_shown:
            return  # Đã cảnh báo rồi, không hỏi lại

        if not self.drone_state.has_home:
            return

        if self.map_panel.check_distance_warning():
            self._distance_warning_shown = True

            reply = QMessageBox.question(
                self,
                "⚠️ Cảnh báo Khoảng cách",
                f"Drone đã bay xa hơn {self.map_panel._distance_threshold}m "
                "so với vị trí Home!\n\n"
                "Bạn có muốn kích hoạt cơ chế Failsafe\n"
                "(RTH tự động) khi mất kết nối WiFi không?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self.flight_controller.send_failsafe_config("rth")
                self.map_panel.val_failsafe_status.setText("RTH — Auto Failsafe")
                self.map_panel.val_failsafe_status.setStyleSheet("color: #ff4444; font-weight: bold;")




# ══════════════════════════════════════════════════
# KHỞI CHẠY ỨNG DỤNG
# ══════════════════════════════════════════════════

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 1. Khởi chạy màn hình chính
    window = GCSApp()
    window.show()

    # 2. Tự động bật hộp thoại kết nối để tiện lợi
    dialog = ConnectionDialog(window)
    if dialog.exec() == QDialog.Accepted:
        window.start_connection(dialog.selected_ip, dialog.selected_port, dialog.is_mock_selected)

    sys.exit(app.exec())