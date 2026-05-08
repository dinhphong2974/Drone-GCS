"""
test_gamepad_controller.py - Unit tests cho GamepadController.

Kiểm tra:
- Deadzone filtering
- Throttle ramp up/down
- Channel mapping (stick → đúng index)
- Speed mode scaling
- Reset/enable/disable
"""

import pytest
from core.drone_state import DroneState
from core.flight_controller import FlightController
from core.gamepad_controller import GamepadController


@pytest.fixture
def gc():
    """GamepadController mới, throttle = 1000."""
    return GamepadController()


@pytest.fixture
def fc():
    """FlightController mock (không cần worker)."""
    ds = DroneState()
    return FlightController(ds)


def _make_state(**overrides):
    """Tạo control_state mặc định (tất cả sticks ở center/zero)."""
    base = {
        "left_x": 0.0,
        "left_throttle": 0.0,
        "right_x": 0.0,
        "right_y": 0.0,
        "speed_mode": 60,
        "is_arming_requested": False,
        "flight_mode": "ANGLE",
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════
# DEADZONE
# ══════════════════════════════════════════════

def test_deadzone_filters_small_values(gc, fc):
    """Stick nhỏ hơn 4% coi như 0 → channel = center 1500."""
    state = _make_state(right_x=0.03, right_y=-0.02, left_x=0.01)
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert channels[fc.CH_ROLL] == 1500
    assert channels[fc.CH_PITCH] == 1500
    assert channels[fc.CH_YAW] == 1500


def test_deadzone_passes_large_values(gc, fc):
    """Stick lớn hơn 4% phải tạo offset từ center."""
    state = _make_state(right_x=0.5, right_y=-0.5, left_x=0.3)
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert channels[fc.CH_ROLL] != 1500
    assert channels[fc.CH_PITCH] != 1500
    assert channels[fc.CH_YAW] != 1500


# ══════════════════════════════════════════════
# THROTTLE RAMP
# ══════════════════════════════════════════════

def test_throttle_ramps_up(gc, fc):
    """Throttle tăng dần, không nhảy thẳng lên target."""
    state = _make_state(left_throttle=1.0, speed_mode=60)
    channels, cur, _, _ = gc.compute_channels(state, fc)
    # Sau 1 tick: throttle tăng 16 (step cho speed 60)
    assert cur == 1016
    assert cur < 2000  # Chưa đạt max


def test_throttle_ramps_up_multiple_ticks(gc, fc):
    """Sau nhiều tick, throttle tiếp tục tăng dần."""
    state = _make_state(left_throttle=1.0, speed_mode=60)
    for _ in range(10):
        channels, cur, _, _ = gc.compute_channels(state, fc)
    assert cur == 1000 + (16 * 10)  # 1160


def test_throttle_ramps_down(gc, fc):
    """Throttle giảm dần khi user thả slider."""
    # Đẩy lên trước
    up = _make_state(left_throttle=0.5, speed_mode=60)
    for _ in range(50):
        gc.compute_channels(up, fc)
    high = gc.current_throttle

    # Thả về 0
    down = _make_state(left_throttle=0.0, speed_mode=60)
    gc.compute_channels(down, fc)
    assert gc.current_throttle < high  # Đang giảm
    assert gc.current_throttle > 1000  # Chưa về hết


def test_throttle_does_not_overshoot(gc, fc):
    """Throttle không bao giờ vượt target."""
    state = _make_state(left_throttle=0.1, speed_mode=100)
    target = int(1000 + 0.1 * 1000)  # 1100
    for _ in range(200):
        gc.compute_channels(state, fc)
    assert gc.current_throttle == target


# ══════════════════════════════════════════════
# SPEED MODE SCALING
# ══════════════════════════════════════════════

def test_speed_30_small_axis(gc, fc):
    """Speed 30% → axis scale 220 → nhỏ hơn 60%."""
    state = _make_state(right_x=1.0, speed_mode=30)
    ch30, _, _, _ = gc.compute_channels(state, fc)

    gc2 = GamepadController()
    state60 = _make_state(right_x=1.0, speed_mode=60)
    ch60, _, _, _ = gc2.compute_channels(state60, fc)

    assert ch30[fc.CH_ROLL] < ch60[fc.CH_ROLL]


def test_speed_100_larger_axis(gc, fc):
    """Speed 100% → axis scale 480 → lớn hơn 60%."""
    state = _make_state(right_x=1.0, speed_mode=100)
    ch100, _, _, _ = gc.compute_channels(state, fc)
    # Roll max ở 100%: 1500 + 480 = 1980
    assert ch100[fc.CH_ROLL] == 1980


# ══════════════════════════════════════════════
# CHANNEL MAPPING
# ══════════════════════════════════════════════

def test_arm_channel(gc, fc):
    """ARM request → AUX1 = 2000."""
    state = _make_state(is_arming_requested=True)
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert channels[fc.CH_AUX1] == fc.AUX_ARM  # 2000


def test_disarm_channel(gc, fc):
    """No ARM request → AUX1 = 1000."""
    state = _make_state(is_arming_requested=False)
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert channels[fc.CH_AUX1] == fc.AUX_DISARM  # 1000


def test_direct_mode(gc, fc):
    """DIRECT mode → AUX2 = NAV_ALTHOLD_POSHOLD (2000)."""
    state = _make_state(flight_mode="DIRECT")
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert channels[fc.CH_AUX2] == fc.AUX_NAV_ALTHOLD_POSHOLD


def test_angle_mode(gc, fc):
    """ANGLE mode → AUX2 = ANGLE (1500)."""
    state = _make_state(flight_mode="ANGLE")
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert channels[fc.CH_AUX2] == fc.AUX_ANGLE


def test_safe_land_rth_always_off(gc, fc):
    """AUX3 (Safe Land) và AUX4 (RTH) luôn OFF trong gamepad mode."""
    state = _make_state()
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert channels[fc.CH_AUX3] == fc.AUX_SAFE_LAND_OFF
    assert channels[fc.CH_AUX4] == fc.AUX_RTH_OFF


# ══════════════════════════════════════════════
# LIFT-OFF & MOTOR PCT
# ══════════════════════════════════════════════

def test_lift_off_false_at_idle(gc, fc):
    """Throttle 1000 → lift_off = False."""
    state = _make_state(left_throttle=0.0)
    _, _, _, lift_off = gc.compute_channels(state, fc)
    assert lift_off is False


def test_lift_off_true_at_hover(gc, fc):
    """Throttle >= 1450 → lift_off = True."""
    state = _make_state(left_throttle=1.0, speed_mode=100)
    for _ in range(50):
        gc.compute_channels(state, fc)
    _, cur, _, lift_off = gc.compute_channels(state, fc)
    assert cur >= 1450
    assert lift_off is True


def test_motor_pct_range(gc, fc):
    """Motor percentage luôn trong 0-100."""
    state = _make_state(left_throttle=1.0, speed_mode=100)
    for _ in range(200):
        _, _, motor_pct, _ = gc.compute_channels(state, fc)
        assert 0 <= motor_pct <= 100


# ══════════════════════════════════════════════
# RESET & ENABLE/DISABLE
# ══════════════════════════════════════════════

def test_reset_throttle(gc, fc):
    """reset_throttle() đưa throttle về 1000."""
    state = _make_state(left_throttle=1.0, speed_mode=100)
    for _ in range(10):
        gc.compute_channels(state, fc)
    assert gc.current_throttle > 1000
    gc.reset_throttle()
    assert gc.current_throttle == 1000


def test_disable_resets_throttle(gc, fc):
    """enabled = False tự reset throttle."""
    state = _make_state(left_throttle=1.0, speed_mode=100)
    for _ in range(10):
        gc.compute_channels(state, fc)
    gc.enabled = False
    assert gc.current_throttle == 1000
    assert gc.enabled is False


def test_channels_always_8_elements(gc, fc):
    """compute_channels luôn trả về đúng 8 kênh."""
    state = _make_state()
    channels, _, _, _ = gc.compute_channels(state, fc)
    assert len(channels) == 8


def test_all_channels_in_valid_range(gc, fc):
    """Tất cả channels trong 1000-2000 ở mọi speed mode."""
    for speed in [30, 60, 100]:
        gc2 = GamepadController()
        state = _make_state(
            left_x=1.0, left_throttle=1.0,
            right_x=-1.0, right_y=1.0,
            speed_mode=speed, is_arming_requested=True,
            flight_mode="DIRECT",
        )
        for _ in range(100):
            channels, _, _, _ = gc2.compute_channels(state, fc)
        for i, ch in enumerate(channels):
            assert 1000 <= ch <= 2000, f"Channel[{i}]={ch} out of range at speed={speed}"
