"""
MainWindow builds the UI layout using qFluentWidgets.

* Left pane – Command library (QTableWidget)
* Right pane – Hex input (QLineEdit) + Parse button + Result view (QPlainTextEdit)
* Top toolbar – Theme toggle button (light / dark)
* All widgets are wired to async slots so the UI stays responsive.
"""

import json
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    FluentWindow,
    Action,
    RoundMenu,
    SwitchButton,
    ToolButton,
    Theme,
    setTheme,
)


class MainWindow(FluentWindow):
    """Top‑level window that contains all panels."""

    def __init__(self, protocol_cfg: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.protocol_cfg = protocol_cfg

        # ---- Toolbar -------------------------------------------------
        self.setWindowTitle("Serial Port Data Parser – PySide6 UI")
        self.resize(960, 640)

        # Theme toggle in the title bar
        self.theme_switch = SwitchButton(self)
        self.theme_switch.setChecked(False)  # start with Light theme
        self.theme_switch.toggled.connect(self._on_theme_toggled)
        self.addToolBarAction(Action("Toggle Theme", lambda: None, parent=self))
        self.titleBar.addWidget(self.theme_switch)

        # ---- Central widget -------------------------------------------
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # ---- Command Library (left) ----------------------------------
        self.cmd_table = QTableWidget()
        self.cmd_table.setColumnCount(4)
        self.cmd_table.setHorizontalHeaderLabels(["Idx", "Name", "Code", "Description"]) 
        self.cmd_table.horizontalHeader().setStretchLastSection(True)
        self._populate_command_table()
        main_layout.addWidget(self.cmd_table, 1)

        # ---- Right side (hex input + result) -------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Hex input line + Parse button
        input_row = QHBoxLayout()
        self.hex_input = QLineEdit()
        self.hex_input.setPlaceholderText("Enter HEX string, e.g. A5 A5 03 01 00 02 11 22 33")
        self.parse_btn = QPushButton("Parse")
        self.parse_btn.clicked.connect(self._on_parse_clicked)

        input_row.addWidget(QLabel("HEX:"))
        input_row.addWidget(self.hex_input, 1)
        input_row.addWidget(self.parse_btn)
        right_layout.addLayout(input_row)

        # Result view (plain text)
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        right_layout.addWidget(self.result_view, 1)

        main_layout.addWidget(right_panel, 2)

        # ---- Debounce timer for live preview (optional) -------------
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setInterval(300)  # 300 ms
        self._debounce_timer.setSingleShot(True)
        self.hex_input.textChanged.connect(self._debounce_timer.start)
        self._debounce_timer.timeout.connect(self._preview_parse)

    # -----------------------------------------------------------------
    # Theme handling
    def _on_theme_toggled(self, checked: bool):
        setTheme(Theme.DARK if checked else Theme.LIGHT)

    # -----------------------------------------------------------------
    # Command library population
    def _populate_command_table(self):
        cmds = self.protocol_cfg.get("commands", [])
        self.cmd_table.setRowCount(len(cmds))
        for row, cmd in enumerate(cmds):
            idx_item = QTableWidgetItem(str(row + 1))
            name_item = QTableWidgetItem(str(cmd.get("name", "")))
            code_item = QTableWidgetItem(str(cmd.get("cmd_code", "")))
            desc_item = QTableWidgetItem(str(cmd.get("description", "")))

            for col, item in enumerate([idx_item, name_item, code_item, desc_item]):
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.cmd_table.setItem(row, col, item)

        self.cmd_table.resizeColumnsToContents()

    # -----------------------------------------------------------------
    # Parsing helpers
    @Slot()
    def _on_parse_clicked(self):
        """Parse when the user explicitly clicks the button."""
        self._do_parse_and_show(self.hex_input.text())

    @Slot()
    def _preview_parse(self):
        """Live preview while typing (debounced)."""
        self._do_parse_and_show(self.hex_input.text(), live=True)

    def _do_parse_and_show(self, raw_hex: str, live: bool = False):
        """Core parsing routine – catches errors and formats output."""
        raw_hex = raw_hex.strip()
        if not raw_hex:
            self.result_view.clear()
            return

        try:
            from protocol_parser import parse_hex_input, split_frame, classify_protocol_error, _log_error_to_disk
            data = parse_hex_input(raw_hex)
        except Exception as exc:
            friendly, debug = classify_protocol_error(exc)
            self.result_view.setPlainText(f"[输入错误] {friendly}")
            _log_error_to_disk(exc)
            return

        try:
            frame = split_frame(data, self.protocol_cfg)
        except Exception as exc:
            friendly, debug = classify_protocol_error(exc)
            self.result_view.setPlainText(f"[解析错误] {friendly}")
            _log_error_to_disk(exc)
            return

        lines = [
            f"原始字节: {frame.raw.hex().upper()}",
            f"帧头: 0x{frame.header:04X}",
            f"版本: {frame.ver}",
            f"命令码: 0x{frame.cmd_code:02X}",
            f"数据长度: {frame.length}",
            f"校验: {'通过' if frame.checksum_ok else '失败' if frame.checksum_ok is not None else '未配置'}",
        ]

        # Find command definition for extra info
        cmd_def = None
        for c in self.protocol_cfg.get("commands", []):
            if int(c.get("cmd_code", 0), 0) == frame.cmd_code:
                cmd_def = c
                break

        if cmd_def:
            lines.append(f"命令名: {cmd_def.get('name', '')}")
            lines.append(f"说明: {cmd_def.get('description', '')}")

        if frame.data:
            lines.append(f"载荷 (HEX): {frame.data.hex().upper()}")

        self.result_view.setPlainText("\n".join(lines))

        if live:
            self.result_view.setStyleSheet("color: #666666;")
