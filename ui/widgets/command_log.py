"""
CommandLog — Widget Command & Response Log cho Right Panel.

Hiển thị lịch sử giao tiếp GCS ↔ UAV theo thời gian thực.
Auto-scroll, giới hạn 500 dòng, hỗ trợ Export và Clear.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor, QColor
from datetime import datetime


class CommandLog(QWidget):
    """
    Command & Response Log — readonly text area + nút Clear/Export.

    Public API:
        append_log(source, message, color=None)
        clear_log()
        export_log() → str
    """

    DARK_BG = "#0d1117"
    BORDER_COLOR = "#1a2332"
    TEXT_COLOR = "#c0c8d8"
    GCS_COLOR = "#00ff88"
    UAV_COLOR = "#2196F3"
    ERROR_COLOR = "#ff4444"
    WARN_COLOR = "#ffd700"

    MAX_LINES = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_count = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Log text area ──
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setFont(QFont("Consolas", 9))
        self.text_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: #080c14;
                color: {self.TEXT_COLOR};
                border: 1px solid {self.BORDER_COLOR};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: rgba(0, 255, 136, 0.2);
            }}
            QScrollBar:vertical {{
                background: #0a0e17;
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #2a3442;
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #3a4a5a;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        layout.addWidget(self.text_log)

        # ── Action buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 68, 68, 0.1);
                color: {self.ERROR_COLOR};
                border: 1px solid rgba(255, 68, 68, 0.3);
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 68, 68, 0.2);
            }}
        """)
        self.btn_clear.clicked.connect(self.clear_log)
        btn_layout.addWidget(self.btn_clear)

        self.btn_export = QPushButton("Export")
        self.btn_export.setFixedHeight(24)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 255, 136, 0.1);
                color: {self.GCS_COLOR};
                border: 1px solid rgba(0, 255, 136, 0.3);
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                padding: 0 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 255, 136, 0.2);
            }}
        """)
        btn_layout.addWidget(self.btn_export)

        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

    # ═══════ PUBLIC API ═══════

    def append_log(self, source: str, message: str, color: str = None):
        """
        Thêm một dòng log mới.

        Args:
            source: "GCS" hoặc "UAV" hoặc "SYS"
            message: Nội dung message
            color: Override màu (mặc định: xanh lá cho GCS, xanh dương cho UAV)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        if color is None:
            if source == "GCS":
                color = self.GCS_COLOR
            elif source == "UAV":
                color = self.UAV_COLOR
            elif source == "ERR":
                color = self.ERROR_COLOR
            elif source == "WARN":
                color = self.WARN_COLOR
            else:
                color = self.TEXT_COLOR

        # Format HTML line
        html = (
            f'<span style="color: {self.TEXT_COLOR};">[{timestamp}]</span> '
            f'<span style="color: {color}; font-weight: bold;">{source}:</span> '
            f'<span style="color: {self.TEXT_COLOR};">{message}</span>'
        )

        self.text_log.append(html)
        self._line_count += 1

        # Trim nếu quá MAX_LINES
        if self._line_count > self.MAX_LINES:
            self._trim_log()

        # Auto-scroll xuống cuối
        cursor = self.text_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.text_log.setTextCursor(cursor)

    def clear_log(self):
        """Xóa toàn bộ log."""
        self.text_log.clear()
        self._line_count = 0

    def export_log(self) -> str:
        """Xuất nội dung log dưới dạng plain text."""
        return self.text_log.toPlainText()

    # ═══════ PRIVATE ═══════

    def _trim_log(self):
        """Xóa 100 dòng đầu tiên khi vượt MAX_LINES."""
        cursor = self.text_log.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(100):
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.deleteChar()  # Xóa newline thừa
        self._line_count -= 100
