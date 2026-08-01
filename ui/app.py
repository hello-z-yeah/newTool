"""PySide6 main window for the serial protocol parsing tool.

The backend modules (serial worker, protocol parser, raw saver and command
library) are intentionally kept UI-framework agnostic.  This module replaces
the former CustomTkinter interface with a native Qt/PySide6 application.
"""
from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections import deque
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.command_library import CommandLibraryError, CommandLibraryStore
from core.command_sender import (
    CommandSender,
    build_ascii_payload,
    build_hex_payload,
    extract_command_code,
    normalize_direction,
    parse_fields_json,
)
from protocol_parser import (
    ProtocolError,
    ResultLogger,
    classify_protocol_error,
    to_hex,
)
from protocol_parser.paths import user_data_path
from protocol_parser.protocol_manager import ProtocolManager
from serial_core.serial_worker import SerialWorker
from storage import RawDataSaver

from .components import (
    CardFrame,
    ComboBox,
    CommandLibraryTable,
    HoverScrollController,
    IntegerLineEdit,
    OutlineFrame,
    SegmentToggle,
    StateButton,
    UnifiedComboBox,
    ZoomableDataView,
    add_combo_item,
    set_button_width_for_texts,
    signals_blocked,
)
from .theme import (
    APP_BG,
    BUTTON_HEIGHT,
    BUTTON_SHADOW_PAD_X,
    BUTTON_SHADOW_PAD_Y,
    CARD_GAP,
    CONTROL_GAP_X,
    CONTROL_HEIGHT,
    CONTROL_ROW_MIN_HEIGHT,
    LIBRARY_MAX_ROWS,
    MONO_FONT_FAMILY,
    NAV_HEIGHT,
    PAGE_MARGIN_X,
    PAGE_MARGIN_Y,
    RX_FONT_DEFAULT_SIZE,
    SECTION_PADDING_X,
    SECTION_PADDING_Y,
    SECTION_ROW_GAP,
    SEND_CARD_HEIGHT,
    STATUS_HEIGHT,
    UI_FONT_FAMILY,
    build_stylesheet,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMMANDS_JSON = DATA_DIR / "commands.json"

# Development-only geometry audit. Keep disabled in normal runs.
DEBUG_UI_AUDIT = False


class UiBridge(QObject):
    serialError = Signal(str)
    storageError = Signal(str)
    monitorResult = Signal(bool, str)
    reconnectResult = Signal(bool, str)


class SerialApp(QMainWindow):
    """Main PySide6 window."""

    def __init__(self, initial_port: str | None = None, initial_baud: str = "9600") -> None:
        super().__init__()
        self.setWindowTitle("串口协议解析工具 v1.2.0")
        # Keep the standard Windows system menu and close button available.
        # Topmost changes below use SetWindowPos and never recreate the window.
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet())
            # 注意：主字体已在 main.py 中通过 app.setFont(UI_FONT_FAMILY, UI_FONT_POINT_SIZE) 统一设置。
            # 这里不再重复设置，避免覆盖 main.py 的 pt 字号为 px 字号。

        self.initial_port = initial_port
        self.initial_baud = str(initial_baud)

        # UI state
        self.library_visible = False
        self.send_visible = False
        self.config_expanded = False
        self.parse_mode = False
        self.auto_scroll = True
        self.packet_display_enabled = False
        self.packet_timeout_ms = 20
        self.display_mode = "hex"
        self.monitoring = False
        self.monitor_starting = False
        self.serial_reconfiguring = False
        self.active_serial_config: dict[str, Any] | None = None
        self.topmost_enabled = False

        # Send state
        self.send_mode = "protocol"
        self.append_crlf_enabled = False
        self.auto_checksum_enabled = False
        self.auto_send_enabled = False
        self.auto_send_interval_ms = 1000
        self._send_buffers = {
            "protocol": '{\n  "value": 1\n}',
            "hex": "",
            "ascii": "",
        }
        self._send_cmd_map: dict[str, int] = {}
        self._quick_action_map: dict[str, dict[str, Any]] = {}

        # Command library state
        self.cmdlib_mode = "hex"
        self.selected_command_index: int | None = None
        self.cmdlib_cycle_on = False
        self.cmdlib_cycle_index = 0
        self.cmdlib_cycle_steps: list[dict[str, Any]] = []

        # Receive state / batching
        self.rx_history: deque[dict[str, Any]] = deque(maxlen=5000)
        self.rx_ui_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10000)
        self.rx_ui_batch_records = 200
        self.rx_ui_batch_bytes = 65536
        self.rx_ui_dropped = 0
        self.rx_count = 0
        self.tx_count = 0
        self.error_count = 0
        self._display_packet_buffer = bytearray()
        self._display_packet_first_ts: float | None = None

        self.port_display_map: dict[str, str] = {}

        # Backend services
        self.bridge = UiBridge(self)
        self.bridge.serialError.connect(self._handle_serial_error)
        self.bridge.storageError.connect(self._show_storage_error)
        self.bridge.monitorResult.connect(self._on_monitor_result)
        self.bridge.reconnectResult.connect(self._on_reconnect_result)

        self.worker = SerialWorker(
            callback=self._on_serial_data,
            error_callback=lambda error: self.bridge.serialError.emit(str(error)),
        )
        self.raw_saver = RawDataSaver(
            error_callback=lambda message: self.bridge.storageError.emit(str(message))
        )

        builtin_dir = PROJECT_ROOT / "product"
        user_proto_dir = DATA_DIR / "protocols" / "imported"
        self.protocol_manager = ProtocolManager(builtin_dir, user_proto_dir)
        self.protocol_manager.load_builtin_protocols()
        self.frame_synchronizer = None
        self.result_logger: ResultLogger | None = None

        self.command_library = CommandLibraryStore(
            user_data_path("cmdlib"),
            legacy_file=COMMANDS_JSON,
        )
        self.command_sender = CommandSender(
            send_bytes=self.worker.send,
            is_connected=lambda: bool(self.monitoring and self.worker.is_connected),
            on_tx=self._on_tx_sent,
        )

        # Timers
        self.rx_timer = QTimer(self)
        self.rx_timer.setInterval(30)
        self.rx_timer.timeout.connect(self._drain_rx_ui_queue)

        self.packet_timer = QTimer(self)
        self.packet_timer.setSingleShot(True)
        self.packet_timer.timeout.connect(self._flush_display_packet)

        self.reconfigure_timer = QTimer(self)
        self.reconfigure_timer.setSingleShot(True)
        self.reconfigure_timer.setInterval(300)
        self.reconfigure_timer.timeout.connect(self._begin_live_serial_reconfigure)

        self.auto_send_timer = QTimer(self)
        self.auto_send_timer.timeout.connect(self._auto_send_tick)

        self.cycle_timer = QTimer(self)
        self.cycle_timer.setSingleShot(True)
        self.cycle_timer.timeout.connect(self._cmdlib_cycle_tick)

        self._build_ui()
        self._load_initial_state()
        self.rx_timer.start()

        # 尺寸审计仅在开发时启用，并等待布局完成，避免隐藏控件宽度为 0 的误报。
        if DEBUG_UI_AUDIT:
            QTimer.singleShot(800, self._audit_button_geometry)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)

        self.root_layout = QVBoxLayout(root)
        # 主页面布局：窗口四边留白统一使用 PAGE_MARGIN
        self.root_layout.setContentsMargins(
            PAGE_MARGIN_X,
            PAGE_MARGIN_Y,
            PAGE_MARGIN_X,
            PAGE_MARGIN_Y,
        )
        self.root_layout.setSpacing(CARD_GAP)

        self._build_nav()
        self._build_config()
        self._build_workspace()
        self._build_send_area()
        self._build_statusbar()

    def _new_card_layout(self, card: CardFrame) -> QVBoxLayout:
        """统一卡片内部布局：左右 SECTION_PADDING_X，上下 SECTION_PADDING_Y，行间距 SECTION_ROW_GAP。"""
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
        )
        layout.setSpacing(SECTION_ROW_GAP)
        return layout

    def _build_nav(self) -> None:
        self.nav_card = CardFrame(self)
        self.nav_card.setFixedHeight(NAV_HEIGHT)
        layout = QHBoxLayout(self.nav_card)
        # 卡片内部留白统一
        layout.setContentsMargins(
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
        )
        layout.setSpacing(CONTROL_GAP_X)

        title = QLabel("串口配置", self.nav_card)
        title.setProperty("title", True)
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)

        self.nav_send_button = StateButton("指令发送", self.nav_card, checkable=True)
        self.nav_send_button.setFixedHeight(BUTTON_HEIGHT)
        self.nav_send_button.toggled.connect(self._set_send_visible)
        layout.addWidget(self.nav_send_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.nav_library_button = StateButton("指令库", self.nav_card, checkable=True)
        self.nav_library_button.setFixedHeight(BUTTON_HEIGHT)
        self.nav_library_button.toggled.connect(self._set_library_visible)
        layout.addWidget(self.nav_library_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.add_serial_button = StateButton("添加串口", self.nav_card)
        self.add_serial_button.setFixedHeight(BUTTON_HEIGHT)
        self.add_serial_button.clicked.connect(self._launch_new_serial_tool)
        layout.addWidget(self.add_serial_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.save_log_button = StateButton("保存日志", self.nav_card)
        self.save_log_button.setFixedHeight(BUTTON_HEIGHT)
        self.save_log_button.clicked.connect(self._open_save_log_dialog)
        layout.addWidget(self.save_log_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.topmost_button = StateButton("置顶", self.nav_card, checkable=True)
        self.topmost_button.setFixedHeight(BUTTON_HEIGHT)
        self.topmost_button.toggled.connect(self._on_topmost_toggled)
        layout.addWidget(self.topmost_button, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)
        self.root_layout.addWidget(self.nav_card)

    # ------------------------------------------------------------------
    # Unified combo-box factory + status-bar hover preview
    # ------------------------------------------------------------------
    def _create_combo(
        self,
        *,
        status_name: str,
        editable: bool = False,
        parent=None,
    ) -> UnifiedComboBox:
        if parent is None:
            parent = self
        combo = UnifiedComboBox(parent, status_name=status_name)
        combo.setEditable(bool(editable))
        combo.optionHovered.connect(self._show_combo_option_status)
        combo.optionHoverCleared.connect(self._clear_combo_option_status)
        return combo

    def _show_combo_option_status(self, category: str, text: str) -> None:
        category = str(category).strip()
        text = str(text).strip()
        if not text:
            self._clear_combo_option_status()
            return
        display_text = f"{category}：{text}" if category else text
        self.combo_hover_status.setText(display_text)
        self.combo_hover_status.setToolTip(display_text)

    def _clear_combo_option_status(self) -> None:
        if not hasattr(self, "combo_hover_status") or self.combo_hover_status is None:
            return
        self.combo_hover_status.clear()
        self.combo_hover_status.setToolTip("")

    def _build_config(self) -> None:
        self.config_card = CardFrame(self)
        self.config_layout = QVBoxLayout(self.config_card)
        # 统一卡片留白：顶部、各行之间、底部都是 8px
        self.config_layout.setContentsMargins(
            SECTION_PADDING_X,
            SECTION_ROW_GAP,
            SECTION_PADDING_X,
            SECTION_ROW_GAP,
        )
        self.config_layout.setSpacing(SECTION_ROW_GAP)
        # 关键：所有内容始终从顶部开始排列，第一行永不下移
        self.config_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- 串口第一行：行高 = 42px，上下 BUTTON_SHADOW_PAD_Y 防阴影裁切 ---
        self.serial_header = QWidget(self.config_card)
        self.serial_header.setFixedHeight(CONTROL_ROW_MIN_HEIGHT)
        self.serial_header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_layout = QHBoxLayout(self.serial_header)
        # 给阴影上下留 4px，按钮本体 34px 居中
        header_layout.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        header_layout.setSpacing(CONTROL_GAP_X)

        port_label = QLabel("串口", self.serial_header)
        port_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(port_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.port_combo = self._create_combo(status_name="串口", parent=self.serial_header)
        self.port_combo.setMinimumWidth(360)
        self.port_combo.setFixedHeight(CONTROL_HEIGHT)
        header_layout.addWidget(self.port_combo, 1, Qt.AlignmentFlag.AlignVCenter)

        self.refresh_ports_button = StateButton("刷新", self.serial_header)
        self.refresh_ports_button.setFixedHeight(BUTTON_HEIGHT)
        self.refresh_ports_button.clicked.connect(self._refresh_ports)
        header_layout.addWidget(self.refresh_ports_button, 0, Qt.AlignmentFlag.AlignVCenter)

        baud_label = QLabel("波特率", self.serial_header)
        baud_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(baud_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.baud_combo = self._create_combo(status_name="波特率", editable=True, parent=self.serial_header)
        baud_values = ["9600", "19200", "38400", "57600", "115200", "460800", "921600", "1000000", "2000000"]
        for value in baud_values:
            add_combo_item(self.baud_combo, value, value, f"波特率：{value}")
        self.baud_combo.setCurrentText(self.initial_baud)
        self.baud_combo.setMinimumWidth(150)
        self.baud_combo.setFixedHeight(CONTROL_HEIGHT)
        header_layout.addWidget(self.baud_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        header_layout.addStretch(1)

        self.expand_button = StateButton("展开 ▼", self.serial_header, checkable=True)
        self.expand_button.setFixedHeight(BUTTON_HEIGHT)
        # 展开/收起：提前根据最长文字固定宽度，绝不因为换文字而位移/裁切
        set_button_width_for_texts(self.expand_button, ("展开 ▼", "收起 ▲"))
        self.expand_button.toggled.connect(self._set_config_expanded)
        header_layout.addWidget(self.expand_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.monitor_button = StateButton("开始监控", self.serial_header, checkable=True, role="danger")
        self.monitor_button.setFixedHeight(BUTTON_HEIGHT)
        self.monitor_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # 开始/停止监控：两种文字统一宽度，底部红色阴影绝不被父容器裁切
        set_button_width_for_texts(self.monitor_button, ("开始监控", "停止监控"))
        self.monitor_button.clicked.connect(self._toggle_monitor)
        header_layout.addWidget(self.monitor_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.config_layout.addWidget(self.serial_header, 0, Qt.AlignmentFlag.AlignTop)

        # --- 串口详情行（展开后显示）---
        self.serial_detail = QWidget(self.config_card)
        self.serial_detail.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        body_layout = QVBoxLayout(self.serial_detail)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(SECTION_ROW_GAP)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        row1.setSpacing(CONTROL_GAP_X)
        data_bits_label = QLabel("数据位")
        data_bits_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row1.addWidget(data_bits_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.data_bits_combo = self._create_combo(status_name="数据位", parent=self.serial_detail)
        for value in ("5", "6", "7", "8"):
            add_combo_item(self.data_bits_combo, value, int(value), f"数据位：{value}")
        self.data_bits_combo.setCurrentText("8")
        self.data_bits_combo.setFixedHeight(CONTROL_HEIGHT)
        row1.addWidget(self.data_bits_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        stop_bits_label = QLabel("停止位")
        stop_bits_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row1.addWidget(stop_bits_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.stop_bits_combo = self._create_combo(status_name="停止位", parent=self.serial_detail)
        for value in ("1", "1.5", "2"):
            add_combo_item(self.stop_bits_combo, value, float(value), f"停止位：{value}")
        self.stop_bits_combo.setCurrentText("1")
        self.stop_bits_combo.setFixedHeight(CONTROL_HEIGHT)
        row1.addWidget(self.stop_bits_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        filename_label = QLabel("文件名")
        filename_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row1.addWidget(filename_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.filename_edit = QLineEdit(
            f"serial_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}", self.serial_detail
        )
        self.filename_edit.setMinimumWidth(300)
        self.filename_edit.setFixedHeight(CONTROL_HEIGHT)
        row1.addWidget(self.filename_edit, 0, Qt.AlignmentFlag.AlignVCenter)
        hint = QLabel("(.dat 格式，超过 50MB 自动分割)", self.serial_detail)
        hint.setProperty("muted", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row1.addWidget(hint, 0, Qt.AlignmentFlag.AlignVCenter)
        row1.addStretch(1)
        body_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        row2.setSpacing(CONTROL_GAP_X)
        self.storage_button = StateButton("开始存储数据", self.serial_detail, checkable=True, role="danger")
        self.storage_button.setFixedHeight(BUTTON_HEIGHT)
        # 开始/停止存储：两种文字统一宽度 + 防裁切上下留白
        set_button_width_for_texts(self.storage_button, ("开始存储数据", "停止存储数据"))
        self.storage_button.clicked.connect(self._toggle_storage)
        row2.addWidget(self.storage_button, 0, Qt.AlignmentFlag.AlignVCenter)
        path_label = QLabel("路径")
        path_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row2.addWidget(path_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.storage_path_edit = QLineEdit(str(PROJECT_ROOT / "data"), self.serial_detail)
        self.storage_path_edit.setFixedHeight(CONTROL_HEIGHT)
        row2.addWidget(self.storage_path_edit, 1, Qt.AlignmentFlag.AlignVCenter)
        self.choose_folder_button = StateButton("选择", self.serial_detail)
        self.choose_folder_button.setFixedHeight(BUTTON_HEIGHT)
        self.choose_folder_button.clicked.connect(self._choose_folder)
        row2.addWidget(self.choose_folder_button, 0, Qt.AlignmentFlag.AlignVCenter)
        body_layout.addLayout(row2)

        self.config_layout.addWidget(self.serial_detail, 0, Qt.AlignmentFlag.AlignTop)
        self.serial_detail.hide()

        for widget in (self.port_combo, self.baud_combo, self.data_bits_combo, self.stop_bits_combo):
            if isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._on_serial_setting_changed)
        line_edit = self.baud_combo.lineEdit()
        if line_edit is not None:
            line_edit.editingFinished.connect(self._on_serial_setting_changed)

        self.root_layout.addWidget(self.config_card)

    def _build_workspace(self) -> None:
        self.workspace_card = CardFrame(self)
        workspace_layout = QVBoxLayout(self.workspace_card)
        # 卡片统一留白
        workspace_layout.setContentsMargins(
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
        )
        workspace_layout.setSpacing(SECTION_ROW_GAP)

        self._build_receive_toolbar(workspace_layout)

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal, self.workspace_card)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(CARD_GAP)

        self.receive_panel = OutlineFrame(self.workspace_splitter)
        receive_layout = QVBoxLayout(self.receive_panel)
        # 内部左右统一留白，上下留白 8 与 SECTION_PADDING_Y 保持一致
        receive_layout.setContentsMargins(
            SECTION_PADDING_Y,
            SECTION_PADDING_Y,
            SECTION_PADDING_Y,
            SECTION_PADDING_Y,
        )
        receive_layout.setSpacing(SECTION_ROW_GAP)
        # 实时数据使用 ZoomableDataView：Ctrl+滚轮调字号，默认与主界面同大小
        self.rx_edit = ZoomableDataView(
            self.receive_panel,
            font_family=MONO_FONT_FAMILY,
            font_size=RX_FONT_DEFAULT_SIZE,
        )
        self.rx_edit.setReadOnly(True)
        self.rx_edit.setPlaceholderText("等待接收数据…")
        # ZoomableDataView 默认使用 NoWrap；此处显式保证 HEX/ASCII 数据不自动换行
        self.rx_edit.setLineWrapMode(self.rx_edit.LineWrapMode.NoWrap)
        self.rx_edit.document().setMaximumBlockCount(5000)
        receive_layout.addWidget(self.rx_edit, 1)
        self.rx_scroll_controller = HoverScrollController(self.rx_edit)

        self.library_panel = OutlineFrame(self.workspace_splitter)
        self._build_library_panel(self.library_panel)

        self.workspace_splitter.addWidget(self.receive_panel)
        self.workspace_splitter.addWidget(self.library_panel)
        self.workspace_splitter.setStretchFactor(0, 7)
        self.workspace_splitter.setStretchFactor(1, 4)
        self.library_panel.hide()

        workspace_layout.addWidget(self.workspace_splitter, 1)
        self.root_layout.addWidget(self.workspace_card, 1)

    def _build_receive_toolbar(self, parent_layout: QVBoxLayout) -> None:
        bar = QWidget(self.workspace_card)
        bar.setMinimumHeight(CONTROL_ROW_MIN_HEIGHT)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        layout.setSpacing(CONTROL_GAP_X)

        title_label = QLabel("实时数据", bar)
        title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.parse_button = StateButton("协议解析模式", bar, checkable=True)
        self.parse_button.setFixedHeight(BUTTON_HEIGHT)
        set_button_width_for_texts(self.parse_button, ("协议解析模式", "协议解析模式"))
        self.parse_button.toggled.connect(self._set_parse_mode)
        layout.addWidget(self.parse_button, 0, Qt.AlignmentFlag.AlignVCenter)

        # 显示格式切换按钮：HEX / ASCII，放在协议解析和清空之间
        self.format_button = StateButton("HEX格式", bar, checkable=True)
        self.format_button.setChecked(True)
        self.format_button.setFixedHeight(BUTTON_HEIGHT)
        # 用公共方法：根据 HEX格式 / ASCII格式 两个文字统一固定宽度，绝不位移
        set_button_width_for_texts(self.format_button, ("HEX格式", "ASCII格式"))
        self.format_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.format_button.clicked.connect(self._toggle_display_format)
        layout.addWidget(self.format_button, 0, Qt.AlignmentFlag.AlignVCenter)

        clear_button = StateButton("清空", bar)
        clear_button.setFixedHeight(BUTTON_HEIGHT)
        clear_button.clicked.connect(self._clear_rx)
        layout.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.auto_scroll_button = StateButton("自动滚动", bar, checkable=True)
        self.auto_scroll_button.setChecked(True)
        self.auto_scroll_button.setFixedHeight(BUTTON_HEIGHT)
        self.auto_scroll_button.toggled.connect(self._toggle_auto_scroll)
        layout.addWidget(self.auto_scroll_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.packet_button = StateButton("分包显示", bar, checkable=True)
        self.packet_button.setFixedHeight(BUTTON_HEIGHT)
        self.packet_button.toggled.connect(self._toggle_packet_display)
        layout.addWidget(self.packet_button, 0, Qt.AlignmentFlag.AlignVCenter)

        timeout_label = QLabel("超时(ms)", bar)
        timeout_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(timeout_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.packet_timeout_spin = IntegerLineEdit(
            value=20,
            minimum=0,
            maximum=100000,
            parent=bar,
        )
        self.packet_timeout_spin.setFixedWidth(68)
        self.packet_timeout_spin.setFixedHeight(CONTROL_HEIGHT)
        self.packet_timeout_spin.valueChanged.connect(self._on_timeout_changed)
        layout.addWidget(self.packet_timeout_spin, 0, Qt.AlignmentFlag.AlignVCenter)

        self.protocol_controls = QWidget(bar)
        protocol_layout = QHBoxLayout(self.protocol_controls)
        protocol_layout.setContentsMargins(0, 0, 0, 0)
        protocol_layout.setSpacing(CONTROL_GAP_X)
        proto_label = QLabel("产品协议:")
        proto_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        protocol_layout.addWidget(proto_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.product_protocol_combo = self._create_combo(status_name="产品协议", parent=self.protocol_controls)
        self.product_protocol_combo.setMinimumWidth(150)
        self.product_protocol_combo.setFixedHeight(CONTROL_HEIGHT)
        protocol_layout.addWidget(self.product_protocol_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        import_button = StateButton("导入Word协议", self.protocol_controls)
        import_button.setFixedHeight(BUTTON_HEIGHT)
        import_button.clicked.connect(self._import_word_protocol)
        protocol_layout.addWidget(import_button, 0, Qt.AlignmentFlag.AlignVCenter)
        view_button = StateButton("查看协议", self.protocol_controls)
        view_button.setFixedHeight(BUTTON_HEIGHT)
        view_button.clicked.connect(self._view_current_protocol)
        protocol_layout.addWidget(view_button, 0, Qt.AlignmentFlag.AlignVCenter)
        module_button = StateButton("模组发送", self.protocol_controls)
        module_button.setFixedHeight(BUTTON_HEIGHT)
        module_button.clicked.connect(self._module_send)
        protocol_layout.addWidget(module_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.protocol_controls.hide()
        layout.addWidget(self.protocol_controls, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch(1)
        parent_layout.addWidget(bar)

    def _build_library_panel(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(
            SECTION_PADDING_Y,
            SECTION_PADDING_Y,
            SECTION_PADDING_Y,
            SECTION_PADDING_Y,
        )
        layout.setSpacing(SECTION_ROW_GAP)

        toolbar = QWidget(parent)
        toolbar.setMinimumHeight(CONTROL_ROW_MIN_HEIGHT)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        toolbar_layout.setSpacing(CONTROL_GAP_X)
        lib_label = QLabel("指令库", toolbar)
        lib_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        toolbar_layout.addWidget(lib_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # HEX / ASCII 分段切换：视觉上一个整体控件，选中段绿色，互斥
        self.cmdlib_mode_switch = SegmentToggle("HEX", "ASCII", toolbar)
        self.cmdlib_mode_switch.set_mode(self.cmdlib_mode, block_external=False)
        self.cmdlib_mode_switch.modeChanged.connect(self._cmdlib_set_mode)
        toolbar_layout.addWidget(self.cmdlib_mode_switch, 0, Qt.AlignmentFlag.AlignVCenter)

        self.cycle_button = StateButton("循环发送", toolbar, checkable=True)
        self.cycle_button.setFixedHeight(BUTTON_HEIGHT)
        # 开始循环 / 停止循环：统一宽度，避免切换时位移
        set_button_width_for_texts(self.cycle_button, ("循环发送", "停止循环"))
        self.cycle_button.toggled.connect(self._cmdlib_toggle_cycle)
        toolbar_layout.addWidget(self.cycle_button, 0, Qt.AlignmentFlag.AlignVCenter)

        configure_cycle = StateButton("配置循环", toolbar)
        configure_cycle.setFixedHeight(BUTTON_HEIGHT)
        configure_cycle.clicked.connect(self._cmdlib_open_cycle_config)
        toolbar_layout.addWidget(configure_cycle, 0, Qt.AlignmentFlag.AlignVCenter)

        clear_selected = StateButton("清空选中", toolbar)
        clear_selected.setFixedHeight(BUTTON_HEIGHT)
        clear_selected.clicked.connect(self._cmdlib_clear_selected)
        toolbar_layout.addWidget(clear_selected, 0, Qt.AlignmentFlag.AlignVCenter)

        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        self.command_table = CommandLibraryTable(parent)
        self.command_table.rowSelected.connect(self._cmdlib_select_index)
        self.command_table.rowCommitRequested.connect(self._cmdlib_commit_inline)
        self.command_table.sendRequested.connect(self._cmdlib_send_index)
        layout.addWidget(self.command_table, 1)

    def _build_send_area(self) -> None:
        self.send_card = CardFrame(self)
        # 发送区由内容自然决定高度，避免固定高度裁掉底部控件。
        self.send_card.setMinimumHeight(SEND_CARD_HEIGHT)
        self.send_card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        outer = QHBoxLayout(self.send_card)
        outer.setContentsMargins(
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
        )
        outer.setSpacing(SECTION_ROW_GAP)

        # Left: mode selector
        left = QWidget(self.send_card)
        left.setFixedWidth(140)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SECTION_ROW_GAP)
        mode_title = QLabel("指令发送模式", left)
        mode_title.setMinimumHeight(CONTROL_HEIGHT)
        mode_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        left_layout.addWidget(mode_title)
        self.protocol_mode_button = StateButton("协议模式", left, checkable=True)
        self.hex_mode_button = StateButton("HEX", left, checkable=True)
        self.ascii_mode_button = StateButton("ASCII", left, checkable=True)
        for button in (self.protocol_mode_button, self.hex_mode_button, self.ascii_mode_button):
            button.setFixedHeight(BUTTON_HEIGHT)
        send_mode_group = QButtonGroup(self)
        send_mode_group.setExclusive(True)
        for button in (self.protocol_mode_button, self.hex_mode_button, self.ascii_mode_button):
            send_mode_group.addButton(button)
            left_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.protocol_mode_button.clicked.connect(lambda: self._set_send_mode("protocol"))
        self.hex_mode_button.clicked.connect(lambda: self._set_send_mode("hex"))
        self.ascii_mode_button.clicked.connect(lambda: self._set_send_mode("ascii"))
        left_layout.addStretch(1)
        outer.addWidget(left)

        # Middle: stacked send editors.  Ignore the large default text-edit
        # sizeHint so the send card height is driven by the actual control rows.
        self.send_stack = QStackedWidget(self.send_card)
        self.send_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        self.send_stack.setMinimumHeight(0)
        self.protocol_page = self._build_protocol_send_page()
        self.hex_page, self.hex_send_edit = self._build_raw_send_page("HEX 数据:")
        self.ascii_page, self.ascii_send_edit = self._build_raw_send_page("ASCII 数据:")
        self.send_stack.addWidget(self.protocol_page)
        self.send_stack.addWidget(self.hex_page)
        self.send_stack.addWidget(self.ascii_page)
        outer.addWidget(self.send_stack, 1)

        # Right: send actions
        right = QWidget(self.send_card)
        right.setMinimumWidth(300)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(SECTION_ROW_GAP)
        send_title = QLabel("发送操作", right)
        send_title.setMinimumHeight(CONTROL_HEIGHT)
        send_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        right_layout.addWidget(send_title)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        row1.setSpacing(CONTROL_GAP_X)
        self.send_button = StateButton("发送", right)
        self.send_button.setFixedHeight(BUTTON_HEIGHT)
        self.send_button.clicked.connect(self._send_data)
        row1.addWidget(self.send_button, 0, Qt.AlignmentFlag.AlignVCenter)
        clear_button = StateButton("清空输入", right)
        clear_button.setFixedHeight(BUTTON_HEIGHT)
        clear_button.clicked.connect(self._clear_input)
        row1.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.crlf_button = StateButton("加回车换行", right, checkable=True)
        self.crlf_button.setFixedHeight(BUTTON_HEIGHT)
        self.crlf_button.toggled.connect(self._toggle_append_crlf)
        row1.addWidget(self.crlf_button, 0, Qt.AlignmentFlag.AlignVCenter)
        right_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        row2.setSpacing(CONTROL_GAP_X)
        self.checksum_button = StateButton("自动追加校验位", right, checkable=True)
        self.checksum_button.setFixedHeight(BUTTON_HEIGHT)
        self.checksum_button.toggled.connect(self._toggle_auto_checksum)
        row2.addWidget(self.checksum_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.checksum_combo = self._create_combo(status_name="校验类型", parent=right)
        checksum_values = ["ADD8", "XOR8", "CRC8", "CRC16", "CRC16_CCITT", "CRC32"]
        for value in checksum_values:
            add_combo_item(self.checksum_combo, value, value, f"校验类型：{value}")
        self.checksum_combo.setFixedHeight(CONTROL_HEIGHT)
        row2.addWidget(self.checksum_combo, 1, Qt.AlignmentFlag.AlignVCenter)
        right_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        row3.setSpacing(CONTROL_GAP_X)
        self.auto_send_button = StateButton("自动发送", right, checkable=True)
        self.auto_send_button.setFixedHeight(BUTTON_HEIGHT)
        # 自动发送 / 停止发送：两种文字统一宽度
        set_button_width_for_texts(self.auto_send_button, ("自动发送", "停止发送"))
        self.auto_send_button.toggled.connect(self._toggle_auto_send)
        row3.addWidget(self.auto_send_button, 0, Qt.AlignmentFlag.AlignVCenter)
        interval_label = QLabel("间隔(ms)", right)
        interval_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row3.addWidget(interval_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.auto_send_interval = IntegerLineEdit(
            value=1000,
            minimum=0,
            maximum=100000,
            parent=right,
        )
        self.auto_send_interval.setFixedWidth(90)
        self.auto_send_interval.setFixedHeight(CONTROL_HEIGHT)
        self.auto_send_interval.valueChanged.connect(self._on_interval_changed)
        row3.addWidget(self.auto_send_interval, 0, Qt.AlignmentFlag.AlignVCenter)
        row3.addStretch(1)
        right_layout.addLayout(row3)
        right_layout.addStretch(1)
        outer.addWidget(right)

        self.send_card.hide()
        self.root_layout.addWidget(self.send_card)

    def _build_protocol_send_page(self) -> QWidget:
        page = QWidget(self.send_card)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SECTION_ROW_GAP)

        params = QWidget(page)
        params.setMinimumWidth(280)
        form = QFormLayout(params)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(CONTROL_GAP_X)
        form.setVerticalSpacing(SECTION_ROW_GAP)
        title = QLabel("协议参数", params)
        title.setProperty("title", True)
        title.setMinimumHeight(CONTROL_HEIGHT)
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        form.addRow(title)
        self.command_combo = self._create_combo(status_name="协议命令", parent=params)
        self.command_combo.setFixedHeight(CONTROL_HEIGHT)
        self.command_combo.currentTextChanged.connect(self._on_send_command_selected)
        form.addRow("命令:", self.command_combo)
        self.quick_action_combo = self._create_combo(status_name="快捷动作", parent=params)
        self.quick_action_combo.setFixedHeight(CONTROL_HEIGHT)
        self.quick_action_combo.currentTextChanged.connect(self._on_quick_action_selected)
        form.addRow("快捷动作:", self.quick_action_combo)
        self.direction_combo = self._create_combo(status_name="方向", parent=params)
        direction_values = ["模组发送", "主机发送"]
        for value in direction_values:
            add_combo_item(self.direction_combo, value, value, f"方向：{value}")
        self.direction_combo.setFixedHeight(CONTROL_HEIGHT)
        self.direction_combo.currentTextChanged.connect(self._on_send_direction_selected)
        form.addRow("方向:", self.direction_combo)
        layout.addWidget(params)

        attr_box = QWidget(page)
        attr_layout = QVBoxLayout(attr_box)
        attr_layout.setContentsMargins(0, 0, 0, 0)
        attr_layout.setSpacing(SECTION_ROW_GAP)
        attr_title = QLabel("协议属性:", attr_box)
        attr_title.setMinimumHeight(CONTROL_HEIGHT)
        attr_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        attr_layout.addWidget(attr_title)
        self.attr_table = QTableWidget(0, 3, attr_box)
        self.attr_table.setHorizontalHeaderLabels(["参数名称", "当前值", "说明/解析"])
        self.attr_table.verticalHeader().hide()
        self.attr_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.attr_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.attr_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.attr_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        attr_layout.addWidget(self.attr_table, 1)
        layout.addWidget(attr_box, 1)

        json_box = QWidget(page)
        json_layout = QVBoxLayout(json_box)
        json_layout.setContentsMargins(0, 0, 0, 0)
        json_layout.setSpacing(SECTION_ROW_GAP)
        json_title = QLabel("字段 JSON:", json_box)
        json_title.setMinimumHeight(CONTROL_HEIGHT)
        json_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        json_layout.addWidget(json_title)
        # 协议 JSON 编辑框同样使用 ZoomableDataView（只读关闭，字号与主界面一致，等宽字体）
        self.protocol_json_edit = ZoomableDataView(
            json_box,
            font_family=MONO_FONT_FAMILY,
            font_size=RX_FONT_DEFAULT_SIZE,
        )
        self.protocol_json_edit.setPlainText(self._send_buffers["protocol"])
        self.protocol_json_scroll = HoverScrollController(self.protocol_json_edit)
        json_layout.addWidget(self.protocol_json_edit, 1)
        layout.addWidget(json_box, 1)
        return page

    def _build_raw_send_page(self, title_text: str) -> tuple[QWidget, ZoomableDataView]:
        page = QWidget(self.send_card)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SECTION_ROW_GAP)
        title_label = QLabel(title_text, page)
        title_label.setMinimumHeight(CONTROL_HEIGHT)
        title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title_label)
        # HEX / ASCII 发送编辑框：ZoomableDataView，默认不换行，等宽字体
        edit = ZoomableDataView(
            page,
            font_family=MONO_FONT_FAMILY,
            font_size=RX_FONT_DEFAULT_SIZE,
        )
        edit.setLineWrapMode(edit.LineWrapMode.NoWrap)
        HoverScrollController(edit)
        layout.addWidget(edit, 1)
        return page, edit

    def _build_statusbar(self) -> None:
        self.status_card = CardFrame(self)
        self.status_card.setFixedHeight(STATUS_HEIGHT)
        layout = QHBoxLayout(self.status_card)
        # 状态栏：左右 SECTION_PADDING_X，上下 SECTION_PADDING_Y
        layout.setContentsMargins(
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
            SECTION_PADDING_X,
            SECTION_PADDING_Y,
        )
        layout.setSpacing(CONTROL_GAP_X)
        for label_widget in (
            self._make_status_label("●", self.status_card, style="color:#16A34A;"),
            self._make_status_label("未连接", self.status_card, attr="status_port"),
            self._make_status_label(self.initial_baud, self.status_card, attr="status_baud"),
            self._make_status_label("未存储", self.status_card, attr="status_storage"),
            self._make_status_label("已隐藏指令库 · HEX", self.status_card, attr="status_library"),
        ):
            layout.addWidget(label_widget, 0, Qt.AlignmentFlag.AlignVCenter)

        # 下拉选项悬停预览：吸收中间剩余宽度，不挤占右侧 RX/TX/错误/缓冲
        self.combo_hover_status = QLabel("", self.status_card)
        self.combo_hover_status.setObjectName("ComboHoverStatus")
        self.combo_hover_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.combo_hover_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.combo_hover_status.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(CONTROL_GAP_X * 2)
        layout.addWidget(self.combo_hover_status, 1)

        for text in ("RX 0", "TX 0", "错误 0", "缓冲 0B"):
            attr = {
                "RX 0": "status_rx",
                "TX 0": "status_tx",
                "错误 0": "status_err",
                "缓冲 0B": "status_buf",
            }[text]
            layout.addWidget(
                self._make_status_label(text, self.status_card, attr=attr),
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
        self.root_layout.addWidget(self.status_card)

    def _make_status_label(self, text: str, parent: QWidget, *, style: str = "", attr: str = "") -> QLabel:
        label = QLabel(str(text), parent)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if style:
            label.setStyleSheet(style)
        if attr:
            setattr(self, attr, label)
        return label

    # ------------------------------------------------------------------
    # 开发期 UI 自检：所有按钮/阴影是否被父容器裁切
    # ------------------------------------------------------------------
    def _audit_button_geometry(self) -> None:
        """Development-only size audit after the window is fully laid out."""
        if not DEBUG_UI_AUDIT:
            return

        from PySide6.QtWidgets import QPushButton

        tolerance = 2
        for button in self.findChildren(QPushButton):
            if not button.isVisibleTo(self):
                continue
            if button.width() <= 0 or button.height() <= 0:
                continue

            required = button.sizeHint()
            if required.width() <= 0 or required.height() <= 0:
                continue

            problems: list[str] = []
            if button.width() + tolerance < required.width():
                problems.append(f"宽度不足 {button.width()} < {required.width()}")
            if button.height() + tolerance < required.height():
                problems.append(f"高度不足 {button.height()} < {required.height()}")

            if problems:
                print(
                    "[UI按钮尺寸检查]",
                    button.objectName() or button.text(),
                    "；".join(problems),
                )

    # ------------------------------------------------------------------
    # Initial state / visibility
    # ------------------------------------------------------------------

    def _load_initial_state(self) -> None:
        self._refresh_ports()
        self._load_protocols()
        self._cmdlib_refresh_table()
        self._set_send_mode("protocol")
        self._set_parse_mode(False)
        self._set_library_visible(False)
        self._set_send_visible(False)
        self._set_config_expanded(False)

    def _load_protocols(self) -> None:
        names = self.protocol_manager.available_protocols()
        self.product_protocol_combo.clear()
        for name in names:
            add_combo_item(self.product_protocol_combo, name, name, f"产品协议：{name}")
        self.product_protocol_combo.currentTextChanged.connect(self._on_protocol_selected)
        if "串口3.0协议" in names:
            self.product_protocol_combo.setCurrentText("串口3.0协议")
        elif names:
            self.product_protocol_combo.setCurrentIndex(0)
        if self.product_protocol_combo.currentText():
            self._on_protocol_selected(self.product_protocol_combo.currentText())

    def _set_library_visible(self, visible: bool) -> None:
        self.library_visible = bool(visible)
        if self.library_visible:
            self.library_panel.show()
            sizes = self.workspace_splitter.sizes()
            total = sum(sizes) or self.workspace_splitter.width()
            self.workspace_splitter.setSizes([max(1, int(total * 0.66)), max(1, int(total * 0.34))])
        else:
            self.library_panel.hide()
        with signals_blocked(self.nav_library_button):
            self.nav_library_button.setChecked(self.library_visible)
        self.status_library.setText(
            f"{'已显示' if self.library_visible else '已隐藏'}指令库 · {self.cmdlib_mode.upper()}"
        )

    def _set_send_visible(self, visible: bool) -> None:
        self.send_visible = bool(visible)
        self.send_card.setVisible(self.send_visible)
        with signals_blocked(self.nav_send_button):
            self.nav_send_button.setChecked(self.send_visible)

    def _set_config_expanded(self, expanded: bool) -> None:
        self.config_expanded = bool(expanded)
        self.serial_detail.setVisible(self.config_expanded)
        self.expand_button.setText("收起 ▲" if self.config_expanded else "展开 ▼")
        with signals_blocked(self.expand_button):
            self.expand_button.setChecked(self.config_expanded)

        # 通知布局重新计算高度，但不移动窗口或重建控件
        self.config_layout.invalidate()
        self.config_card.updateGeometry()
        root = self.centralWidget()
        if root is not None:
            central_layout = root.layout()
            if central_layout is not None:
                central_layout.invalidate()

    def _set_parse_mode(self, enabled: bool) -> None:
        self.parse_mode = bool(enabled)
        self.protocol_controls.setVisible(self.parse_mode)
        with signals_blocked(self.parse_button):
            self.parse_button.setChecked(self.parse_mode)
        self._rerender_rx_history()

    # ------------------------------------------------------------------
    # Serial configuration / monitoring
    # ------------------------------------------------------------------

    def _scan_ports(self):
        """扫描串口并返回带完整属性的列表。

        每个元素是 dict，至少含 device / display_name / description /
        manufacturer / hwid。用于下拉框悬停时状态栏展示完整名称。
        """
        try:
            items = self.worker.scan_ports()
        except Exception:
            items = []
        self.port_display_map = {item["display_name"]: item["device"] for item in items}
        if not items:
            self.port_display_map = {"未检测到串口": ""}
            return [{"display_name": "未检测到串口", "device": "", "manufacturer": "", "hwid": ""}]
        return list(items)

    @staticmethod
    def _extract_vid_pid(hwid: str) -> tuple[str, str]:
        """从 hwid 中提取 VID/PID（典型: 'USB VID:PID=1A86:7523'）。"""
        vid = pid = ""
        match = re.search(
            r"VID[_\s]*:[_\s]*PID[_\s]*=*\s*([0-9A-Fa-f]+)[\s:：]+([0-9A-Fa-f]+)",
            str(hwid or ""),
        )
        if match:
            vid, pid = match.group(1), match.group(2)
        else:
            import re as _re_local  # noqa: WPS433 - fallback regex

            m2 = _re_local.search(r"VID_([0-9A-Fa-f]+).*?PID_([0-9A-Fa-f]+)", str(hwid or ""), flags=_re_local.IGNORECASE)
            if m2:
                vid, pid = m2.group(1), m2.group(2)
        return vid, pid

    def _build_port_full_text(self, item: dict) -> str:
        display_name = str(item.get("display_name") or "").strip()
        manufacturer = str(item.get("manufacturer") or "").strip()
        vid, pid = self._extract_vid_pid(str(item.get("hwid") or ""))

        parts = [p for p in [display_name, manufacturer, f"VID:{vid}" if vid else "", f"PID:{pid}" if pid else ""] if p]
        return " - ".join(parts)

    def _refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        items = self._scan_ports()
        with signals_blocked(self.port_combo):
            self.port_combo.clear()
            for item in items:
                display_name = str(item.get("display_name") or "").strip()
                device = str(item.get("device") or "").strip()
                full_text = self._build_port_full_text(item)
                add_combo_item(self.port_combo, display_name, device, full_text)

            target = None
            if self.initial_port:
                target = next(
                    (
                        name
                        for name, device in self.port_display_map.items()
                        if device == self.initial_port
                    ),
                    None,
                )
            display_values = list(self.port_display_map.keys())
            if target:
                self.port_combo.setCurrentText(target)
            elif current in display_values:
                self.port_combo.setCurrentText(current)
            elif display_values:
                self.port_combo.setCurrentIndex(0)

    def _get_serial_config_from_ui(self) -> dict[str, Any]:
        display = self.port_combo.currentText().strip()
        port = self.port_display_map.get(display, "")
        if not port:
            raise ValueError("请选择有效串口")
        baud_text = self.baud_combo.currentText().strip()
        if not baud_text.isdigit() or int(baud_text) <= 0:
            raise ValueError("请输入有效波特率")
        return {
            "port": port,
            "display": display,
            "baudrate": int(baud_text),
            "data_bits": int(self.data_bits_combo.currentText()),
            "stop_bits": float(self.stop_bits_combo.currentText()),
        }

    def _on_serial_setting_changed(self, *_args: object) -> None:
        if self.monitoring and not self.monitor_starting:
            self.reconfigure_timer.start()

    def _toggle_monitor(self) -> None:
        if self.monitoring or self.monitor_starting:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self) -> None:
        try:
            config = self._get_serial_config_from_ui()
        except Exception as error:
            QMessageBox.warning(self, "串口配置", str(error))
            with signals_blocked(self.monitor_button):
                self.monitor_button.setChecked(False)
            return

        self.monitor_starting = True
        self.monitor_button.setEnabled(False)
        self.monitor_button.setText("连接中…")

        def job() -> None:
            try:
                self.worker.connect(
                    config["port"],
                    config["baudrate"],
                    config["data_bits"],
                    config["stop_bits"],
                )
                self.active_serial_config = config
                self.bridge.monitorResult.emit(True, "")
            except Exception as error:
                self.bridge.monitorResult.emit(False, str(error))

        threading.Thread(target=job, daemon=True, name="qt-serial-connect").start()

    def _on_monitor_result(self, success: bool, message: str) -> None:
        self.monitor_starting = False
        self.monitor_button.setEnabled(True)
        self.monitoring = bool(success)
        with signals_blocked(self.monitor_button):
            self.monitor_button.setChecked(self.monitoring)
        self.monitor_button.setText("停止监控" if self.monitoring else "开始监控")
        if success and self.active_serial_config:
            self.status_port.setText(self.active_serial_config["port"])
            self.status_baud.setText(str(self.active_serial_config["baudrate"]))
        elif not success:
            self.status_port.setText("未连接")
            if message:
                QMessageBox.warning(self, "串口连接失败", message)

    def _stop_monitoring(self) -> None:
        self.reconfigure_timer.stop()
        self.worker.disconnect(wait=False)
        self.monitoring = False
        self.monitor_starting = False
        self.serial_reconfiguring = False
        self.active_serial_config = None
        with signals_blocked(self.monitor_button):
            self.monitor_button.setChecked(False)
        self.monitor_button.setEnabled(True)
        self.monitor_button.setText("开始监控")
        self.status_port.setText("未连接")

    def _begin_live_serial_reconfigure(self) -> None:
        if not self.monitoring or self.serial_reconfiguring:
            return
        try:
            config = self._get_serial_config_from_ui()
        except Exception as error:
            QMessageBox.warning(self, "串口配置", str(error))
            return
        if config == self.active_serial_config:
            return
        self.serial_reconfiguring = True
        self.monitor_button.setEnabled(False)
        self.monitor_button.setText("重连中…")

        def job() -> None:
            try:
                self.worker.reconnect(
                    config["port"],
                    config["baudrate"],
                    config["data_bits"],
                    config["stop_bits"],
                )
                self.active_serial_config = config
                self.bridge.reconnectResult.emit(True, "")
            except Exception as error:
                self.bridge.reconnectResult.emit(False, str(error))

        threading.Thread(target=job, daemon=True, name="qt-serial-reconnect").start()

    def _on_reconnect_result(self, success: bool, message: str) -> None:
        self.serial_reconfiguring = False
        self.monitor_button.setEnabled(True)
        self.monitor_button.setText("停止监控" if success else "开始监控")
        self.monitoring = bool(success)
        with signals_blocked(self.monitor_button):
            self.monitor_button.setChecked(self.monitoring)
        if success and self.active_serial_config:
            self.status_port.setText(self.active_serial_config["port"])
            self.status_baud.setText(str(self.active_serial_config["baudrate"]))
        else:
            self.status_port.setText("未连接")
            if message:
                QMessageBox.warning(self, "串口重连失败", message)

    def _handle_serial_error(self, message: str) -> None:
        self.error_count += 1
        self.status_err.setText(f"错误 {self.error_count}")
        self._stop_monitoring()
        QMessageBox.warning(self, "串口错误", message)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _toggle_storage(self) -> None:
        if self.raw_saver.active:
            self.raw_saver.stop(flush=True)
            self.storage_button.setText("开始存储数据")
            with signals_blocked(self.storage_button):
                self.storage_button.setChecked(False)
            self.status_storage.setText("未存储")
            return
        try:
            self.raw_saver.start(
                directory=self.storage_path_edit.text().strip(),
                base_name=self.filename_edit.text().strip(),
                display_mode=self.display_mode,
                split_mb=50,
            )
        except Exception as error:
            with signals_blocked(self.storage_button):
                self.storage_button.setChecked(False)
            QMessageBox.warning(self, "存储失败", str(error))
            return
        self.storage_button.setText("停止存储数据")
        with signals_blocked(self.storage_button):
            self.storage_button.setChecked(True)
        self.status_storage.setText("存储中")

    def _choose_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择存储目录",
            self.storage_path_edit.text().strip() or str(PROJECT_ROOT),
        )
        if directory:
            self.storage_path_edit.setText(directory)

    def _show_storage_error(self, message: str) -> None:
        QMessageBox.warning(self, "存储错误", message)

    # ------------------------------------------------------------------
    # Receive / render / protocol parsing
    # ------------------------------------------------------------------

    def _on_serial_data(self, data: bytes, received_at: float | None = None) -> None:
        if not (self.monitoring or self.monitor_starting) or self.serial_reconfiguring:
            return
        raw = bytes(data)
        timestamp = received_at if received_at is not None else time.time()
        if self.raw_saver.active:
            self.raw_saver.enqueue_rx(raw, timestamp)
        record = {"timestamp": timestamp, "direction": "RX", "data": raw}
        try:
            self.rx_ui_queue.put_nowait(record)
        except queue.Full:
            self.rx_ui_dropped += 1

    def _drain_rx_ui_queue(self) -> None:
        records: list[dict[str, Any]] = []
        total_bytes = 0
        while len(records) < self.rx_ui_batch_records and total_bytes < self.rx_ui_batch_bytes:
            try:
                record = self.rx_ui_queue.get_nowait()
            except queue.Empty:
                break
            records.append(record)
            total_bytes += len(record["data"])

        if not records:
            self.status_buf.setText(f"缓冲 {self.rx_ui_queue.qsize()}B")
            return

        text_parts: list[str] = []
        for record in records:
            self.rx_history.append(record)
            direction = record.get("direction", "RX")
            if self.parse_mode and direction == "RX":
                self._process_protocol_data(record["data"], record["timestamp"], text_parts)
            elif self.packet_display_enabled and direction == "RX":
                self._feed_display_packet(record["data"], record["timestamp"])
            else:
                text_parts.append(self._format_rx_record(record))

        if text_parts:
            self._append_lines(text_parts)

        self.rx_count += sum(len(r["data"]) for r in records if r.get("direction", "RX") == "RX")
        self.tx_count += sum(1 for r in records if r.get("direction", "RX") == "TX")
        self.status_rx.setText(f"RX {self.rx_count}")
        self.status_tx.setText(f"TX {self.tx_count}")
        self.status_buf.setText(f"缓冲 {self.rx_ui_queue.qsize()}B")

    def _append_lines(self, lines: list[str]) -> None:
        if not lines:
            return
        cursor = self.rx_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\n".join(lines) + "\n")
        if self.auto_scroll:
            self.rx_edit.moveCursor(QTextCursor.MoveOperation.End)
        QTimer.singleShot(0, self.rx_scroll_controller.refresh)

    def _format_timestamp(self, timestamp: float) -> str:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}"

    def _format_ascii_data(self, data: bytes) -> str:
        parts: list[str] = []
        for value in data:
            if value == 13:
                parts.append("\\r")
            elif value == 10:
                parts.append("\\n")
            elif value == 9:
                parts.append("\\t")
            elif 32 <= value <= 126:
                parts.append(chr(value))
            else:
                parts.append(f"\\x{value:02X}")
        return "".join(parts)

    def _format_rx_record(self, record: dict[str, Any]) -> str:
        data = bytes(record["data"])
        content = data.hex(" ").upper() if self.display_mode == "hex" else self._format_ascii_data(data)
        return f"[{self._format_timestamp(record['timestamp'])}] {record.get('direction', 'RX')}  {content}"

    def _toggle_display_format(self) -> None:
        self.display_mode = "ascii" if self.display_mode == "hex" else "hex"
        self.format_button.setText("ASCII格式" if self.display_mode == "ascii" else "HEX格式")
        with signals_blocked(self.format_button):
            self.format_button.setChecked(self.display_mode == "hex")
        self._rerender_rx_history()

    def _rerender_rx_history(self) -> None:
        self.rx_edit.clear()
        lines: list[str] = []
        if self.parse_mode:
            # Historical protocol reparse is intentionally conservative: raw history is shown
            # until new complete frames arrive, avoiding stateful synchronizer duplication.
            lines = [self._format_rx_record(record) for record in self.rx_history]
        else:
            lines = [self._format_rx_record(record) for record in self.rx_history]
        self._append_lines(lines)

    def _clear_rx(self) -> None:
        self.rx_history.clear()
        self.rx_edit.clear()
        self.rx_scroll_controller.reset()
        self._display_packet_buffer.clear()
        self._display_packet_first_ts = None
        self.packet_timer.stop()

    def _toggle_auto_scroll(self, enabled: bool) -> None:
        self.auto_scroll = bool(enabled)

    def _toggle_packet_display(self, enabled: bool) -> None:
        self.packet_display_enabled = bool(enabled)
        if not enabled:
            self._flush_display_packet()

    def _feed_display_packet(self, data: bytes, timestamp: float) -> None:
        if self._display_packet_first_ts is None:
            self._display_packet_first_ts = timestamp
        self._display_packet_buffer.extend(data)
        self.packet_timeout_ms = int(self.packet_timeout_spin.value())
        self.packet_timer.start(self.packet_timeout_ms)

    def _flush_display_packet(self) -> None:
        if not self._display_packet_buffer:
            return
        record = {
            "timestamp": self._display_packet_first_ts or time.time(),
            "direction": "RX",
            "data": bytes(self._display_packet_buffer),
        }
        self._display_packet_buffer.clear()
        self._display_packet_first_ts = None
        self._append_lines([self._format_rx_record(record)])

    def _process_protocol_data(self, data: bytes, timestamp: float, output: list[str]) -> None:
        if self.frame_synchronizer is None:
            output.append(f"[{self._format_timestamp(timestamp)}] RX  协议同步器未初始化")
            return
        try:
            frames = self.frame_synchronizer.feed(data)
            for frame in frames:
                try:
                    result = self.protocol_manager.parse_frame(frame.raw)
                    checksum = "✓" if result.checksum_ok else "✗"
                    output.append(
                        f"[{self._format_timestamp(timestamp)}] RX  {result.cmd_name}  "
                        f"CMD=0x{result.cmd:02X}  Checksum={checksum}"
                    )
                    if self.result_logger:
                        try:
                            self.result_logger.log(result, timestamp)
                        except Exception:
                            pass
                except ProtocolError as error:
                    friendly, _debug = classify_protocol_error(error)
                    output.append(
                        f"[{self._format_timestamp(timestamp)}] RX  ERR {friendly} raw={to_hex(frame.raw)}"
                    )
        except Exception as error:
            output.append(f"[{self._format_timestamp(timestamp)}] RX  解析异常: {error}")

    def _on_tx_sent(self, data: bytes, sent_at: float | None = None) -> None:
        timestamp = sent_at if sent_at is not None else time.time()
        raw = bytes(data)
        if self.raw_saver.active:
            self.raw_saver.enqueue_tx(raw, timestamp)
        try:
            self.rx_ui_queue.put_nowait({"timestamp": timestamp, "direction": "TX", "data": raw})
        except queue.Full:
            self.rx_ui_dropped += 1

    # ------------------------------------------------------------------
    # Protocol selection / viewing / Word import
    # ------------------------------------------------------------------

    def _on_protocol_selected(self, name: str) -> None:
        if not name:
            return
        try:
            self.protocol_manager.select(name)
            self.frame_synchronizer = self.protocol_manager.create_synchronizer()
            self._refresh_send_protocol_ui()
        except Exception as error:
            QMessageBox.warning(self, "协议加载失败", str(error))

    def _import_word_protocol(self) -> None:
        try:
            from protocol_parser.docx_importer import ImporterError, check_docx_available, import_and_save
        except ImportError:
            QMessageBox.critical(self, "错误", "Word 导入模块未安装")
            return
        if not check_docx_available():
            QMessageBox.critical(self, "错误", "请先安装 python-docx")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 Word 协议文档", str(PROJECT_ROOT), "Word 文档 (*.docx);;所有文件 (*)"
        )
        if not file_path:
            return
        try:
            protocols_dir = DATA_DIR / "protocols" / "imported"
            protocols_dir.mkdir(parents=True, exist_ok=True)
            cfg, saved_path = import_and_save(file_path, protocols_dir)
            display_name = cfg.get("product", Path(file_path).name)
            self.protocol_manager.add_user_protocol(display_name, cfg)
            with signals_blocked(self.product_protocol_combo):
                self.product_protocol_combo.clear()
                for name in self.protocol_manager.available_protocols():
                    add_combo_item(self.product_protocol_combo, name, name, f"产品协议：{name}")
                self.product_protocol_combo.setCurrentText(display_name)
            self._on_protocol_selected(display_name)
            QMessageBox.information(self, "成功", f"协议已导入：{display_name}\n保存到：{saved_path}")
        except ImporterError as error:
            QMessageBox.critical(self, "导入失败", str(error))
        except Exception as error:
            QMessageBox.critical(self, "导入失败", f"解析 Word 文档时出错：{error}")

    def _view_current_protocol(self) -> None:
        cfg = self.protocol_manager.current_config()
        if cfg is None:
            QMessageBox.information(self, "提示", "未选择协议")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"协议详情 - {self.protocol_manager.current_name()}")
        dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(SECTION_PADDING_X, SECTION_PADDING_Y, SECTION_PADDING_X, SECTION_PADDING_Y)
        layout.setSpacing(SECTION_ROW_GAP)
        label = QLabel(f"协议名称：{self.protocol_manager.current_name()}", dialog)
        label.setProperty("title", True)
        label.setMinimumHeight(CONTROL_HEIGHT)
        layout.addWidget(label)
        # 查看协议对话框中的文本也使用 ZoomableDataView，统一字号默认与主界面一致
        text = ZoomableDataView(
            dialog,
            font_family=MONO_FONT_FAMILY,
            font_size=RX_FONT_DEFAULT_SIZE,
        )
        text.setReadOnly(True)
        text.setPlainText(json.dumps(cfg, ensure_ascii=False, indent=2))
        HoverScrollController(text)
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _module_send(self) -> None:
        self._set_send_visible(True)
        self._set_send_mode("protocol")
        self.direction_combo.setCurrentText("模组发送")

    # ------------------------------------------------------------------
    # Send editor / sending
    # ------------------------------------------------------------------

    def _set_send_mode(self, mode: str) -> None:
        if mode not in {"protocol", "hex", "ascii"}:
            return
        if hasattr(self, "protocol_json_edit"):
            self._send_buffers[self.send_mode] = self._current_send_text()
        self.send_mode = mode
        index = {"protocol": 0, "hex": 1, "ascii": 2}[mode]
        self.send_stack.setCurrentIndex(index)
        buttons = {
            "protocol": self.protocol_mode_button,
            "hex": self.hex_mode_button,
            "ascii": self.ascii_mode_button,
        }
        for key, button in buttons.items():
            with signals_blocked(button):
                button.setChecked(key == mode)
        self._replace_send_text(self._send_buffers.get(mode, ""), mode)
        if mode == "protocol":
            self._refresh_send_protocol_ui()

    def _get_send_edit(self, mode: str | None = None) -> QPlainTextEdit:
        target = mode or self.send_mode
        return {
            "protocol": self.protocol_json_edit,
            "hex": self.hex_send_edit,
            "ascii": self.ascii_send_edit,
        }[target]

    def _current_send_text(self, mode: str | None = None) -> str:
        return self._get_send_edit(mode).toPlainText()

    def _replace_send_text(self, text: str, mode: str | None = None) -> None:
        edit = self._get_send_edit(mode)
        with signals_blocked(edit):
            edit.setPlainText(text)

    def _clear_input(self) -> None:
        self._replace_send_text("")
        self._send_buffers[self.send_mode] = ""

    def _default_fields_for_command(self, command_code: int) -> dict[str, Any]:
        cfg = self.protocol_manager.current_config() or {}
        direction = normalize_direction(self.direction_combo.currentText())
        fmt = "raw"
        for command in cfg.get("commands", []) or []:
            try:
                code = int(str(command.get("cmd_code", "0")), 0)
            except (TypeError, ValueError):
                continue
            if code == command_code:
                branch = command.get(direction) or command.get("request") or {}
                fmt = str(branch.get("format", "raw")).lower()
                break
        if fmt in {"module_status", "heartbeat_resp", "errcode", "net_config_type"}:
            return {"value": 1}
        if fmt == "msg_id":
            return {"msg_id": 0}
        if fmt in {"msg_id_then_attr", "msg_id_then_attr_unit"}:
            return {"msg_id": 0, "attrs": []}
        if fmt in {"attr_list", "errcode_then_attr"}:
            return {"attrs": []}
        if fmt == "attr_unit":
            return {"attrids": []}
        if fmt in {"raw", ""}:
            return {"raw": ""}
        return {}

    def _refresh_send_protocol_ui(self) -> None:
        cfg = self.protocol_manager.current_config() or {}
        labels: list[str] = []
        self._send_cmd_map = {}
        for command in cfg.get("commands", []) or []:
            if not isinstance(command, dict):
                continue
            raw_code = command.get("cmd_code", command.get("code"))
            try:
                code = raw_code if isinstance(raw_code, int) else int(str(raw_code), 0)
            except (TypeError, ValueError):
                continue
            name = str(command.get("name", "")).strip()
            label = f"0x{code & 0xFF:02X} {name}".strip()
            labels.append(label)
            self._send_cmd_map[label] = code & 0xFF

        with signals_blocked(self.command_combo):
            current = self.command_combo.currentText()
            self.command_combo.clear()
            for label in (labels or ["未配置命令"]):
                add_combo_item(self.command_combo, label, label, f"协议命令：{label}")
            if current in labels:
                self.command_combo.setCurrentText(current)
        self._refresh_quick_actions()
        self._render_protocol_attributes()
        self._on_send_command_selected(self.command_combo.currentText())

    def _on_send_direction_selected(self, _value: str = "") -> None:
        if self.send_mode == "protocol":
            self._on_send_command_selected(self.command_combo.currentText())

    def _on_send_command_selected(self, value: str) -> None:
        if self.send_mode != "protocol" or not value:
            return
        code = self._send_cmd_map.get(value)
        if code is None:
            try:
                code = extract_command_code(value)
            except ValueError:
                return
        text = json.dumps(self._default_fields_for_command(code), ensure_ascii=False, indent=2)
        self._send_buffers["protocol"] = text
        self._replace_send_text(text, "protocol")

    def _render_protocol_attributes(self) -> None:
        attrs = (self.protocol_manager.current_config() or {}).get("attributes") or {}
        rows: list[tuple[str, str, str]] = []
        if isinstance(attrs, dict):
            for attr_id, meta in attrs.items():
                if str(attr_id).startswith("__"):
                    continue
                meta = meta if isinstance(meta, dict) else {}
                name = meta.get("cn_name") or meta.get("name") or str(attr_id)
                value = meta.get("value", meta.get("default", ""))
                desc = meta.get("desc") or meta.get("description") or meta.get("unit") or ""
                rows.append((str(name), str(value), str(desc)))
        self.attr_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.attr_table.setItem(row, column, item)

    def _refresh_quick_actions(self) -> None:
        attrs = (self.protocol_manager.current_config() or {}).get("attributes") or {}
        labels = ["无"]
        self._quick_action_map = {}
        if isinstance(attrs, dict):
            for attr_id, meta in attrs.items():
                if str(attr_id).startswith("__") or not isinstance(meta, dict):
                    continue
                name = meta.get("cn_name") or meta.get("name") or str(attr_id)
                type_id = meta.get("typeid", 0)
                enum_map = meta.get("enum") or {}
                candidates = []
                if isinstance(enum_map, dict) and enum_map:
                    candidates = list(enum_map.items())
                else:
                    candidates = [(0, "关闭"), (1, "打开")]
                for raw_value, display in candidates:
                    try:
                        value = int(str(raw_value), 0)
                    except ValueError:
                        continue
                    label = f"{name} → {display}"
                    labels.append(label)
                    self._quick_action_map[label] = {
                        "attrid": attr_id,
                        "value": value,
                        "typeid": type_id,
                    }
        with signals_blocked(self.quick_action_combo):
            self.quick_action_combo.clear()
            for label in labels:
                add_combo_item(self.quick_action_combo, label, label, f"快捷动作：{label}")

    def _on_quick_action_selected(self, label: str) -> None:
        info = self._quick_action_map.get(label)
        if not info:
            return
        self._set_send_mode("protocol")
        command_label = next((name for name, code in self._send_cmd_map.items() if code == 0x01), None)
        if command_label:
            self.command_combo.setCurrentText(command_label)
        payload = {"msg_id": 0, "attrs": [[info["attrid"], info["value"], info["typeid"]]]}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        self._send_buffers["protocol"] = text
        self._replace_send_text(text, "protocol")

    def _send_protocol_from_ui(self) -> bytes:
        command_code = extract_command_code(self.command_combo.currentText())
        fields = parse_fields_json(self._current_send_text("protocol")) or {}
        payload = self.protocol_manager.encode_frame(
            cmd_code=command_code,
            direction=normalize_direction(self.direction_combo.currentText()),
            fields=fields,
        )
        self.command_sender.send(payload)
        return payload

    def _send_data(self) -> bool:
        try:
            if self.send_mode == "protocol":
                self._send_protocol_from_ui()
            elif self.send_mode == "hex":
                payload = build_hex_payload(
                    self._current_send_text("hex"),
                    append_checksum=self.auto_checksum_enabled,
                    checksum_algorithm=self.checksum_combo.currentText(),
                    append_crlf=self.append_crlf_enabled,
                )
                self.command_sender.send(payload)
            else:
                payload = build_ascii_payload(
                    self._current_send_text("ascii"),
                    append_crlf=self.append_crlf_enabled,
                )
                self.command_sender.send(payload)
            self._send_buffers[self.send_mode] = self._current_send_text()
            return True
        except Exception as error:
            QMessageBox.warning(self, "发送失败", str(error))
            return False

    def _toggle_append_crlf(self, enabled: bool) -> None:
        self.append_crlf_enabled = bool(enabled)

    def _toggle_auto_checksum(self, enabled: bool) -> None:
        self.auto_checksum_enabled = bool(enabled)

    def _on_timeout_changed(self, value: int) -> None:
        self.packet_timeout_ms = int(value)

    def _on_interval_changed(self, value: int) -> None:
        self.auto_send_interval_ms = int(value)
        if self.auto_send_timer.isActive():
            self.auto_send_timer.setInterval(max(1, self.auto_send_interval_ms))

    def _toggle_auto_send(self, enabled: bool) -> None:
        self.auto_send_enabled = bool(enabled)
        if enabled:
            self.auto_send_timer.start(max(1, self.auto_send_interval.value()))
        else:
            self.auto_send_timer.stop()

    def _auto_send_tick(self) -> None:
        if not self.auto_send_enabled:
            return
        if not self._send_data():
            self.auto_send_button.setChecked(False)
            self.auto_send_enabled = False
            self.auto_send_timer.stop()
            return
        self.auto_send_timer.setInterval(max(1, self.auto_send_interval.value()))

    # ------------------------------------------------------------------
    # Command library
    # ------------------------------------------------------------------

    def _cmdlib_items(self) -> list[dict[str, Any]]:
        return self.command_library.items(self.cmdlib_mode)

    def _cmdlib_refresh_table(self) -> None:
        self.command_table.set_items(self._cmdlib_items(), self.cmdlib_mode)
        self.status_library.setText(
            f"{'已显示' if self.library_visible else '已隐藏'}指令库 · {self.cmdlib_mode.upper()}"
        )

    def _cmdlib_set_mode(self, mode: str) -> None:
        if mode not in {"hex", "ascii"}:
            return
        self._cmdlib_stop_cycle()
        self.cmdlib_mode = mode
        self.cmdlib_mode_switch.set_mode(mode, block_external=True)
        self.selected_command_index = None
        self._cmdlib_refresh_table()

    def _cmdlib_select_index(self, index: int) -> None:
        self.selected_command_index = index

    def _cmdlib_commit_inline(self, index: int, name: str, payload: str) -> None:
        items = self._cmdlib_items()
        try:
            if index < len(items):
                if not name and not payload:
                    self.command_library.delete(self.cmdlib_mode, index)
                else:
                    self.command_library.update(self.cmdlib_mode, index, name, payload)
            else:
                if not name and not payload:
                    return
                if index != len(items):
                    # New rows are appended in order; focus the first empty slot.
                    self.command_table.focus_first_empty(len(items))
                    return
                self.command_library.add(self.cmdlib_mode, name, payload)
        except Exception as error:
            QMessageBox.warning(self, "指令保存失败", str(error))
        self._cmdlib_refresh_table()

    def _cmdlib_focus_first_empty_row(self) -> None:
        items = self._cmdlib_items()
        if len(items) >= LIBRARY_MAX_ROWS:
            QMessageBox.information(self, "指令库已满", "当前模式最多保存 40 条指令。")
            return
        self.command_table.focus_first_empty(len(items))

    def _cmdlib_clear_selected(self) -> None:
        index = self.command_table.selected_index()
        items = self._cmdlib_items()
        if index is None or not 0 <= index < len(items):
            return
        reply = QMessageBox.question(self, "删除指令", f"确认删除“{items[index]['name']}”吗？")
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.command_library.delete(self.cmdlib_mode, index)
        except Exception as error:
            QMessageBox.warning(self, "删除失败", str(error))
        self._cmdlib_refresh_table()

    def _cmdlib_send_index(self, index: int) -> None:
        items = self._cmdlib_items()
        if not 0 <= index < len(items):
            return
        self._cmdlib_send_item(items[index])

    def _cmdlib_send_item(self, item: dict[str, Any]) -> None:
        try:
            payload_text = str(item.get("payload", item.get("data", "")))
            if self.cmdlib_mode == "hex":
                payload = build_hex_payload(payload_text)
            else:
                payload = build_ascii_payload(payload_text)
            self.command_sender.send(payload)
        except Exception as error:
            QMessageBox.warning(self, "发送失败", str(error))

    def _cmdlib_toggle_cycle(self, enabled: bool) -> None:
        if enabled:
            self._cmdlib_start_cycle()
        else:
            self._cmdlib_stop_cycle()

    def _cmdlib_start_cycle(self) -> None:
        items = self._cmdlib_items()
        if not items:
            with signals_blocked(self.cycle_button):
                self.cycle_button.setChecked(False)
            return
        configured = self.command_library.cycle(self.cmdlib_mode)
        by_id = {item["id"]: item for item in items}
        self.cmdlib_cycle_steps = [
            {"item": by_id[step["id"]], "delay_ms": int(step.get("delay_ms", 1000))}
            for step in configured
            if step.get("id") in by_id
        ]
        if not self.cmdlib_cycle_steps:
            self.cmdlib_cycle_steps = [{"item": item, "delay_ms": 1000} for item in items]
        self.cmdlib_cycle_on = True
        self.cmdlib_cycle_index = 0
        self._cmdlib_cycle_tick()

    def _cmdlib_stop_cycle(self) -> None:
        self.cmdlib_cycle_on = False
        self.cycle_timer.stop()
        with signals_blocked(self.cycle_button):
            self.cycle_button.setChecked(False)

    def _cmdlib_cycle_tick(self) -> None:
        if not self.cmdlib_cycle_on or not self.cmdlib_cycle_steps:
            return
        step = self.cmdlib_cycle_steps[self.cmdlib_cycle_index % len(self.cmdlib_cycle_steps)]
        self._cmdlib_send_item(step["item"])
        delay = max(10, int(step.get("delay_ms", 1000)))
        self.cmdlib_cycle_index = (self.cmdlib_cycle_index + 1) % len(self.cmdlib_cycle_steps)
        self.cycle_timer.start(delay)

    def _cmdlib_open_cycle_config(self) -> None:
        items = self._cmdlib_items()
        if not items:
            QMessageBox.information(self, "配置循环", "当前指令库为空。")
            return
        current = {step["id"]: int(step.get("delay_ms", 1000)) for step in self.command_library.cycle(self.cmdlib_mode)}
        dialog = QDialog(self)
        dialog.setWindowTitle(f"配置循环 - {self.cmdlib_mode.upper()}")
        dialog.resize(520, 460)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(items), 3, dialog)
        table.setHorizontalHeaderLabels(["启用", "名称", "间隔(ms)"])
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        controls: list[tuple[QCheckBox, QSpinBox, dict[str, Any]]] = []
        for row, item in enumerate(items):
            check = QCheckBox(table)
            check.setChecked(item["id"] in current)
            table.setCellWidget(row, 0, check)
            table.setItem(row, 1, QTableWidgetItem(item["name"]))
            spin = QSpinBox(table)
            spin.setRange(10, 3_600_000)
            spin.setValue(current.get(item["id"], 1000))
            table.setCellWidget(row, 2, spin)
            controls.append((check, spin, item))
        layout.addWidget(table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        steps = [
            {"id": item["id"], "delay_ms": spin.value()}
            for check, spin, item in controls
            if check.isChecked()
        ]
        try:
            self.command_library.set_cycle(self.cmdlib_mode, steps)
        except CommandLibraryError as error:
            QMessageBox.warning(self, "保存失败", str(error))

    # ------------------------------------------------------------------
    # Windows native topmost (no window recreation)
    # ------------------------------------------------------------------

    def _set_windows_topmost(
        self,
        enabled: bool,
    ) -> tuple[bool, int]:
        """Windows原生置顶。

        不修改Qt窗口flags，
        不调用hide/show，
        不改变窗口位置、尺寸和激活状态。
        """
        if os.name != "nt":
            return False, 0

        try:
            # 强制Qt先创建原生窗口句柄
            hwnd_value = int(self.winId())

            if hwnd_value == 0:
                return False, 0

            user32 = ctypes.WinDLL(
                "user32",
                use_last_error=True,
            )

            set_window_pos = user32.SetWindowPos

            set_window_pos.argtypes = (
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            )

            set_window_pos.restype = wintypes.BOOL

            HWND_TOPMOST = wintypes.HWND(-1)
            HWND_NOTOPMOST = wintypes.HWND(-2)

            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            SWP_NOOWNERZORDER = 0x0200
            SWP_NOSENDCHANGING = 0x0400

            flags = (
                SWP_NOSIZE
                | SWP_NOMOVE
                | SWP_NOACTIVATE
                | SWP_NOOWNERZORDER
                | SWP_NOSENDCHANGING
            )

            insert_after = (
                HWND_TOPMOST
                if enabled
                else HWND_NOTOPMOST
            )

            ctypes.set_last_error(0)

            result = set_window_pos(
                wintypes.HWND(hwnd_value),
                insert_after,
                0,
                0,
                0,
                0,
                flags,
            )

            if not result:
                return False, ctypes.get_last_error()

            return True, 0

        except Exception:
            return False, ctypes.get_last_error()

    def _on_topmost_toggled(
        self,
        checked: bool,
    ):
        requested_state = bool(checked)

        if os.name == "nt":
            success, error_code = (
                self._set_windows_topmost(
                    requested_state
                )
            )

        else:
            # 非Windows平台的Qt回退逻辑
            self.setWindowFlag(
                Qt.WindowStaysOnTopHint,
                requested_state,
            )

            self.show()
            success = True
            error_code = 0

        if not success:
            # 恢复按钮原状态，并阻止信号递归
            blocker = QSignalBlocker(
                self.topmost_button
            )

            self.topmost_button.setChecked(
                not requested_state
            )

            del blocker

            QMessageBox.warning(
                self,
                "置顶失败",
                (
                    "Windows 无法修改窗口置顶状态。\n"
                    f"系统错误代码：{error_code}"
                ),
            )

            return

        self.topmost_enabled = requested_state

        # 只刷新按钮状态，不操作窗口flags
        self.topmost_button.setProperty(
            "active",
            requested_state,
        )

        self.topmost_button.style().unpolish(
            self.topmost_button
        )

        self.topmost_button.style().polish(
            self.topmost_button
        )

        self.topmost_button.update()

    # ------------------------------------------------------------------
    # Miscellaneous actions
    # ------------------------------------------------------------------

    def _launch_new_serial_tool(self) -> None:
        try:
            subprocess.Popen([sys.executable, str(PROJECT_ROOT / "main.py")], cwd=str(PROJECT_ROOT))
        except Exception as error:
            QMessageBox.warning(self, "添加串口失败", str(error))

    def _open_save_log_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存实时数据日志",
            str(PROJECT_ROOT / f"serial_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self.rx_edit.toPlainText(), encoding="utf-8")
        except Exception as error:
            QMessageBox.warning(self, "保存失败", str(error))

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        self.rx_timer.stop()
        self.packet_timer.stop()
        self.reconfigure_timer.stop()
        self.auto_send_timer.stop()
        self.cycle_timer.stop()
        self.auto_send_enabled = False
        self.cmdlib_cycle_on = False
        try:
            if self.raw_saver.active:
                self.raw_saver.stop(flush=True)
        except Exception:
            pass
        try:
            self.worker.disconnect(wait=True, timeout=2.0)
        except Exception:
            pass
        event.accept()
