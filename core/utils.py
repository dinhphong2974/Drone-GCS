"""
utils.py - Tiện ích dùng chung cho DroneGCS.

Chứa các hàm nhỏ được dùng bởi nhiều module (core, ui, main).
Tránh duplicate code và đảm bảo logic nhất quán.
"""


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Giới hạn giá trị trong khoảng [minimum, maximum].

    Sử dụng chính trong:
    - MSPParser: clamp PWM 1000-2000μs trước khi đóng gói
    - FlightController: clamp channels trước khi gửi RC
    - GamepadTab: clamp stick input → RC value

    Args:
        value: Giá trị cần giới hạn
        minimum: Giá trị tối thiểu
        maximum: Giá trị tối đa

    Returns:
        float: Giá trị đã được giới hạn
    """
    return max(minimum, min(maximum, value))


def clamp_pwm(value: int) -> int:
    """Giới hạn giá trị PWM trong dải an toàn 1000-2000μs.

    INAV/ESC chỉ chấp nhận giá trị 1000-2000μs:
    - < 1000: Motor không phản hồi, FC có thể báo lỗi
    - > 2000: Motor quá tải, ESC có thể bảo vệ bằng cách ngắt

    Hardware: OddityRC XI35 Pro 3.5-inch, Motor 1960kv, 6S Lipo

    Args:
        value: Giá trị PWM thô

    Returns:
        int: Giá trị đã clamp trong [1000, 2000]
    """
    return max(1000, min(2000, int(value)))
