"""

gamepad_controller.py - Logic điều khiển gamepad tách biệt khỏi UI.

Module này chứa toàn bộ computation logic cho virtual gamepad:
- Deadzone filtering cho joystick
- Speed mode scaling (30/60/100%)
- Throttle ramping (tăng/giảm ga mượt)
- Channel mapping (stick → RC channels AETR)

Thiết kế pure Python (không Qt) để dễ unit test.
GCSApp (main.py) làm cầu nối giữa GamepadTab (UI) và module này.

Hardware reference: OddityRC XI35 Pro 3.5-inch, 6S 1960kv
"""

import time

from core.utils import clamp as _clamp


class GamepadController:
    """
    Xử lý logic gamepad: deadzone, speed scaling, ramp, channel mapping.

    Không chứa QTimer, Signal, hay bất kỳ Qt dependency nào.
    GCSApp gọi compute_channels() mỗi tick (50ms) và gửi kết quả xuống FC.
    """

    # ── Hằng số ──
    DEADZONE = 0.04  # Stick nhỏ hơn 4% coi như 0 (tránh drift)

    # Bước tăng throttle theo speed mode (μs/tick tại 20Hz)
    THROTTLE_STEPS = {30: 8, 60: 16, 100: 26}

    # Biên độ trục điều khiển theo speed mode (μs offset từ center 1500)
    AXIS_SCALES = {30: 220, 60: 350, 100: 480}

    # ── Ground Idle Detection — Auto-DISARM khi nằm đất ──
    GROUND_IDLE_TIMEOUT_S = 2.0     # Ga min + chạm đất liên tục > 2s → auto DISARM
    GROUND_PROXIMITY_M = 0.15       # LiDAR < 15cm = chạm đất (khớp FC.LIDAR_GROUND_PROXIMITY)

    def __init__(self):
        """Khởi tạo với throttle ở mức tối thiểu."""
        self._current_throttle: int = 1000
        self._enabled: bool = False

        # Ground idle detection state
        self._ground_idle_start: float = 0.0
        self._ground_idle_active: bool = False
        self._auto_disarmed: bool = False

    @property
    def enabled(self) -> bool:
        """Trạng thái bật/tắt gamepad."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if not value:
            self._current_throttle = 1000
            self._ground_idle_active = False
            self._ground_idle_start = 0.0
            self._auto_disarmed = False

    @property
    def current_throttle(self) -> int:
        """Throttle hiện tại sau ramp (1000-2000μs)."""
        return self._current_throttle

    @property
    def auto_disarmed(self) -> bool:
        """True khi auto-DISARM đã được trigger do drone nằm đất quá lâu."""
        return self._auto_disarmed

    def reset_throttle(self):
        """Reset throttle về mức tối thiểu (motor idle) và xóa ground idle state."""
        self._current_throttle = 1000
        self._ground_idle_active = False
        self._ground_idle_start = 0.0
        self._auto_disarmed = False

    def compute_channels(self, control_state: dict, fc,
                         surface_altitude: float = -1.0) -> tuple:
        """
        Tính toán 8 kênh RC từ trạng thái joystick.

        Args:
            control_state: Dict từ GamepadTab.get_control_state() gồm:
                - left_x (float): Yaw axis [-1, 1]
                - left_throttle (float): Throttle [0, 1]
                - right_x (float): Roll axis [-1, 1]
                - right_y (float): Pitch axis [-1, 1]
                - speed_mode (int): 30, 60, hoặc 100
                - is_arming_requested (bool): ARM toggle
                - flight_mode (str): "ANGLE" hoặc "DIRECT"
            fc: FlightController reference — dùng để lấy constants
                (CH_*, AUX_*, _safe_channels)
            surface_altitude: Khoảng cách LiDAR tới mặt đất (m).
                -1.0 = không có data (default, backward compatible).
                Dùng cho ground idle detection auto-DISARM.

        Returns:
            tuple: (channels, current_throttle, motor_pct, lift_off)
                - channels (list[int]): 8 kênh RC [1000-2000]
                - current_throttle (int): Throttle sau ramp
                - motor_pct (int): % motor output [0-100]
                - lift_off (bool): True nếu throttle >= 1450 (ước lượng nhấc)
        """
        speed = control_state["speed_mode"]
        throttle_step = self.THROTTLE_STEPS.get(speed, 16)
        axis_scale = self.AXIS_SCALES.get(speed, 350)

        # ── Deadzone filtering ──
        left_x = control_state["left_x"] if abs(control_state["left_x"]) >= self.DEADZONE else 0.0
        left_throttle = _clamp(control_state["left_throttle"], 0.0, 1.0)
        right_x = control_state["right_x"] if abs(control_state["right_x"]) >= self.DEADZONE else 0.0
        right_y = control_state["right_y"] if abs(control_state["right_y"]) >= self.DEADZONE else 0.0

        # ── Target throttle từ slider (0-1 → 1000-2000μs) ──
        target_throttle = int(1000 + (left_throttle * 1000))

        # ── Ramp throttle mượt theo speed mode ──
        if self._current_throttle < target_throttle:
            self._current_throttle = min(
                self._current_throttle + throttle_step, target_throttle
            )
        elif self._current_throttle > target_throttle:
            self._current_throttle = max(
                self._current_throttle - throttle_step, target_throttle
            )

        # ── Build channels từ safe baseline ──
        channels = fc._safe_channels()

        # ARM/DISARM
        is_arming = control_state.get("is_arming_requested")
        channels[fc.CH_AUX1] = (
            fc.AUX_ARM if is_arming else fc.AUX_DISARM
        )

        # Flight mode
        # SAFETY FIX: Khi DISARM → PHẢI force ANGLE mode (tắt NAV modes)
        # INAV firmware REJECT DISARM khi NAV mode active (ARMING_DISABLED_NAVIGATION)
        # Chỉ cho phép bật NAV (DIRECT mode) khi đang ARM
        if is_arming and control_state.get("flight_mode") == "DIRECT":
            channels[fc.CH_AUX2] = fc.AUX_NAV_ALTHOLD_POSHOLD
        else:
            channels[fc.CH_AUX2] = fc.AUX_ANGLE

        # Safety: Safe Land OFF + RTH OFF
        channels[fc.CH_AUX3] = fc.AUX_SAFE_LAND_OFF
        channels[fc.CH_AUX4] = fc.AUX_RTH_OFF

        # Stick → channel mapping
        channels[fc.CH_ROLL] = int(1500 + (right_x * axis_scale))
        channels[fc.CH_PITCH] = int(1500 - (right_y * axis_scale))
        channels[fc.CH_YAW] = int(1500 + (left_x * axis_scale))
        channels[fc.CH_THROTTLE] = self._current_throttle

        # ── Ground Idle Detection — Auto-DISARM khi nằm đất + ga min > 2s ──
        if (is_arming
                and self._current_throttle <= 1000
                and 0 <= surface_altitude < self.GROUND_PROXIMITY_M):
            # Drone đang ARM + ga min + trên mặt đất
            if not self._ground_idle_active:
                self._ground_idle_start = time.time()
                self._ground_idle_active = True
            elif time.time() - self._ground_idle_start >= self.GROUND_IDLE_TIMEOUT_S:
                # Timeout → tự DISARM để chống bouncing loop
                channels[fc.CH_AUX1] = fc.AUX_DISARM
                # SAFETY FIX: Force ANGLE khi auto-DISARM (cùng root cause BUG #1)
                channels[fc.CH_AUX2] = fc.AUX_ANGLE
                self._auto_disarmed = True
                self._ground_idle_active = False
        else:
            # Điều kiện không thỏa → reset timer
            self._ground_idle_active = False

        # ── Metrics cho UI feedback ──
        motor_pct = max(0, min(100, int((self._current_throttle - 1000) / 10)))
        lift_off = self._current_throttle >= 1450

        return channels, self._current_throttle, motor_pct, lift_off
