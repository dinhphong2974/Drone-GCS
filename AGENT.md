# DroneGCS — Agent Context

> Đọc file này + `memories.md` + `.ai_rules.md` MỖI KHI bắt đầu chat.

## Hệ Thống

```
[PC/PySide6 GCS] ──TCP/WiFi──→ [ESP32 AP 192.168.4.1:8080] ──UART 115200──→ [SpeedyBee F405 INAV 9.0.1]
```

**Phần cứng**: OddityRC XI35 Pro 3.5" | 6S 1960kv | GPS BZ 251 (UART5) | LiDAR+OptFlow MTF-02 (UART6/MSP)

## Kiến Trúc (SoC)

| Module | Vai trò |
|---|---|
| `main.py` (GCSApp) | Entry point, Signal/Slot hub, cập nhật UI |
| `comm/wifi_worker.py` | QThread 20Hz, poll telemetry, drain command/emergency queue |
| `comm/msp_parser.py` | MSP v1 pack/parse ($M< / $M>) |
| `core/flight_controller.py` | State machine 10Hz (QTimer), gửi RC qua worker |
| `core/drone_state.py` | Shared state (Main Thread only) |
| `ui/` | Layout ONLY — không logic nghiệp vụ |
| `ESP32/main.py` | MicroPython bridge, failsafe watchdog, prefix routing |

## Luồng Tín Hiệu

- **Telemetry**: FC→UART→ESP32→TCP→WifiWorker→MSPParser→Signal→GCSApp→drone_state+UI
- **Command**: FlightController→MSPParser.pack→command_queue→WifiWorker→TCP→ESP32→UART→FC
- **Emergency**: `EM:` prefix → emergency_queue (priority) → ESP32 flush UART → FC ngay lập tức

## AUX Mapping (AETR order, index 0-7)

| Index | Kênh | Chức năng | Values |
|---|---|---|---|
| 4 | AUX1/CH5 | ARM | 1000=DISARM, 2000=ARM |
| 5 | AUX2/CH6 | Flight Mode | 1000=Acro, 1500=ANGLE, 2000=ALTHOLD+POSHOLD+WP |
| 6 | AUX3/CH7 | Safe Land | 1000=OFF, 2000=ON |
| 7 | AUX4/CH8 | RTH | 1000=OFF, 2000=ON |

## State Machine Tóm Tắt

- **NAV Takeoff**: IDLE→PRE_ARM→WAIT_RC_LINK(2s)→ARMING→ARMED_WAIT→WP_UPLOAD→WP_ACTIVATE(rising edge)→NAV_CLIMB→ALTITUDE_REACHED(1s settle)→HOLDING
- **Manual Takeoff**: ...→ARMED_WAIT→MANUAL_ANGLE_IDLE(1s)→MANUAL_THROTTLE_RAMP(+50μs/tick)→MANUAL_CLIMB_ANGLE(→2m)→MANUAL_SWITCH_NAV(1.5s)→NAV_CLIMB→...
- **DISARM**: NAV_OFF(300ms)→DISARMING(10Hz repeated)
- **Force DISARM**: STOP→EM:NAV_OFF→EM:DISARM×2→FORCE_DISARMING(emergency queue)

## Hằng Số Quan Trọng

| Key | Value | Note |
|---|---|---|
| TICK_INTERVAL_MS | 100 | 10Hz state machine |
| RC_LINK_WAIT_S | 2.0 | INAV ARM_SWITCH safety |
| NAV_OFF_DELAY_S | 0.3 | Tắt NAV trước DISARM |
| LIDAR_TRUST_RANGE_M | 2.2 | MTF-02 trust ≤2.2m (accuracy 2%) |
| MANUAL_HOVER_THROTTLE | 1400 | 3.5" 6S hover estimate |
| MANUAL_RAMP_STEP | 50 | μs/tick ramp speed |

## Quy Tắc (xem chi tiết `.ai_rules.md`)

1. Đọc `config/INAV_QUIRKS.md` — BoxID SpeedyBee khác chuẩn
2. Thay đổi code ↔ báo lệnh CLI INAV cần sửa
3. Phân tích → Đề xuất → Plan → CHỜ duyệt → Code
4. Thread Safety: FC=Main Thread(QTimer), Worker=QThread, giao tiếp Queue/Signal
5. Mọi tham chiếu vật lý = hệ 3.5-inch
6. Ưu tiên Grapuco MCP tools