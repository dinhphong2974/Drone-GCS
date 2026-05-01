"""
CameraWidget — Placeholder widget cho Camera Live Feed.

Hiển thị "NO SIGNAL" trên nền đen với tab bar mini (Main/Thermal/FPV).
Chức năng video stream sẽ được bổ sung sau.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTabBar, QHBoxLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class CameraWidget(QWidget):
    """
    Camera Live Feed placeholder — sẵn sàng tích hợp stream.

    Tabs: Main | Thermal | FPV
    HUD overlay: RES / FPS / B/W (sẽ kích hoạt khi có stream)
    """

    DARK_BG = "#050508"
    BORDER_COLOR = "#1a2332"
    TEXT_MUTED = "#3a3a4a"
    ACCENT_GREEN = "#00ff88"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Tab bar ──
        self.tab_bar = QTabBar()
        self.tab_bar.addTab("GÓC NHÌN CHÍNH")
        self.tab_bar.addTab("THERMAL")
        self.tab_bar.addTab("FPV")
        self.tab_bar.setCurrentIndex(0)
        self.tab_bar.setStyleSheet(f"""
            QTabBar {{
                background: #0a0e17;
                border: none;
            }}
            QTabBar::tab {{
                background: transparent;
                color: #808098;
                font-size: 9px;
                font-weight: bold;
                padding: 4px 10px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {self.ACCENT_GREEN};
                border-bottom: 2px solid {self.ACCENT_GREEN};
            }}
            QTabBar::tab:hover {{
                color: #c0c8d8;
            }}
        """)
        layout.addWidget(self.tab_bar)

        # ── Video area (placeholder) ──
        self.video_frame = QWidget()
        self.video_frame.setStyleSheet(f"""
            background-color: {self.DARK_BG};
            border: 1px solid {self.BORDER_COLOR};
            border-radius: 4px;
        """)
        video_layout = QVBoxLayout(self.video_frame)
        video_layout.setAlignment(Qt.AlignCenter)

        # "NO SIGNAL" text
        self.lbl_no_signal = QLabel("NO SIGNAL")
        self.lbl_no_signal.setFont(QFont("Consolas", 14, QFont.Bold))
        self.lbl_no_signal.setStyleSheet(f"color: {self.TEXT_MUTED}; background: transparent; border: none;")
        self.lbl_no_signal.setAlignment(Qt.AlignCenter)
        video_layout.addWidget(self.lbl_no_signal)

        # Scanline effect text
        self.lbl_scanline = QLabel("▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒")
        self.lbl_scanline.setFont(QFont("Consolas", 8))
        self.lbl_scanline.setStyleSheet(f"color: #1a1a2e; background: transparent; border: none;")
        self.lbl_scanline.setAlignment(Qt.AlignCenter)
        video_layout.addWidget(self.lbl_scanline)

        layout.addWidget(self.video_frame, stretch=1)

        # ── HUD overlay info ──
        hud_layout = QHBoxLayout()
        hud_layout.setContentsMargins(8, 2, 8, 4)

        self.lbl_resolution = QLabel("RES: ---")
        self.lbl_resolution.setFont(QFont("Consolas", 8))
        self.lbl_resolution.setStyleSheet(f"color: {self.TEXT_MUTED};")
        hud_layout.addWidget(self.lbl_resolution)

        self.lbl_fps = QLabel("FPS: ---")
        self.lbl_fps.setFont(QFont("Consolas", 8))
        self.lbl_fps.setStyleSheet(f"color: {self.TEXT_MUTED};")
        hud_layout.addWidget(self.lbl_fps)

        self.lbl_bandwidth = QLabel("B/W: ---")
        self.lbl_bandwidth.setFont(QFont("Consolas", 8))
        self.lbl_bandwidth.setStyleSheet(f"color: {self.TEXT_MUTED};")
        hud_layout.addWidget(self.lbl_bandwidth)

        hud_layout.addStretch(1)
        layout.addLayout(hud_layout)
