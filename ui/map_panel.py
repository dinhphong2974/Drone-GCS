"""
map_panel.py - Panel bản đồ trung tâm (refactored từ mission_tab.py).

Chứa class MapPanel(QWidget) bao gồm:
- Bản đồ OpenStreetMap nhúng qua QWebEngineView + Leaflet.js (local)
- Drone marker cập nhật vị trí real-time từ GPS BZ 251 (KHÔNG reload page)
- Path tracking — vẽ đường bay theo thời gian thực
- Click-to-add-waypoint — nhấp chuột lên bản đồ để tạo waypoint
- Floating overlay: Waypoint table + Action buttons (toggle qua toolbar)
- Logic an toàn: Cảnh báo khoảng cách + cấu hình failsafe

Architecture:
    assets/map.html     ← Leaflet map (self-contained, local JS/CSS)
    ↕ QWebChannel       ← Cầu nối JavaScript ↔ Python
    map_panel.py        ← Python backend (QWebEngineView)

Khác biệt so với mission_tab.py:
- BỎ QSplitter 70:30 — map chiếm toàn bộ khu vực center
- Waypoint panel nằm dạng floating overlay (QPushButton toggle)
- Giữ nguyên 100% logic: WebBridge, JS bridge, waypoint management

KHÔNG CÒN dùng folium. Leaflet.js load local từ assets/leaflet/.
"""

import os
import json
import math
from PySide6.QtCore import Qt, Slot, QUrl, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSpinBox, QInputDialog, QFrame
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel


# ══════════════════════════════════════════════
# HÀM TIỆN ÍCH — TÍNH KHOẢNG CÁCH HAVERSINE
# ══════════════════════════════════════════════

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Tính khoảng cách giữa 2 điểm trên mặt đất bằng công thức Haversine.

    Args:
        lat1, lon1: Tọa độ điểm 1 (độ thập phân)
        lat2, lon2: Tọa độ điểm 2 (độ thập phân)

    Returns:
        float: Khoảng cách (mét)
    """
    R = 6371000  # Bán kính trái đất (mét)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ══════════════════════════════════════════════
# WebBridge — Cầu nối Python ↔ JavaScript
# ══════════════════════════════════════════════

class WebBridge(QObject):
    """
    Cầu nối giao tiếp giữa JavaScript (Leaflet map) và Python (MapPanel).

    Class RIÊNG BIỆT kế thừa QObject, được đăng ký vào QWebChannel
    thay vì MapPanel, tránh cảnh báo:
    "Property '...' of object has no notify signal, is not bindable..."

    Signals:
        map_clicked(float, float): Phát khi user click trên bản đồ Leaflet
    """

    map_clicked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(float, float)
    def on_map_clicked(self, lat: float, lon: float):
        """
        Slot nhận tọa độ từ JavaScript khi user click trên bản đồ.

        JavaScript gọi: bridge.on_map_clicked(lat, lng)
        → Slot này phát signal map_clicked(lat, lon)
        → MapPanel._handle_map_click(lat, lon) xử lý UI
        """
        self.map_clicked.emit(lat, lon)


class MapPanel(QWidget):
    """
    Panel bản đồ trung tâm — chiếm toàn bộ khu vực giữa.

    Signals:
        waypoints_updated(list): Danh sách waypoint đã thay đổi
    """

    # ── Signals giao tiếp với GCSApp ──
    waypoints_updated = Signal(list)

    # ── Ngưỡng khoảng cách cảnh báo mặc định (mét) ──
    DEFAULT_DISTANCE_THRESHOLD = 50

    # ── Style constants ──
    OVERLAY_BG = "rgba(10, 14, 23, 0.92)"
    BORDER_COLOR = "#1a2332"
    ACCENT_GREEN = "#00ff88"
    ACCENT_BLUE = "#2196F3"
    TEXT_COLOR = "#c0c8d8"

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Dữ liệu nội bộ ──
        self._waypoints = []
        self._drone_lat = 0.0
        self._drone_lon = 0.0
        self._drone_heading = 0.0
        self._home_lat = 0.0
        self._home_lon = 0.0
        self._has_home = False
        self._distance_threshold = self.DEFAULT_DISTANCE_THRESHOLD
        self._waypoint_panel_visible = False

        # ── Cờ chống race condition ──
        self.map_is_ready = False

        # ── Đường dẫn tuyệt đối tới assets/map.html ──
        self._map_html_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'assets', 'map.html')
        )

        # ── WebBridge ──
        self._web_bridge = WebBridge(self)
        self._web_bridge.map_clicked.connect(self._handle_map_click)

        # ── Xây dựng UI ──
        self._setup_ui()

    def _setup_ui(self):
        """Map chiếm 100% — waypoint panel nằm dạng floating overlay."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Map WebView ──
        self.map_view = QWebEngineView()
        self.map_view.setMinimumSize(400, 300)

        settings = self.map_view.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalStorageEnabled, True
        )

        self._web_channel = QWebChannel()
        self._web_channel.registerObject("bridge", self._web_bridge)
        self.map_view.page().setWebChannel(self._web_channel)
        self.map_view.loadFinished.connect(self._on_map_loaded)

        layout.addWidget(self.map_view)

        # ── Floating waypoint panel (initially hidden) ──
        self._create_floating_waypoint_panel()

        # ── Floating locate button ──
        self.btn_locate_drone = QPushButton("📍", self)
        self.btn_locate_drone.setFixedSize(42, 42)
        self.btn_locate_drone.setToolTip("Định vị drone trên bản đồ")
        self.btn_locate_drone.setCursor(Qt.PointingHandCursor)
        self.btn_locate_drone.setStyleSheet("""
            QPushButton {
                background-color: rgba(10, 14, 23, 0.92);
                color: #4FC3F7;
                font-size: 20px;
                border: 1px solid #1a2332;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: rgba(20, 28, 46, 0.95);
                border-color: #4FC3F7;
            }
        """)
        self.btn_locate_drone.clicked.connect(self._locate_drone)

        # ── Load map ──
        self._load_map()

    def _create_floating_waypoint_panel(self):
        """Tạo floating overlay cho waypoint table + action buttons."""
        self.waypoint_overlay = QFrame(self)
        self.waypoint_overlay.setFixedWidth(300)
        self.waypoint_overlay.setStyleSheet(f"""
            QFrame {{
                background-color: {self.OVERLAY_BG};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 8px;
            }}
        """)
        self.waypoint_overlay.hide()

        overlay_layout = QVBoxLayout(self.waypoint_overlay)
        overlay_layout.setContentsMargins(8, 8, 8, 8)
        overlay_layout.setSpacing(6)

        # Header
        header = QLabel("📍 WAYPOINT LIST")
        header.setFont(QFont("Consolas", 10, QFont.Bold))
        header.setStyleSheet(f"color: {self.ACCENT_GREEN}; background: transparent; border: none;")
        overlay_layout.addWidget(header)

        # Waypoint table
        self.table_waypoints = QTableWidget()
        self.table_waypoints.setColumnCount(4)
        self.table_waypoints.setHorizontalHeaderItem(0, QTableWidgetItem("#"))
        self.table_waypoints.setHorizontalHeaderItem(1, QTableWidgetItem("Lat"))
        self.table_waypoints.setHorizontalHeaderItem(2, QTableWidgetItem("Lon"))
        self.table_waypoints.setHorizontalHeaderItem(3, QTableWidgetItem("Alt"))

        header_view = self.table_waypoints.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Stretch)

        self.table_waypoints.setMaximumHeight(200)
        self.table_waypoints.setStyleSheet(f"""
            QTableWidget {{
                background-color: #080c14;
                color: {self.TEXT_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 4px;
                gridline-color: {self.BORDER_COLOR};
                font-size: 9px;
            }}
            QHeaderView::section {{
                background-color: #0a0e17;
                color: {self.ACCENT_GREEN};
                border: 1px solid {self.BORDER_COLOR};
                font-weight: bold;
                font-size: 9px;
                padding: 3px;
            }}
            QTableWidget::item:selected {{
                background-color: rgba(0, 255, 136, 0.15);
            }}
        """)
        overlay_layout.addWidget(self.table_waypoints)

        # Distance + failsafe
        dist_row = QHBoxLayout()
        self.val_distance = QLabel("Dist: N/A")
        self.val_distance.setFont(QFont("Consolas", 9, QFont.Bold))
        self.val_distance.setStyleSheet(f"color: {self.ACCENT_GREEN}; background: transparent; border: none;")
        dist_row.addWidget(self.val_distance)

        self.val_failsafe_status = QLabel("FS: RTH")
        self.val_failsafe_status.setFont(QFont("Consolas", 9, QFont.Bold))
        self.val_failsafe_status.setStyleSheet(f"color: {self.ACCENT_BLUE}; background: transparent; border: none;")
        dist_row.addWidget(self.val_failsafe_status)
        overlay_layout.addLayout(dist_row)

        # Action buttons
        btn_row1 = QHBoxLayout()

        self.btn_remove = QPushButton("🗑️ Remove")
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.clicked.connect(self._remove_selected_waypoint)
        self.btn_remove.setStyleSheet(self._action_btn_style("#F44336"))
        btn_row1.addWidget(self.btn_remove)

        self.btn_clear = QPushButton("🧹 Clear")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_all_waypoints)
        self.btn_clear.setStyleSheet(self._action_btn_style("#F44336"))
        btn_row1.addWidget(self.btn_clear)
        overlay_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()

        self.btn_upload = QPushButton("⬆️ Upload")
        self.btn_upload.setCursor(Qt.PointingHandCursor)
        self.btn_upload.setStyleSheet(self._action_btn_style("#2196F3"))
        btn_row2.addWidget(self.btn_upload)

        self.btn_start_mission_tab = QPushButton("▶️ Start")
        self.btn_start_mission_tab.setCursor(Qt.PointingHandCursor)
        self.btn_start_mission_tab.setStyleSheet(self._action_btn_style("#4CAF50"))
        btn_row2.addWidget(self.btn_start_mission_tab)
        overlay_layout.addLayout(btn_row2)

        self.btn_stop_mission = QPushButton("⏹️ Stop Mission")
        self.btn_stop_mission.setCursor(Qt.PointingHandCursor)
        self.btn_stop_mission.setStyleSheet(self._action_btn_style("#F44336"))
        overlay_layout.addWidget(self.btn_stop_mission)

    def _action_btn_style(self, color: str) -> str:
        """Generate consistent dark-mode button style."""
        return f"""
            QPushButton {{
                background-color: rgba({self._hex_to_rgb(color)}, 0.15);
                color: {color};
                border: 1px solid rgba({self._hex_to_rgb(color)}, 0.4);
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: rgba({self._hex_to_rgb(color)}, 0.3);
            }}
        """

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> str:
        """Convert #RRGGBB to R, G, B string."""
        h = hex_color.lstrip('#')
        return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"

    # ══════════════════════════════════════════════
    # BẢN ĐỒ (QWebEngineView + Leaflet local)
    # ══════════════════════════════════════════════

    def _load_map(self):
        """Tải file map.html local vào QWebEngineView."""
        self.map_is_ready = False

        if not os.path.isfile(self._map_html_path):
            self.map_view.setHtml(
                "<html><body style='background:#0a0e17; color:#ff4444; "
                "display:flex; align-items:center; justify-content:center;'>"
                f"<h2>⚠️ Không tìm thấy: {self._map_html_path}</h2>"
                "</body></html>"
            )
            print(f"[MapPanel] ERROR: map.html not found at {self._map_html_path}")
            return

        url = QUrl.fromLocalFile(self._map_html_path)
        self.map_view.setUrl(url)
        print(f"[MapPanel] Loading map from: {url.toString()}")

    def _on_map_loaded(self, ok: bool):
        """Callback khi QWebEngineView tải xong HTML."""
        if not ok:
            print("[MapPanel] ERROR: Failed to load map.html")
            self.map_is_ready = False
            return

        self.map_is_ready = True
        print("[MapPanel] OK - map.html loaded successfully")

        self._reposition_overlays()

        # Sync lại dữ liệu hiện có
        if self._has_home:
            self._js_update_home()
        if self._drone_lat != 0.0 or self._drone_lon != 0.0:
            self._js_update_drone()
        if self._waypoints:
            self._js_update_waypoints()

    # ══════════════════════════════════════════════
    # JAVASCRIPT BRIDGE — Gọi JS từ Python
    # ══════════════════════════════════════════════

    def _run_js(self, script: str):
        """Helper an toàn để chạy JavaScript — chỉ khi map sẵn sàng."""
        if self.map_is_ready:
            self.map_view.page().runJavaScript(script)

    def _js_update_drone(self):
        """Gọi JS updateDronePosition() — di chuyển drone marker."""
        self._run_js(
            f"updateDronePosition({self._drone_lat}, {self._drone_lon}, {self._drone_heading});"
        )

    def _js_update_home(self):
        """Gọi JS updateHomePosition() — đặt/di chuyển home marker."""
        self._run_js(
            f"updateHomePosition({self._home_lat}, {self._home_lon});"
        )

    def _js_update_waypoints(self):
        """Gọi JS updateWaypoints() — vẽ lại waypoint markers + route."""
        wp_json = json.dumps(self._waypoints)
        self._run_js(f"updateWaypoints({json.dumps(wp_json)});")

    def _js_set_view(self, lat: float, lon: float, zoom: int = 0):
        """Gọi JS setMapView() — di chuyển bản đồ tới vị trí."""
        self._run_js(f"setMapView({lat}, {lon}, {zoom});")

    def _js_clear_all(self):
        """Gọi JS clearAll() — xóa toàn bộ markers và polylines."""
        self._run_js("clearAll();")

    # ══════════════════════════════════════════════
    # FLOATING OVERLAYS POSITIONING
    # ══════════════════════════════════════════════

    def _locate_drone(self):
        """Chuyển bản đồ về vị trí GPS hiện tại của drone."""
        if self._drone_lat == 0.0 and self._drone_lon == 0.0:
            QMessageBox.warning(
                self,
                "Không có vị trí",
                "Chưa nhận được tọa độ GPS từ drone.\n"
                "Hãy đảm bảo drone đã kết nối và có GPS fix."
            )
            return
        self._js_set_view(self._drone_lat, self._drone_lon, 17)

    def resizeEvent(self, event):
        """Giữ vị trí floating overlays khi resize."""
        super().resizeEvent(event)
        self._reposition_overlays()

    def _reposition_overlays(self):
        """Đặt lại vị trí locate button và waypoint panel."""
        margin = 12

        # Locate button — bottom-left
        if hasattr(self, 'btn_locate_drone'):
            x = margin
            y = self.height() - self.btn_locate_drone.height() - margin - 20
            self.btn_locate_drone.move(x, max(y, margin))
            self.btn_locate_drone.raise_()

        # Waypoint panel — top-right
        if hasattr(self, 'waypoint_overlay') and self.waypoint_overlay.isVisible():
            x = self.width() - self.waypoint_overlay.width() - margin
            y = margin
            self.waypoint_overlay.move(max(x, margin), y)
            self.waypoint_overlay.setFixedHeight(self.height() - margin * 2)
            self.waypoint_overlay.raise_()

    def toggle_waypoint_panel(self):
        """Toggle hiển thị waypoint panel overlay."""
        self._waypoint_panel_visible = not self._waypoint_panel_visible
        if self._waypoint_panel_visible:
            self.waypoint_overlay.show()
        else:
            self.waypoint_overlay.hide()
        self._reposition_overlays()

    # ══════════════════════════════════════════════
    # XỬ LÝ CLICK TỪ BẢN ĐỒ (qua WebBridge)
    # ══════════════════════════════════════════════

    def _handle_map_click(self, lat: float, lon: float):
        """Xử lý tọa độ khi user click trên bản đồ Leaflet."""
        alt, ok = QInputDialog.getDouble(
            self,
            "Thêm Waypoint",
            f"Tọa độ: ({lat:.6f}, {lon:.6f})\n\nNhập độ cao (mét):",
            value=10.0, minValue=1.0, maxValue=120.0, decimals=1
        )
        if ok:
            self._add_waypoint(lat, lon, alt)

    # ══════════════════════════════════════════════
    # QUẢN LÝ WAYPOINT
    # ══════════════════════════════════════════════

    def _add_waypoint(self, lat: float, lon: float, alt: float):
        """Thêm waypoint mới."""
        wp = {"lat": lat, "lon": lon, "alt": alt}
        self._waypoints.append(wp)

        row = self.table_waypoints.rowCount()
        self.table_waypoints.insertRow(row)
        self.table_waypoints.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table_waypoints.setItem(row, 1, QTableWidgetItem(f"{lat:.6f}"))
        self.table_waypoints.setItem(row, 2, QTableWidgetItem(f"{lon:.6f}"))
        self.table_waypoints.setItem(row, 3, QTableWidgetItem(f"{alt:.1f}"))

        self._js_update_waypoints()
        self.waypoints_updated.emit(self._waypoints)

    def _remove_selected_waypoint(self):
        """Xóa waypoint đang chọn."""
        row = self.table_waypoints.currentRow()
        if 0 <= row < len(self._waypoints):
            self._waypoints.pop(row)
            self.table_waypoints.removeRow(row)
            for i in range(self.table_waypoints.rowCount()):
                self.table_waypoints.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._js_update_waypoints()
            self.waypoints_updated.emit(self._waypoints)

    def _clear_all_waypoints(self):
        """Xóa toàn bộ waypoint."""
        self._waypoints.clear()
        self.table_waypoints.setRowCount(0)
        self._js_update_waypoints()
        self.waypoints_updated.emit(self._waypoints)

    # ══════════════════════════════════════════════
    # CẬP NHẬT VỊ TRÍ DRONE (gọi từ GCSApp)
    # ══════════════════════════════════════════════

    def update_drone_position(self, lat: float, lon: float, heading: float = 0.0):
        """Cập nhật vị trí drone trên bản đồ (no reload)."""
        if lat == 0.0 and lon == 0.0:
            return
        self._drone_lat = lat
        self._drone_lon = lon
        self._drone_heading = heading
        self._js_update_drone()
        self._update_distance_display()

    def update_home_position(self, lat: float, lon: float):
        """Cập nhật vị trí Home (chốt khi ARM)."""
        if lat == 0.0 and lon == 0.0:
            return
        self._home_lat = lat
        self._home_lon = lon
        self._has_home = True
        self._js_update_home()

    def update_telemetry(self, lat: float, lon: float, heading: float = 0.0):
        """Alias cho update_drone_position."""
        self.update_drone_position(lat, lon, heading)

    def _update_distance_display(self):
        """Cập nhật hiển thị khoảng cách drone → Home."""
        if not self._has_home or (self._drone_lat == 0.0 and self._drone_lon == 0.0):
            self.val_distance.setText("Dist: N/A")
            return

        dist = haversine_distance(
            self._home_lat, self._home_lon,
            self._drone_lat, self._drone_lon
        )

        if dist < 1000:
            self.val_distance.setText(f"Dist: {dist:.0f}m")
        else:
            self.val_distance.setText(f"Dist: {dist/1000:.2f}km")

        if dist > self._distance_threshold:
            self.val_distance.setStyleSheet("color: #ff4444; font-weight: bold; background: transparent; border: none;")
        else:
            self.val_distance.setStyleSheet("color: #00ff88; font-weight: bold; background: transparent; border: none;")

    def check_distance_warning(self) -> bool:
        """Kiểm tra khoảng cách drone có vượt ngưỡng không."""
        if not self._has_home:
            return False
        dist = haversine_distance(
            self._home_lat, self._home_lon,
            self._drone_lat, self._drone_lon
        )
        return dist > self._distance_threshold

    def get_waypoints(self) -> list[dict]:
        """Trả về danh sách waypoint hiện tại."""
        return self._waypoints.copy()

    def refresh_map(self):
        """Cập nhật bản đồ — legacy compatibility."""
        if not self.map_is_ready:
            return
        self._js_update_waypoints()
        if self._has_home:
            self._js_update_home()
        if self._drone_lat != 0.0 or self._drone_lon != 0.0:
            self._js_update_drone()
