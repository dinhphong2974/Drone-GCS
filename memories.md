# DroneGCS — Session Memory

> Đọc file này khi bắt đầu chat mới để nắm ngữ cảnh nhanh.

## Trạng Thái Hiện Tại (2026-05-03)

- **Kiến trúc**: Single-screen Mission Control (Phase 4), PySide6
- **Tests**: 128 passed, 3 xfailed (test_flight_logic + test_msp_noise_robustness)
- **FC**: INAV 9.0.1 trên SpeedyBee F405 AIO — `receiver_type = MSP`
- **Chưa test thực tế**: Manual takeoff flow, force_disarm khi đang bay

## Bugs Đã Sửa

| Bug | Fix | Phiên |
|---|---|---|
| DISARM delay 10-20s | Repeated-send state machine (DISARMING/FORCE_DISARMING) | 04-28 |
| ESP32 failsafe đóng socket | Giữ mở cho emergency override | 04-28 |
| Channel RPYT→AETR | Đồng bộ GCS + ESP32 | 04-28 |
| RSSI parse thiếu return | Thêm `result['rssi']` | 04-30 |
| GPS multipath | Haversine guard 3m | 04-28 |
| Rising edge NAV_WP | Giữ ANGLE→bung 2000 rising edge | 04-28 |
| **ESP32 TCP coalescing** | Loop parse tất cả EM: frames trong buffer | **05-03** |
| **_send_rc_emergency fallback** | Bỏ fallback send_command(), buộc emergency_queue | **05-03** |
| **force_disarm race** | timer.stop() TRƯỚC khi đổi state | **05-03** |
| **FORCE_DISARMING thiếu NAV_OFF** | Gửi NAV_OFF + DISARM mỗi tick | **05-03** |
| **LeftToolbar icon tràn** | font-size 20→16px, padding:0, width 48→52px | **05-03** |
| **EmergencyOverlay fade race** | Disconnect fade-out signal trước fade-in | **05-03** |
| **EmergencyOverlay hide guard** | Guard isVisible() trước animate | **05-03** |

## Ghi Nhớ Kỹ Thuật

- **BoxID SpeedyBee**: RTH=10, POSHOLD=11, FAILSAFE=27, NAV_WP=28 (KHÁC chuẩn INAV)
- **AUX2=2000 chồng chéo 3 mode** (ALTHOLD+POSHOLD+WP) là ĐÚNG thiết kế
- **LiDAR MTF-02**: Trust ≤2.2m, max 2.5m, giá trị âm = out of range
- **NAV_OFF 300ms**: INAV từ chối DISARM khi NAV active → phải tắt NAV trước
- **INAV MSP override**: Cần `receiver_type = MSP` HOẶC `msp_override_channels` bitmask + MSP_OVERRIDE mode
- **MSP_SET_RAW_RC ≥5Hz**: Dưới 5Hz INAV revert về RC gốc (failsafe)
- **Ground effect 3.5"**: Zone <1m, manual takeoff bật NAV sau 2m
- **EM: prefix**: ESP32 xóa UART buffer + gửi tức thì + tắt failsafe
- **send_emergency_command**: PHẢI dùng emergency queue, KHÔNG fallback sang command queue

## UI Updates (05-03)

- **LeftToolbar**: Thêm nút Manual Takeoff (M▲), xanh dương, nằm giữa NAV▲ và RTH⌂
- **EmergencyOverlay**: Fix fade race, button vẫn accessible khi overlay đang transition

## Việc Cần Làm Tiếp

- [ ] Test thực tế với phần cứng (HIL)
- [ ] Validate manual takeoff: ANGLE idle → throttle ramp → NAV switch
- [ ] Check `receiver_type` và `disarm_kill_switch` trên CLI
