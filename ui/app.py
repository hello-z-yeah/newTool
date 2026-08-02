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
from PySide6.QtGui import QCloseEvent, QFont, QIntValidator, QTextCursor
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
    ReorderableCycleTable,
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
    RECEIVE_TOOLBAR_WRAP_WIDTH,
    RX_FONT_DEFAULT_SIZE,
    SECTION_PADDING_X,
    SECTION_PADDING_Y,
    SECTION_ROW_GAP,
    SEND_CARD_HEIGHT,
    STATUS_GREEN,
    STATUS_HEIGHT,
    STATUS_ORANGE,
    TEXT_MUTED,
    TEXT_SECONDARY,
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
        # protocol_parse_enabled 别名（兼容 protocol_parse_enabled 命名的代码路径）
        self.protocol_parse_enabled = False
        self.auto_scroll = True
        self.packet_display_enabled = False
        self.packet_timeout_ms = 20
        self.display_mode = "hex"
        # display_format 别名（兼容 display_format 命名的代码路径）
        self.display_format = "hex"
        self.monitoring = False
        self.monitor_starting = False
        self.serial_reconfiguring = False
        self.active_serial_config: dict[str, Any] | None = None
        self.topmost_enabled = False
        # 数据存储状态（不依赖 storage_button.setChecked，避免靠按钮文字反推）
        self.is_storing = False

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
        category = str(category or "").strip()
        text = str(text or "").strip()

        if not text:
            self._clear_combo_option_status()
            return

        if category:
            prefixes = (
                f"{category}：",
                f"{category}:",
            )
            for prefix in prefixes:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
                    break
            display_text = f"{category}：{text}"
        else:
            display_text = text

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
            add_combo_item(self.baud_combo, value, value, value)
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
            add_combo_item(self.data_bits_combo, value, int(value), value)
        self.data_bits_combo.setCurrentText("8")
        self.data_bits_combo.setFixedHeight(CONTROL_HEIGHT)
        row1.addWidget(self.data_bits_combo, 0, Qt.AlignmentFlag.AlignVCenter)

        stop_bits_label = QLabel("停止位")
        stop_bits_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        row1.addWidget(stop_bits_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.stop_bits_combo = self._create_combo(status_name="停止位", parent=self.serial_detail)
        for value in ("1", "1.5", "2"):
            add_combo_item(self.stop_bits_combo, value, float(value), value)
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
            font_size=RX_FONT_DEFAULT_SIZE,
        )
        self.rx_edit.setReadOnly(True)
        self.rx_edit.setPlaceholderText("等待接收数据…")
        # ZoomableDataView 默认使用 NoWrap；此处显式保证 HEX/ASCII 数据不自动换行
        self.rx_edit.setLineWrapMode(self.rx_edit.LineWrapMode.NoWrap)
        self.rx_edit.document().setMaximumBlockCount(5000)
        receive_layout.addWidget(self.rx_edit, 1)
        self.rx_scroll_controller = HoverScrollController(self.rx_edit)
        # 连接显示内容统计（字节数+行数）到状态栏，并初始化一次
        self.rx_edit.displayStatsChanged.connect(self._update_display_stats)
        self.rx_edit.scheduleDisplayStatsUpdate()

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
        # 顶层容器：使用 QGridLayout 支持宽窄布局两种排布
        self.receive_toolbar = QWidget(self.workspace_card)
        self.receive_toolbar.setMinimumHeight(CONTROL_ROW_MIN_HEIGHT)
        self.receive_toolbar_grid = QGridLayout(self.receive_toolbar)
        # 只给外侧预留按钮阴影的上下留白，左右不缩进
        self.receive_toolbar_grid.setContentsMargins(0, BUTTON_SHADOW_PAD_Y, 0, BUTTON_SHADOW_PAD_Y)
        # 统一 8px 水平/垂直间距
        self.receive_toolbar_grid.setHorizontalSpacing(8)
        self.receive_toolbar_grid.setVerticalSpacing(6)

        # 基础控制区：实时数据｜协议解析模式｜HEX格式｜清空｜自动滚动｜分包显示｜超时｜20
        self.receive_basic_controls = QWidget(self.receive_toolbar)
        self.receive_basic_layout = QHBoxLayout(self.receive_basic_controls)
        self.receive_basic_layout.setContentsMargins(0, 0, 0, 0)
        self.receive_basic_layout.setSpacing(8)

        self.receive_title = QLabel("实时数据", self.receive_basic_controls)
        self.receive_title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.receive_basic_layout.addWidget(self.receive_title, 0, Qt.AlignmentFlag.AlignVCenter)

        self.parse_button = StateButton("协议解析模式", self.receive_basic_controls, checkable=True)
        self.parse_button.setFixedHeight(BUTTON_HEIGHT)
        set_button_width_for_texts(self.parse_button, ("协议解析模式", "协议解析模式"))
        self.parse_button.toggled.connect(self._set_parse_mode)
        self.receive_basic_layout.addWidget(self.parse_button, 0, Qt.AlignmentFlag.AlignVCenter)

        # 显示格式切换按钮：HEX / ASCII
        self.format_button = StateButton("HEX格式", self.receive_basic_controls, checkable=True)
        self.format_button.setChecked(True)
        self.format_button.setFixedHeight(BUTTON_HEIGHT)
        set_button_width_for_texts(self.format_button, ("HEX格式", "ASCII格式"))
        self.format_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.format_button.clicked.connect(self._toggle_display_format)
        self.receive_basic_layout.addWidget(self.format_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.clear_receive_button = StateButton("清空", self.receive_basic_controls)
        self.clear_receive_button.setFixedHeight(BUTTON_HEIGHT)
        self.clear_receive_button.clicked.connect(self._clear_rx)
        self.receive_basic_layout.addWidget(self.clear_receive_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.auto_scroll_button = StateButton("自动滚动", self.receive_basic_controls, checkable=True)
        self.auto_scroll_button.setChecked(True)
        self.auto_scroll_button.setFixedHeight(BUTTON_HEIGHT)
        self.auto_scroll_button.toggled.connect(self._toggle_auto_scroll)
        self.receive_basic_layout.addWidget(self.auto_scroll_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.packet_display_button = StateButton("分包显示", self.receive_basic_controls, checkable=True)
        # 保留旧引用名 packet_button，兼容其他代码
        self.packet_button = self.packet_display_button
        self.packet_display_button.setFixedHeight(BUTTON_HEIGHT)
        self.packet_display_button.toggled.connect(self._toggle_packet_display)
        self.receive_basic_layout.addWidget(self.packet_display_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.timeout_label = QLabel("超时(ms)", self.receive_basic_controls)
        self.timeout_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.receive_basic_layout.addWidget(self.timeout_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.timeout_input = IntegerLineEdit(
            value=20,
            minimum=0,
            maximum=100000,
            parent=self.receive_basic_controls,
        )
        # 保留旧引用名 packet_timeout_spin，兼容其他代码
        self.packet_timeout_spin = self.timeout_input
        self.timeout_input.setFixedWidth(68)
        self.timeout_input.setFixedHeight(CONTROL_HEIGHT)
        self.timeout_input.valueChanged.connect(self._on_timeout_changed)
        self.receive_basic_layout.addWidget(self.timeout_input, 0, Qt.AlignmentFlag.AlignVCenter)

        # 弹性空间只能放在基础控件尾部，避免前面被拉伸
        self.receive_basic_layout.addStretch(1)

        # 协议控制区：产品协议｜下拉｜导入Word｜查看协议｜模组发送
        self.receive_protocol_controls = QWidget(self.receive_toolbar)
        # SizePolicy：水平 Minimum（只按内容需要的最小宽度），垂直 Fixed
        self.receive_protocol_controls.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        # 同时保留旧引用名 protocol_controls，避免其他代码直接使用它出现 AttributeError
        self.protocol_controls = self.receive_protocol_controls
        self.receive_protocol_layout = QHBoxLayout(self.receive_protocol_controls)
        self.receive_protocol_layout.setContentsMargins(0, 0, 0, 0)
        # 统一 8px 间距
        self.receive_protocol_layout.setSpacing(8)
        # 第二行要求所有控件整体靠左、竖向居中，不拉伸任何一个控件
        self.receive_protocol_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.product_protocol_label = QLabel("产品协议:", self.receive_protocol_controls)
        self.product_protocol_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        # 标签后立即连接下拉框，中间不加任何空白占位
        self.receive_protocol_layout.addWidget(
            self.product_protocol_label, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.product_protocol_combo = self._create_combo(
            status_name="产品协议", parent=self.receive_protocol_controls
        )
        # 固定 180px 宽（不再 Expanding 或 Min/Max 区间），宽窄模式下宽度完全一致
        self.product_protocol_combo.setFixedWidth(180)
        self.product_protocol_combo.setFixedHeight(CONTROL_HEIGHT)
        self.product_protocol_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.receive_protocol_layout.addWidget(
            self.product_protocol_combo, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.import_word_button = StateButton("导入Word协议", self.receive_protocol_controls)
        self.import_word_button.setFixedHeight(BUTTON_HEIGHT)
        self.import_word_button.clicked.connect(self._import_word_protocol)
        # 三个协议按钮统一 Fixed/Fixed，宽窄切换不改尺寸
        self.import_word_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.receive_protocol_layout.addWidget(
            self.import_word_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.view_protocol_button = StateButton("查看协议", self.receive_protocol_controls)
        self.view_protocol_button.setFixedHeight(BUTTON_HEIGHT)
        self.view_protocol_button.clicked.connect(self._view_current_protocol)
        self.view_protocol_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.receive_protocol_layout.addWidget(
            self.view_protocol_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        self.module_send_button = StateButton("模组发送", self.receive_protocol_controls)
        self.module_send_button.setFixedHeight(BUTTON_HEIGHT)
        self.module_send_button.clicked.connect(self._module_send)
        self.module_send_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.receive_protocol_layout.addWidget(
            self.module_send_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

        # 弹性空间只能放在协议控件尾部（且只能有这一个 stretch）
        self.receive_protocol_layout.addStretch(1)

        # 协议解析默认关闭时隐藏协议控件（窄/宽布局都只隐藏协议容器）
        self.receive_protocol_controls.hide()

        # 按当前宽度决定排布方式
        self._update_receive_toolbar_layout()

        parent_layout.addWidget(self.receive_toolbar)

    def _update_receive_toolbar_layout(self) -> None:
        """根据 receive_card(workspace_card) 宽度切换工具栏单行/两行布局。

        只移动两个容器在 QGridLayout 中的位置/对齐，不改变任何按钮或下拉框尺寸。
        """
        if not hasattr(self, "receive_toolbar_grid") or not hasattr(self, "receive_basic_controls"):
            return

        # 工具栏挂在 workspace_card 下；宽度以 workspace_card 为准
        card = getattr(self, "workspace_card", None) or getattr(self, "receive_card", None)
        available_width = card.width() if card is not None else 10000
        compact = available_width < RECEIVE_TOOLBAR_WRAP_WIDTH

        grid = self.receive_toolbar_grid
        basic = self.receive_basic_controls
        proto = self.receive_protocol_controls

        # 先从网格中移除位置关系（不销毁控件）
        try:
            grid.removeWidget(basic)
        except Exception:
            pass
        try:
            grid.removeWidget(proto)
        except Exception:
            pass

        if compact:
            # 窄窗口：第一行基础控件，第二行协议控件，都从左侧开始
            grid.addWidget(
                basic, 0, 0, 1, 1, Qt.AlignmentFlag.AlignLeft
            )
            grid.addWidget(
                proto, 1, 0, 1, 1, Qt.AlignmentFlag.AlignLeft
            )
            # 伸缩只作用于行尾剩余空间，不拉伸控件本体
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 0)
        else:
            # 宽窗口：基础控件 (0,0) 不吸收，协议控件 (0,1) 吸收行尾剩余空间
            grid.addWidget(
                basic, 0, 0, 1, 1, Qt.AlignmentFlag.AlignLeft
            )
            grid.addWidget(
                proto, 0, 1, 1, 1, Qt.AlignmentFlag.AlignLeft
            )
            grid.setColumnStretch(0, 0)
            grid.setColumnStretch(1, 1)

        grid.invalidate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 防抖 80ms：只在窗口尺寸稳定后重新排布工具栏
        if not hasattr(self, "_receive_layout_timer"):
            self._receive_layout_timer = QTimer(self)
            self._receive_layout_timer.setSingleShot(True)
            self._receive_layout_timer.timeout.connect(self._update_receive_toolbar_layout)
        self._receive_layout_timer.start(80)

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
        # 视觉只负责发出 valueChanged(str) 信号；
        # 主窗口只用 self.cmdlib_mode 作为业务状态的唯一真源，
        # 不再分别连 modeChanged / 左按钮clicked / 右按钮clicked，避免重复切换。
        self.cmdlib_mode_switch.valueChanged.connect(self._on_cmdlib_mode_changed)
        self.cmdlib_mode_switch.setValue(self.cmdlib_mode, emit_signal=False)
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
            add_combo_item(self.checksum_combo, value, value, value)
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
            add_combo_item(self.direction_combo, value, value, value)
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

        # ------------------------------------------------------------
        # 1) 串口监控状态：● 绿/橙 + 未连接 / COM1 9600
        # ------------------------------------------------------------
        self.connection_dot = QLabel("●", self.status_card)
        self.connection_dot.setStyleSheet(f"color: {STATUS_ORANGE};")
        self.connection_text = QLabel("未连接", self.status_card)
        self.connection_text.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        # 兼容旧代码可能还在写 status_port / status_baud
        self.status_port = self.connection_text
        self.status_baud = QLabel("", self.status_card)
        self.status_baud.setVisible(False)

        layout.addWidget(self.connection_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.connection_text, 0, Qt.AlignmentFlag.AlignVCenter)

        # ------------------------------------------------------------
        # 2) 存储状态：● 绿/橙 + 未存储 / 存储中
        # ------------------------------------------------------------
        layout.addSpacing(10)
        self.storage_dot = QLabel("●", self.status_card)
        self.storage_dot.setStyleSheet(f"color: {STATUS_ORANGE};")
        self.storage_text = QLabel("未存储", self.status_card)
        self.storage_text.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        # 兼容可能存在的 status_storage 别名
        self.status_storage = self.storage_text

        layout.addWidget(self.storage_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.storage_text, 0, Qt.AlignmentFlag.AlignVCenter)

        # ------------------------------------------------------------
        # 3) 指令库状态：已显示/已隐藏指令库 · HEX/ASCII
        # ------------------------------------------------------------
        layout.addSpacing(10)
        self.status_library = self._make_status_label(
            f"已隐藏指令库 · {self.cmdlib_mode.upper()}",
            self.status_card,
            attr="status_library",
        )
        layout.addWidget(self.status_library, 0, Qt.AlignmentFlag.AlignVCenter)

        # 下拉选项悬停预览：吸收中间剩余宽度，不挤占右侧 RX/TX/错误/缓冲/显示缓存/行数
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

        # 与串口缓冲保持间距，再增加两个独立状态：显示缓存、行数
        layout.addSpacing(10)
        self.display_buffer_status = self._make_status_label(
            "显示缓存 0B", self.status_card, attr="display_buffer_status"
        )
        layout.addWidget(self.display_buffer_status, 0, Qt.AlignmentFlag.AlignVCenter)
        self.display_line_status = self._make_status_label(
            "行数 0", self.status_card, attr="display_line_status"
        )
        layout.addWidget(self.display_line_status, 0, Qt.AlignmentFlag.AlignVCenter)

        self.root_layout.addWidget(self.status_card)

    @staticmethod
    def _format_byte_size(byte_count: int) -> str:
        """统一格式化字节数：B / KB / MB。"""
        size = max(0, int(byte_count))
        if size < 1024:
            return f"{size}B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size / 1024 / 1024:.1f}MB"

    def _update_display_stats(self, byte_count: int, line_count: int) -> None:
        """接收 ZoomableDataView.displayStatsChanged 信号，更新状态栏显示缓存和行数。"""
        if hasattr(self, "display_buffer_status"):
            self.display_buffer_status.setText(
                "显示缓存 " + self._format_byte_size(byte_count)
            )
        if hasattr(self, "display_line_status"):
            self.display_line_status.setText(f"行数 {max(0, int(line_count))}")

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
        # 初始化：根据当前 display_format (默认 HEX) 刷新协议解析按钮可用状态
        self._enforce_protocol_parse_for_display_format()
        # 初始化：状态栏连接/存储状态点首次颜色
        self._update_connection_status_ui()
        self._update_storage_status_ui()
        self._update_library_status_label()

    def _load_protocols(self) -> None:
        names = self.protocol_manager.available_protocols()
        self.product_protocol_combo.clear()
        for name in names:
            add_combo_item(self.product_protocol_combo, name, name, name)
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
        self._update_connection_status_ui()
        if not success and message:
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
        self._update_connection_status_ui()

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
        self._update_connection_status_ui()
        if not success and message:
            QMessageBox.warning(self, "串口重连失败", message)

    def _handle_serial_error(self, message: str) -> None:
        self.error_count += 1
        self.status_err.setText(f"错误 {self.error_count}")
        self._stop_monitoring()
        QMessageBox.warning(self, "串口错误", message)

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _update_connection_status_ui(self) -> None:
        """刷新左下角串口监控状态点和文字。

        绿点 = 监控中（monitoring=True + worker.is_connected 实际已打开）
        橙点 = 未连接
        """
        monitoring = bool(getattr(self, "monitoring", False))
        worker_connected = False
        if monitoring:
            worker = getattr(self, "worker", None)
            if worker is not None:
                connected = getattr(worker, "is_connected", None)
                if callable(connected):
                    worker_connected = bool(connected())
                elif connected is not None:
                    worker_connected = bool(connected)
                else:
                    worker_connected = True

        green = monitoring and worker_connected
        self.connection_dot.setStyleSheet(f"color: {STATUS_GREEN if green else STATUS_ORANGE};")

        if green and self.active_serial_config:
            port = str(self.active_serial_config.get("port") or "").strip()
            baud = str(self.active_serial_config.get("baudrate") or "").strip()
            if not port:
                port = str(self.port_combo.currentData() or self.port_combo.currentText() or "").strip()
            if not baud:
                baud = str(self.baud_combo.currentText() or "").strip()
            if port and baud:
                self.connection_text.setText(f"{port}  {baud}")
            elif port:
                self.connection_text.setText(port)
            else:
                self.connection_text.setText("未连接")
        else:
            self.connection_text.setText("未连接")

    def _update_storage_status_ui(self) -> None:
        """刷新存储状态点和文字（不依赖 storage_button 的文案）。"""
        is_active = bool(getattr(self, "is_storing", False)) or bool(getattr(self.raw_saver, "active", False))
        # 以 raw_saver.active 为基准，同步 self.is_storing
        saver_active = bool(getattr(self.raw_saver, "active", False))
        self.is_storing = saver_active
        self.storage_dot.setStyleSheet(f"color: {STATUS_GREEN if saver_active else STATUS_ORANGE};")
        self.storage_text.setText("存储中" if saver_active else "未存储")

    def _toggle_storage(self) -> None:
        if self.raw_saver.active:
            self.raw_saver.stop(flush=True)
            self.storage_button.setText("开始存储数据")
            with signals_blocked(self.storage_button):
                self.storage_button.setChecked(False)
            self._update_storage_status_ui()
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
            self._update_storage_status_ui()
            return
        self.storage_button.setText("停止存储数据")
        with signals_blocked(self.storage_button):
            self.storage_button.setChecked(True)
        self._update_storage_status_ui()

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
        # 存储错误后，强制回到"未存储"状态
        self.is_storing = False
        with signals_blocked(self.storage_button):
            self.storage_button.setChecked(False)
        self.storage_button.setText("开始存储数据")
        self._update_storage_status_ui()

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
            # 双重保护：必须同时开启协议解析 AND 显示模式为 HEX
            parse_enabled = self._is_protocol_parse_enabled()
            is_hex_mode = self._get_display_format() == "hex"
            if parse_enabled and is_hex_mode and direction == "RX":
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
        # 批量插入完成后，异步刷新状态栏的显示缓存与行数（防抖 80ms）
        self.rx_edit.scheduleDisplayStatsUpdate()

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
        # 更新 display_format 别名（兼容外部代码按 display_format 访问）
        self.display_format = self.display_mode
        # 关键：ASCII模式下强制关闭协议解析
        self._enforce_protocol_parse_for_display_format()
        self._rerender_rx_history()

    def _refresh_protocol_parse_button_style(self) -> None:
        """刷新协议解析按钮 QSS 样式（绿色选中态 / 白色未选中态）。"""
        button = getattr(self, "parse_button", None) or getattr(
            self, "protocol_parse_button", None
        )
        if button is None:
            return
        try:
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        except Exception:
            pass

    def _set_protocol_parse_enabled(self, enabled: bool) -> None:
        """统一设置协议解析开关状态（同时更新 parse_mode / protocol_parse_enabled）。"""
        enabled = bool(enabled)
        if hasattr(self, "parse_mode"):
            self.parse_mode = enabled
        if hasattr(self, "protocol_parse_enabled"):
            self.protocol_parse_enabled = enabled

    def _is_protocol_parse_enabled(self) -> bool:
        return bool(getattr(self, "parse_mode", False) or getattr(self, "protocol_parse_enabled", False))

    def _get_display_format(self) -> str:
        """统一获取显示格式（同时兼容 display_format / display_mode）。"""
        return str(
            getattr(self, "display_format", None)
            or getattr(self, "display_mode", "hex")
        ).strip().lower()

    def _enforce_protocol_parse_for_display_format(self) -> None:
        """ASCII显示模式下强制关闭并禁用协议解析。"""
        is_hex_mode = self._get_display_format() == "hex"

        # 兼容两种变量名：parse_button / protocol_parse_button
        protocol_parse_button = getattr(
            self, "parse_button", None
        ) or getattr(self, "protocol_parse_button", None)

        # 兼容两种控件名：protocol_controls / protocol_controls_frame
        protocol_controls_frame = getattr(
            self, "protocol_controls_frame", None
        ) or getattr(self, "protocol_controls", None)

        if not is_hex_mode:
            # 当前协议解析已开启时，强制关闭
            if protocol_parse_button is not None and protocol_parse_button.isChecked():
                blocker = QSignalBlocker(protocol_parse_button)
                protocol_parse_button.setChecked(False)
                del blocker

            # 同时同步两个状态名
            self._set_protocol_parse_enabled(False)

            # ASCII模式下不允许再次点击开启
            if protocol_parse_button is not None:
                protocol_parse_button.setEnabled(False)
                protocol_parse_button.setToolTip(
                    "ASCII显示模式下不可使用协议解析"
                )

            # 隐藏产品协议、导入Word、查看协议、模组发送等控件
            if protocol_controls_frame is not None:
                protocol_controls_frame.setVisible(False)

            # 清理未完成协议帧，防止切回HEX后解析旧缓存
            synchronizer = getattr(self, "frame_synchronizer", None)
            if synchronizer is not None:
                reset_method = getattr(synchronizer, "reset", None)
                if callable(reset_method):
                    try:
                        reset_method()
                    except Exception:
                        pass

            parser = getattr(self, "protocol_parser", None)
            if parser is not None:
                reset_method = getattr(parser, "reset", None)
                if callable(reset_method):
                    try:
                        reset_method()
                    except Exception:
                        pass

        else:
            # 切回HEX只恢复可用状态，不自动开启
            if protocol_parse_button is not None:
                protocol_parse_button.setEnabled(True)
                protocol_parse_button.setToolTip("")

            if protocol_controls_frame is not None:
                protocol_controls_frame.setVisible(self._is_protocol_parse_enabled())

        # 刷新按钮的绿色开启态/白色关闭态
        self._refresh_protocol_parse_button_style()

    def _set_parse_mode(self, enabled: bool) -> None:
        """协议解析按钮切换回调（toggled 信号）—— ASCII 模式二次保护。"""
        is_hex_mode = self._get_display_format() == "hex"

        # 兼容两种按钮名
        protocol_parse_button = getattr(
            self, "parse_button", None
        ) or getattr(self, "protocol_parse_button", None)

        protocol_controls_frame = getattr(
            self, "protocol_controls_frame", None
        ) or getattr(self, "protocol_controls", None)

        if not is_hex_mode:
            # ASCII模式：任何方式尝试开启都要恢复为未选中并禁用
            if protocol_parse_button is not None:
                blocker = QSignalBlocker(protocol_parse_button)
                protocol_parse_button.setChecked(False)
                del blocker
                protocol_parse_button.setEnabled(False)
                protocol_parse_button.setToolTip(
                    "ASCII显示模式下不可使用协议解析"
                )
            # 同时同步两个状态名
            self._set_protocol_parse_enabled(False)
            return

        # HEX模式：正常切换状态
        enabled = bool(enabled)
        self._set_protocol_parse_enabled(enabled)

        if protocol_controls_frame is not None:
            protocol_controls_frame.setVisible(enabled)

        if protocol_parse_button is not None:
            with signals_blocked(protocol_parse_button):
                protocol_parse_button.setChecked(enabled)

        self._refresh_protocol_parse_button_style()
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
                add_combo_item(self.command_combo, label, label, label)
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
                add_combo_item(self.quick_action_combo, label, label, label)

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
        """按 self.cmdlib_mode 读取当前指令库数据（禁止空 ASCII 时回退到 HEX）。

        真正的读库入口统一在这里，CommandLibraryStore.items 按 mode 参数独立
        维护两套库：hex_cmds.json / ascii_cmds.json，互不串数据。
        """
        mode = CommandLibraryStore.normalize_mode(self.cmdlib_mode)
        return self.command_library.items(mode)

    def _cmdlib_refresh_table(self) -> None:
        """刷新指令库表格与状态栏显示。

        这里禁止执行 `self.cmdlib_mode = "hex"` 之类的回写；
        cmdlib_mode 只在 _on_cmdlib_mode_changed / __init__ 中被修改。
        """
        items = self._cmdlib_items()

        # 临时打印（用于定位链：signal→stored→refresh）；验证完成后可以删除
        print(
            "[cmdlib] refresh mode:",
            repr(self.cmdlib_mode),
            "item count:",
            len(items),
        )

        self.command_table.set_items(items, self.cmdlib_mode)
        self._update_library_status_label()

    def _on_cmdlib_mode_changed(self, mode: object) -> None:
        """唯一的指令库模式切换入口。

        只连 SegmentToggle.valueChanged(str)；
        其它连法（modeChanged / 左右按钮clicked）都去掉，避免重复或覆盖。
        """
        normalized = str(mode or "").strip().lower()

        # 临时打印：验证 signal 传过来的是字符串 "ascii"/"hex"，
        # 而不是 True/False 这种 clicked(bool) 的布尔值；验证完成后可以删除
        print(
            "[cmdlib] signal mode:",
            repr(mode),
            "-> normalized:",
            repr(normalized),
        )

        if normalized not in {"hex", "ascii"}:
            return

        # 切库前先停止正在运行的循环发送，避免按新库重排步骤继续跑
        self._cmdlib_stop_cycle()

        self.cmdlib_mode = normalized

        # 同步视觉，且 emit_signal=False，禁止 SegmentToggle 再发信号，
        # 否则会递归触发 _on_cmdlib_mode_changed
        self.cmdlib_mode_switch.setValue(normalized, emit_signal=False)

        # 清除当前选中行：两套库独立，行号不再对应
        self.selected_command_index = None

        # 临时打印：验证 self.cmdlib_mode 确实被成功写入；验证完成后可以删除
        print(
            "[cmdlib] stored mode:",
            repr(self.cmdlib_mode),
        )

        self._cmdlib_refresh_table()

    # ---------- 旧接口兼容别名 ----------
    def _cmdlib_set_mode(self, mode: object) -> None:
        self._on_cmdlib_mode_changed(mode)

    def _update_library_status_label(self) -> None:
        if not hasattr(self, "status_library"):
            return
        self.status_library.setText(
            f"{'已显示' if self.library_visible else '已隐藏'}指令库 · {self.cmdlib_mode.upper()}"
        )

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

    def _command_item_for_row(self, row: int) -> dict[str, Any] | None:
        """获取指定行的真实数据项（优先读存储中的数据，其次读表格当前显示）。"""
        items = self._cmdlib_items()
        if 0 <= row < len(items):
            return dict(items[row])

        # 超出已保存行数：从表格当前行读取（用户可能刚填写还没保存）
        if 0 <= row < LIBRARY_MAX_ROWS:
            try:
                name, payload = self.command_table.row_values(row)
                cmd_type = self.command_table._type_items[row].text().strip().upper() or self.cmdlib_mode.upper()
                if payload.strip():
                    return {
                        "name": name,
                        "payload": payload,
                        "type": cmd_type if cmd_type in {"HEX", "ASCII"} else self.cmdlib_mode.upper(),
                    }
            except Exception:
                pass
        return None

    def _parse_hex_payload(self, payload: str) -> bytes:
        compact = "".join(payload.split())
        if not compact:
            return b""
        if len(compact) % 2 != 0:
            raise ValueError("HEX指令必须由完整字节组成。")
        try:
            return bytes.fromhex(compact)
        except ValueError as error:
            raise ValueError("HEX指令中包含非法字符。") from error

    def _encode_ascii_payload(self, payload: str) -> bytes:
        encoding = getattr(self, "ascii_encoding", "utf-8")
        try:
            return payload.encode(encoding)
        except UnicodeEncodeError as error:
            raise ValueError(f"ASCII指令无法使用 {encoding} 编码。") from error

    def _show_send_error(self, message: str) -> None:
        QMessageBox.warning(self, "发送失败", str(message))

    def _serial_is_connected(self) -> bool:
        """返回当前串口是否可发送数据。

        以 self.monitoring（connect 成功后设置的主状态）为基准，
        再结合 SerialWorker.is_connected（内部基于 _serial.is_open）双重确认，
        不假设不存在的 worker.is_open / ser 属性。
        """
        if not bool(getattr(self, "monitoring", False)):
            return False

        worker = getattr(self, "worker", None)
        if worker is None:
            return False

        worker_connected = getattr(worker, "is_connected", None)
        if callable(worker_connected):
            return bool(worker_connected())
        if worker_connected is not None:
            # property 情形：is_connected 本身就是 bool
            return bool(worker_connected)

        # 极端兜底：没有 is_connected，但 monitoring 为 True，视为已连接
        return True

    def _send_library_payload(self, *, payload: str, command_type: str) -> None:
        """显式指定 HEX/ASCII 类型发送（不依赖主发送模式）。

        复用与主发送完全相同的底层：self.command_sender.send(payload)，
        从而保证：串口连接检查、TX 计数、实时数据显示 TX、存储日志、错误处理、
        自动滚动、HEX/ASCII 渲染 所有行为一致。
        """
        if not self._serial_is_connected():
            self._show_send_error("串口未连接，请先开始监控。")
            return

        try:
            if command_type == "HEX":
                # 复用 command_sender 的 build_hex_payload（保持原分隔符兼容性）
                data = build_hex_payload(payload)
            else:
                data = build_ascii_payload(payload)

            if not data:
                return

            # 通过 command_sender.send 发送：完全复用主发送同一管线
            # (串口检查 → worker.send → TX计数 → 发送日志/实时数据)
            self.command_sender.send(data)

        except ValueError as error:
            self._show_send_error(str(error))
        except RuntimeError as error:
            # CommandSender.send 抛的 "请先开始监控串口后再发送" 等，以友好提示呈现
            self._show_send_error(str(error))
        except Exception as error:
            self._show_send_error(f"发送失败：{error}")

    def _send_command_library_row(self, row: int) -> None:
        """指令库行发送入口：只认当前行的 CMD 类型，不依赖主界面/分段模式。"""
        item = self._command_item_for_row(row)
        if not item:
            return

        payload = str(
            item.get(
                "payload",
                item.get("data", ""),
            )
        ).strip()

        command_type = str(
            item.get(
                "type",
                item.get("cmd_type", ""),
            )
        ).strip().upper()

        if not payload:
            return

        if command_type not in {"HEX", "ASCII"}:
            self._show_send_error(f"不支持的指令类型：{command_type}")
            return

        self._send_library_payload(
            payload=payload,
            command_type=command_type,
        )

    def _cmdlib_send_index(self, index: int) -> None:
        self._send_command_library_row(index)

    def _cmdlib_send_item(self, item: dict[str, Any]) -> None:
        """循环发送仍然走行数据中的 type 字段。"""
        try:
            payload = str(
                item.get("payload", item.get("data", ""))
            ).strip()
            command_type = str(
                item.get(
                    "type",
                    item.get("cmd_type", self.cmdlib_mode.upper()),
                )
            ).strip().upper()
            if command_type not in {"HEX", "ASCII"}:
                command_type = self.cmdlib_mode.upper()
            self._send_library_payload(payload=payload, command_type=command_type)
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
        """配置循环发送：可拖动调整发送顺序，间隔用普通 QLineEdit+QIntValidator（无上下箭头）。

        最终保存的 ``steps`` 列表顺序与用户拖动后一致，循环发送严格按此顺序执行。

        关键修复：
        * 拖动期间禁止直接重建 / setRowCount / clearContents（Qt 拖放栈未结束会崩溃）
        * rowsReordered 通过 ReorderableCycleTable 中 QTimer.singleShot(0) 延迟发出，
          收到信号后才先 collect → 改 cycle_items → rebuild 表格
        * checkbox / interval 回调全部绑定稳定 command_id，不再捕获 row（拖动后 row 变化）
        """
        items = self._cmdlib_items()
        if not items:
            QMessageBox.information(self, "配置循环", "当前指令库为空。")
            return

        # ------------------------------------------------------------
        # 1) 构造后台顺序列表（带稳定 id + enabled + interval）
        # ------------------------------------------------------------
        enabled_map: dict[str, dict[str, Any]] = {}
        cycle_ordered: list[dict[str, Any]] = []
        for step in self.command_library.cycle(self.cmdlib_mode):
            item_id = str(step.get("id", "")).strip()
            if not item_id:
                continue
            entry = {
                "id": item_id,
                "enabled": True,
                "name": "",
                "interval_ms": int(step.get("delay_ms", 1000)),
                "item": None,
            }
            cycle_ordered.append(entry)
            enabled_map[item_id] = entry

        by_id = {str(item["id"]): item for item in items}
        for item in items:
            item_id = str(item["id"])
            if item_id in enabled_map:
                enabled_map[item_id]["name"] = str(item.get("name", "")).strip() or "(未命名)"
                enabled_map[item_id]["item"] = item
            else:
                cycle_ordered.append(
                    {
                        "id": item_id,
                        "enabled": False,
                        "name": str(item.get("name", "")).strip() or "(未命名)",
                        "interval_ms": 1000,
                        "item": item,
                    }
                )
        cycle_ordered = [row for row in cycle_ordered if row.get("item") is not None]

        # 提升为临时实例属性：拖动信号回调、collect、rebuild 都只依赖它们，不再靠闭包捕获 row
        self._cycle_items: list[dict[str, Any]] = cycle_ordered
        self._cycle_controls: list[tuple[QCheckBox, QLineEdit, dict[str, Any]]] = []
        self._cycle_reordering = False

        dialog = QDialog(self)
        dialog.setWindowTitle(f"配置循环 - {self.cmdlib_mode.upper()}")
        dialog.resize(560, 500)
        root = QVBoxLayout(dialog)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        hint = QLabel("提示：鼠标选中左侧 ☰ 列或整行空白区域拖动可调整发送顺序。", dialog)
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        root.addWidget(hint)

        # ------------------------------------------------------------
        # 2) 构建可拖动表格（4 列：☰ | 启用 | 名称 | 间隔(ms)）
        # ------------------------------------------------------------
        self._cycle_table = ReorderableCycleTable(dialog)
        self._cycle_table.setColumnCount(4)
        self._cycle_table.setHorizontalHeaderLabels(["", "启用", "名称", "间隔(ms)"])
        self._cycle_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._cycle_table.verticalHeader().setDefaultSectionSize(34)
        self._cycle_table.verticalHeader().setMinimumSectionSize(34)
        hdr = self._cycle_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._cycle_table.setColumnWidth(0, 28)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._cycle_table.setColumnWidth(1, 60)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._cycle_table.setColumnWidth(3, 150)

        root.addWidget(self._cycle_table, 1)

        # rowsReordered 已经由 ReorderableCycleTable 通过 QTimer.singleShot(0) 延后发出，
        # 这里直接改后台 list + rebuild 即可，不再额外用 singleShot 包一层。
        self._cycle_table.rowsReordered.connect(self._on_cycle_rows_reordered)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        # 首次构建
        self._rebuild_cycle_table(select_row=None)

        accepted = dialog.exec() == QDialog.DialogCode.Accepted

        # 无论是否 OK，最后都清理临时实例属性，避免跨窗口串数据
        try:
            if accepted:
                self._collect_cycle_table_values()
                steps = [
                    {"id": entry["id"], "delay_ms": int(entry.get("interval_ms", 1000))}
                    for entry in self._cycle_items
                    if bool(entry.get("enabled", False)) and str(entry.get("id", "")).strip()
                ]
                try:
                    self.command_library.set_cycle(self.cmdlib_mode, steps)
                except CommandLibraryError as error:
                    QMessageBox.warning(self, "保存失败", str(error))
        finally:
            for attr in ("_cycle_items", "_cycle_controls", "_cycle_table", "_cycle_reordering"):
                try:
                    delattr(self, attr)
                except AttributeError:
                    pass

    # ------------------------------------------------------------------
    # Cycle configure helpers（仅在 _cmdlib_open_cycle_config 生命周期内有效）
    # ------------------------------------------------------------------
    def _cycle_row_by_id(self, command_id: str) -> dict[str, Any] | None:
        command_id = str(command_id).strip()
        for entry in getattr(self, "_cycle_items", []):
            if str(entry.get("id", "")).strip() == command_id:
                return entry
        return None

    def _collect_cycle_table_values(self) -> None:
        """OK 保存前 / 拖动重排前：把表格最新 checkbox + 输入框值写回 _cycle_items。

        始终以稳定 id 定位条目，绝不依赖当前行号（拖动后行号会变）。
        """
        controls = getattr(self, "_cycle_controls", [])
        for check, edit, entry in controls:
            command_id = str(entry.get("id", "")).strip()
            target = self._cycle_row_by_id(command_id)
            if target is None:
                continue
            target["enabled"] = bool(check.isChecked())
            target["interval_ms"] = self._clamp_cycle_interval(edit.text())

    def _rebuild_cycle_table(self, select_row: int | None = None) -> None:
        """按 self._cycle_items 重建整个表格。

        关键：
        * 在 setUpdatesEnabled(False) 期间用 QSignalBlocker 屏蔽表格信号，
          防止 clearContents/setRowCount/setCellWidget 过程中再次触发 itemChanged
          / rowsReordered / editingFinished 回写 list 造成递归或悬空 C++ 对象。
        * dropEvent 已经用 singleShot(0) 延后，这里是在 Qt 拖放事件栈完全结束后执行。
        """
        table = getattr(self, "_cycle_table", None)
        cycle_items = getattr(self, "_cycle_items", None)
        if table is None or cycle_items is None:
            return
        row_count = max(0, int(len(cycle_items)))

        blocker = QSignalBlocker(table)  # noqa: F841
        table.setUpdatesEnabled(False)
        try:
            # 先把现有 cellWidget 从表格上摘掉（与 clearContents 顺序：先摘再清，降低崩溃概率）
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    widget = table.cellWidget(row, col)
                    if widget is not None:
                        widget.setParent(None)
            table.clearContents()
            table.setRowCount(row_count)

            new_controls: list[tuple[QCheckBox, QLineEdit, dict[str, Any]]] = []
            for row_idx, entry in enumerate(cycle_items):
                command_id = str(entry.get("id", "")).strip()
                name = str(entry.get("name", "")).strip()

                handle = QLabel("☰", table)
                handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
                handle.setStyleSheet(f"color: {TEXT_MUTED};")
                table.setCellWidget(row_idx, 0, handle)

                check = QCheckBox(table)
                check.setChecked(bool(entry.get("enabled", False)))
                # 回调绑定稳定 command_id，不是 row_idx
                check.toggled.connect(
                    lambda _checked=False, cid=command_id, widget=check:
                        self._set_cycle_enabled(cid, widget.isChecked())
                )
                table.setCellWidget(row_idx, 1, check)

                name_item = QTableWidgetItem(name)
                # 名称列只展示，不编辑
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                name_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                table.setItem(row_idx, 2, name_item)

                interval_edit = QLineEdit(str(int(entry.get("interval_ms", 1000))), table)
                interval_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                interval_edit.setValidator(QIntValidator(1, 100_000, interval_edit))
                interval_edit.setFixedHeight(CONTROL_HEIGHT)
                # 同样绑定稳定 command_id
                interval_edit.editingFinished.connect(
                    lambda cid=command_id, edit=interval_edit:
                        self._save_cycle_interval_by_id(cid, edit)
                )
                table.setCellWidget(row_idx, 3, interval_edit)

                new_controls.append((check, interval_edit, entry))
            self._cycle_controls = new_controls
        finally:
            table.setUpdatesEnabled(True)
            # QSignalBlocker 离开作用域自动解除；显式 del 提醒生命周期
            del blocker
        table.viewport().update()
        if select_row is not None and 0 <= int(select_row) < table.rowCount():
            table.selectRow(int(select_row))

    def _on_cycle_rows_reordered(self, source_row: int, target_row: int) -> None:
        """收到延后 rowsReordered 后：collect → 改 _cycle_items → rebuild。"""
        if bool(getattr(self, "_cycle_reordering", False)):
            return
        items_list = getattr(self, "_cycle_items", None)
        if items_list is None:
            return
        source_row = int(source_row)
        target_row = int(target_row)
        total = len(items_list)
        if not (0 <= source_row < total and 0 <= target_row < total) or source_row == target_row:
            return
        self._cycle_reordering = True
        try:
            # 先把未失焦的编辑值/勾选状态回写 _cycle_items（按 id 匹配，顺序无影响）
            self._collect_cycle_table_values()
            moved = items_list.pop(source_row)
            items_list.insert(target_row, moved)
            self._rebuild_cycle_table(select_row=target_row)
        finally:
            self._cycle_reordering = False

    def _set_cycle_enabled(self, command_id: str, enabled: bool) -> None:
        """用户勾选/取消启用；回调绑定稳定 command_id，不依赖当前 row。"""
        if bool(getattr(self, "_cycle_reordering", False)):
            return
        target = self._cycle_row_by_id(command_id)
        if target is None:
            return
        target["enabled"] = bool(enabled)

    def _save_cycle_interval_by_id(self, command_id: str, edit: QLineEdit) -> None:
        """用户完成间隔输入；回调绑定稳定 command_id，拖动顺序变化后仍写到正确指令。"""
        if bool(getattr(self, "_cycle_reordering", False)):
            return
        target = self._cycle_row_by_id(command_id)
        if target is None:
            return
        value = self._clamp_cycle_interval(edit.text())
        edit.setText(str(value))
        target["interval_ms"] = value

    @staticmethod
    def _clamp_cycle_interval(text: object) -> int:
        try:
            value = int(str(text).strip())
        except (TypeError, ValueError):
            value = 1000
        return max(1, min(100_000, value))

    def _save_cycle_interval(
        self,
        rows: list[dict[str, Any]],
        row: int,
        edit: QLineEdit,
    ) -> None:
        """兼容旧调用路径：保留基于 row 的保存入口（内部转为 id 匹配更安全）。

        说明：当前新代码已经改用按 id 的 ``_save_cycle_interval_by_id``，本方法
        仅兜底保留，避免外部或遗留引用再次调用时报 AttributeError。
        """
        if bool(getattr(self, "_cycle_reordering", False)):
            return
        try:
            entry = rows[int(row)]
            command_id = str(entry.get("id", "")).strip()
        except (LookupError, TypeError, ValueError):
            return
        if command_id:
            self._save_cycle_interval_by_id(command_id, edit)
        else:
            value = self._clamp_cycle_interval(edit.text())
            edit.setText(str(value))
            try:
                rows[int(row)]["interval_ms"] = value
            except (LookupError, TypeError):
                pass

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
