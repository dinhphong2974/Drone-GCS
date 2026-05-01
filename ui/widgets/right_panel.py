"""
RightPanel — Panel phải 320px chứa Camera Feed và Command Log.

Cấu trúc dọc:
1. Section "CAMERA - LIVE": CameraWidget placeholder
2. Section "COMMAND & RESPONSE LOG": CommandLog widget
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QSizePolicy
)
from PySide6.QtCore import Qt

from ui.widgets.camera_widget import CameraWidget
from ui.widgets.command_log import CommandLog


class RightPanel(QWidget):
    """
    Panel phải chứa Camera Live Feed + Command Log.

    Widget ownership cho GCSApp:
        - camera_widget: CameraWidget (placeholder)
        - command_log: CommandLog (log giao tiếp GCS ↔ UAV)
    """

    DARK_BG = "#0d1117"
    SECTION_BG = "#0a0e17"
    BORDER_COLOR = "#1a2332"
    ACCENT_GREEN = "#00ff88"
    ACCENT_BLUE = "#2196F3"

    _GROUP_STYLE = """
        QGroupBox {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 6px;
            margin-top: 14px;
            padding-top: 18px;
            font-size: 10px;
            font-weight: bold;
            color: {accent};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
            color: {accent};
        }}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setObjectName("rightPanel")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 8)
        layout.setSpacing(6)

        # ═══════ SECTION 1: CAMERA ═══════
        camera_group = QGroupBox("CAMERA — LIVE")
        camera_group.setStyleSheet(
            self._GROUP_STYLE.format(
                bg=self.SECTION_BG, border=self.BORDER_COLOR,
                accent=self.ACCENT_GREEN
            )
        )
        cam_layout = QVBoxLayout(camera_group)
        cam_layout.setContentsMargins(4, 4, 4, 4)

        self.camera_widget = CameraWidget()
        self.camera_widget.setMinimumHeight(180)
        self.camera_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cam_layout.addWidget(self.camera_widget)

        layout.addWidget(camera_group, stretch=2)

        # ═══════ SECTION 2: COMMAND LOG ═══════
        log_group = QGroupBox("COMMAND & RESPONSE LOG")
        log_group.setStyleSheet(
            self._GROUP_STYLE.format(
                bg=self.SECTION_BG, border=self.BORDER_COLOR,
                accent=self.ACCENT_BLUE
            )
        )
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)

        self.command_log = CommandLog()
        self.command_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_layout.addWidget(self.command_log)

        layout.addWidget(log_group, stretch=3)

        # Panel background
        self.setStyleSheet(f"""
            #rightPanel {{
                background-color: {self.DARK_BG};
                border-left: 1px solid {self.BORDER_COLOR};
            }}
        """)
