import json
import os
import subprocess
import sys
import time
import customtkinter as ctk
from tkinter import ttk, filedialog, messagebox
from .components import (
    Card,
    Btn,
    IconBtn,
    Label,
    setup_tree_style,
    NavActionButton,
    ReadOnlyDropdown,
    EditableBaudDropdown,
    COMMON_BAUD_RATES,
    apply_global_font,
    BLUE,
    GREEN,
    RED,
    FONT_SMALL,
    FONT_NORMAL,
    FONT_TITLE,
    FONT_LARGE,
    HEIGHT_HEADER,
)
from protocol_parser.protocol_manager import ProtocolManager
from protocol_parser import (
    FrameSynchronizer,
    ResultLogger,
    ParseResult,
    ProtocolError,
    classify_protocol_error,
    to_hex,
)
from storage import RawDataSaver

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
COMMANDS_JSON = os.path.join(DATA_DIR, "commands.json")

# 统一左侧内容对齐基准（与"实时数据"文字左边缘对齐）
# 右侧保持与卡片边距一致
LEFT_CONTENT_PADDING = 28
RIGHT_CONTENT_PADDING = 17


class SerialApp(ctk.CTk):

    def _build_ui(self):
        """
        兼容当前安装的 CustomTkinter。

        CTk.__init__() 会在 super().__init__() 期间调用 self._build_ui()。
        此时应用自身的属性还未初始化，因此这里只保留空实现。
        真正的应用界面由 __init__() 中的 self._build_app_ui() 构建。
        """
        return None

    def __init__(
        self,
        initial_port=None,
        initial_baud="9600",
    ):
        super().__init__()
        self.title("串口协议解析工具 v1.2.0")
        self.geometry("1440x900")
        self.minsize(1280, 780)

        # 预设串口/波特率，必须在构建界面之前赋值
        self.initial_port = initial_port
        self.initial_baud = str(initial_baud)

        self.library_visible = False
        self.send_visible = False
        self.auto_scroll = True
        self.hex_mode = True
        self.monitoring = False
        self.selected_command_index = None
        # True=协议解析模式(绿底白字, 显示协议控件)
        # False=原始数据模式(白底黑字, 隐藏协议控件)
        self.parse_mode = True

        # 显示名称 -> 真实端口(COM 号)的映射
        # 下拉框显示 display_name，连接时通过它取出真实 device 传给 pyserial
        self.port_display_map = {}

        # 协议管理器和帧同步器
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        builtin_dir = os.path.join(project_root, "product")
        user_proto_dir = os.path.join(project_root, "data", "protocols", "imported")
        self.protocol_manager = ProtocolManager(builtin_dir, user_proto_dir)
        self.protocol_manager.load_builtin_protocols()

        self.frame_synchronizer = None
        self.result_logger = None

        # 原始数据保存器（后台线程写文件）
        self.raw_saver = RawDataSaver(
            error_callback=self._on_storage_error
        )

        self._init_workers()
        self._build_app_ui()
        self._load_commands()

        # 默认选择串口3.0协议并创建帧同步器
        try:
            self.protocol_manager.select("串口3.0协议")
            self.frame_synchronizer = self.protocol_manager.create_synchronizer()
        except Exception:
            pass

        # 注册窗口关闭事件，安全释放所有资源
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        apply_global_font(self)

    def _init_workers(self):
        try:
            from serial_core.serial_worker import SerialWorker
            self.worker = SerialWorker(callback=self._on_serial_data)
        except Exception:
            self.worker = None

    def _build_app_ui(self):
        self._build_root()
        self._build_nav()
        self._build_config()

        # 状态栏始终固定在最底部
        self._build_statusbar()

        # 状态栏上方的全部可变内容
        self._build_workspace()

        # 所有控件创建完成后统一应用初始状态
        self._apply_initial_panel_state()

    # ─────────────────────────────────────────────────────────────────
    # ROOT
    # ─────────────────────────────────────────────────────────────────
    def _build_root(self):
        self.root = ctk.CTkFrame(self, fg_color="#f0f2f5")
        self.root.pack(fill="both", expand=True)

    # ─────────────────────────────────────────────────────────────────
    # NAVIGATION
    # ─────────────────────────────────────────────────────────────────
    def _build_nav(self):
        nav = ctk.CTkFrame(
            self.root,
            fg_color="white",
            height=HEIGHT_HEADER,
            corner_radius=12,
        )
        nav.pack(fill="x", padx=10, pady=(7, 2))
        nav.pack_propagate(False)

        ctk.CTkLabel(
            nav,
            text="⚙  串口配置",
            text_color="#202124",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=(16, 10))

        self.nav_send_button = NavActionButton(
            nav,
            text="➤  发送界面",
            mode="toggle",
            width=115,
            height=HEIGHT_HEADER,
            initial_active=False,
            command=self.toggle_send,
        )
        self.nav_send_button.pack(side="left", fill="y")

        self.nav_library_button = NavActionButton(
            nav,
            text="◇  发送指令库",
            mode="toggle",
            width=135,
            height=HEIGHT_HEADER,
            initial_active=False,
            command=self.toggle_library,
        )
        self.nav_library_button.pack(side="left", fill="y")

        self.nav_add_button = NavActionButton(
            nav,
            text="+  添加串口",
            mode="action",
            width=110,
            height=HEIGHT_HEADER,
            command=self._open_add_serial_dialog,
        )
        self.nav_add_button.pack(side="left", fill="y")

        self.nav_save_button = NavActionButton(
            nav,
            text="▤  保存日志",
            mode="action",
            width=110,
            height=HEIGHT_HEADER,
            command=self._open_save_log_dialog,
        )
        self.nav_save_button.pack(side="left", fill="y")

        self.nav_topmost_button = NavActionButton(
            nav,
            text="☆  置顶",
            mode="toggle",
            width=90,
            height=HEIGHT_HEADER,
            command=self._toggle_topmost,
        )
        self.nav_topmost_button.pack(side="left", fill="y")

    # ─────────────────────────────────────────────────────────────────
    # CONFIG CARD
    # ─────────────────────────────────────────────────────────────────
    def _build_config(self):
        self.config_expanded = True

        CONTROL_HEIGHT = 30
        CONFIG_HEADER_HEIGHT = 46

        self.serial_config_card = Card(self.root)
        self.serial_config_card.pack(fill="x", padx=10, pady=4)

        # ── Header (always visible) ──
        self.serial_config_header = ctk.CTkFrame(
            self.serial_config_card,
            fg_color="transparent",
            height=CONFIG_HEADER_HEIGHT,
        )
        self.serial_config_header.pack(
            fill="x",
            padx=(LEFT_CONTENT_PADDING, RIGHT_CONTENT_PADDING),
            pady=(8, 8),
        )
        self.serial_config_header.pack_propagate(False)

        # 中间空白列自动扩展，把右侧按钮推到最右边
        self.serial_config_header.grid_columnconfigure(5, weight=1)
        self.serial_config_header.grid_rowconfigure(0, weight=1)

        Label(
            self.serial_config_header, "串口", width=50, height=CONTROL_HEIGHT,
        ).grid(row=0, column=0, sticky="nsw", padx=(0, 8))

        # 先扫描端口，再根据传入的真实 COM 号反查显示名称
        port_values = self._scan_ports()

        initial_display = None
        if self.initial_port:
            for display_name, device in self.port_display_map.items():
                if device == self.initial_port:
                    initial_display = display_name
                    break

        if initial_display is None:
            initial_display = (
                port_values[0]
                if port_values
                else "未检测到串口"
            )

        self.com_port = ReadOnlyDropdown(
            self.serial_config_header, values=port_values,
            width=420, height=CONTROL_HEIGHT,
            default=initial_display,
        )
        self.com_port.grid(row=0, column=1, sticky="ns")

        Btn(
            self.serial_config_header, "刷新", width=60, height=CONTROL_HEIGHT,
            command=self._refresh_ports,
        ).grid(row=0, column=2, sticky="ns", padx=8)

        Label(
            self.serial_config_header, "波特率", width=50, height=CONTROL_HEIGHT,
        ).grid(row=0, column=3, sticky="nsw", padx=(18, 8))

        # 允许传入自定义波特率（不在常用列表中也可），只要为正整数即可
        initial_baud = (
            self.initial_baud.strip()
            if str(self.initial_baud).strip().isdigit()
            else "9600"
        )

        self.baud_cb = EditableBaudDropdown(
            self.serial_config_header,
            values=COMMON_BAUD_RATES,
            width=140, height=CONTROL_HEIGHT, default=initial_baud,
        )
        self.baud_cb.grid(row=0, column=4, sticky="ns")

        self.monitor_btn = Btn(
            self.serial_config_header, "开始监控 ▶", color="blue",
            width=110, height=CONTROL_HEIGHT, command=self._toggle_monitor,
        )
        self.monitor_btn.grid(row=0, column=6, sticky="nse")

        self.collapse_button = Btn(
            self.serial_config_header, "收起 ▲", color="red",
            width=90, height=CONTROL_HEIGHT, command=self._toggle_cfg,
        )
        self.collapse_button.grid(row=0, column=7, sticky="nse", padx=(8, 0))

        Btn(
            self.serial_config_header, "HEX 格式", color="green",
            width=90, height=CONTROL_HEIGHT, command=self._toggle_hex,
        ).grid(row=0, column=8, sticky="nse", padx=(8, 0))

        # ── Body (rows 2-3, collapsible) ──
        self.serial_config_body = ctk.CTkFrame(self.serial_config_card, fg_color="transparent")
        self.serial_config_body.pack(
            fill="x",
            padx=(LEFT_CONTENT_PADDING, RIGHT_CONTENT_PADDING),
            pady=(0, 14),
        )

        # Row 2
        r2 = ctk.CTkFrame(self.serial_config_body, fg_color="transparent")
        r2.pack(fill="x", pady=6)

        Label(r2, "数据位", width=50).pack(side="left", padx=(0, 8))
        self.data_bits_cb = ReadOnlyDropdown(
            r2, values=["5", "6", "7", "8"], width=70, default="8"
        )
        self.data_bits_cb.pack(side="left", padx=(0, 24))

        Label(r2, "停止位", width=50).pack(side="left", padx=(0, 8))
        self.stop_bits_cb = ReadOnlyDropdown(
            r2, values=["1", "1.5", "2"], width=70, default="1"
        )
        self.stop_bits_cb.pack(side="left", padx=(0, 24))

        Label(r2, "文件名", width=50).pack(side="left", padx=(0, 8))
        self.filename_entry = ctk.CTkEntry(
            r2, width=340, height=30, fg_color="white",
            border_color="#d1d5db", text_color="#1f2937"
        )
        self.filename_entry.insert(0, "serial_data_20260731,033058")
        self.filename_entry.pack(side="left")

        Label(r2, "(.dat 格式，超过 50MB 自动分割)",
              text_color="#9ca3af", font=FONT_NORMAL).pack(side="left", padx=8)

        # Row 3
        r3 = ctk.CTkFrame(self.serial_config_body, fg_color="transparent")
        r3.pack(fill="x", pady=6)

        self.storage_btn = Btn(r3, "开始存储数据", color="blue", width=110, height=28,
                                command=self._toggle_storage)
        self.storage_btn.pack(side="left")

        Label(r3, "路径", width=50).pack(side="left", padx=(18, 8))
        self.path_entry = ctk.CTkEntry(
            r3, height=30, fg_color="white",
            border_color="#d1d5db", text_color="#1f2937"
        )
        self.path_entry.insert(
            0, r"D:\测试\工具\串口解析\Serial-port-data-parsing\data"
        )
        self.path_entry.pack(side="left", fill="x", expand=True)

        Btn(r3, "选择", width=60, height=28,
            command=self._choose_folder).pack(side="left", padx=(8, 0))

    # ─────────────────────────────────────────────────────────────────
    # WORKSPACE  (main_area + send_panel，统一使用 grid)
    # ─────────────────────────────────────────────────────────────────
    def _build_workspace(self):
        self.workspace = ctk.CTkFrame(
            self.root,
            fg_color="transparent",
        )
        self.workspace.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=4,
        )

        # 第0行是中间主体，自动占满剩余空间
        self.workspace.grid_rowconfigure(0, weight=1)
        # 第1行是发送界面，按内容高度显示
        self.workspace.grid_rowconfigure(1, weight=0)
        self.workspace.grid_columnconfigure(0, weight=1)

        self._build_main(self.workspace)
        self._build_send_area(self.workspace)

    # ─────────────────────────────────────────────────────────────────
    # MAIN AREA  (left: receive / right: library)
    # ─────────────────────────────────────────────────────────────────
    def _build_main(self, parent):
        self.main_area = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        self.main_area.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(1, weight=0)

        self._build_receive_panel(self.main_area)
        self._build_library_panel(self.main_area)

    # ─────────────────────────────────────────────────────────────────
    # RECEIVE PANEL (left)
    # ─────────────────────────────────────────────────────────────────
    def _build_receive_panel(self, parent):
        self.receive = Card(parent)
        self.receive.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        # 工具栏固定高度，禁止子控件撑大
        TOOLBAR_HEIGHT = 40
        CONTROL_HEIGHT = 28

        tb = ctk.CTkFrame(
            self.receive,
            fg_color="transparent",
            height=TOOLBAR_HEIGHT,
            corner_radius=0,
        )
        tb.pack(
            fill="x",
            padx=(LEFT_CONTENT_PADDING, RIGHT_CONTENT_PADDING),
            pady=(6, 6),
        )

        # 关键：禁止子控件改变工具栏高度
        tb.pack_propagate(False)

        self.receive_toolbar = tb

        # 实时数据 (label)
        # anchor="w" 确保文字在 80px 宽度内左对齐，作为左侧对齐基准
        ctk.CTkLabel(
            tb, text="实时数据", font=FONT_TITLE,
            text_color="#111827", width=80, height=CONTROL_HEIGHT,
            anchor="w",
        ).pack(side="left", pady=6)

        # 协议解析模式按钮：初始绿底白字（协议解析模式）
        self.btn_parse_mode = Btn(
            tb, "协议解析模式", color="green",
            width=110, height=CONTROL_HEIGHT,
            command=self._toggle_parse_mode,
        )
        self.btn_parse_mode.pack(side="left", padx=2, pady=6)

        Btn(
            tb, "清空", width=60, height=CONTROL_HEIGHT,
            command=self._clear_rx,
        ).pack(side="left", padx=2, pady=6)

        self.btn_auto_scroll = Btn(
            tb, "自动滚动", color="green",
            width=80, height=CONTROL_HEIGHT,
            command=self._toggle_auto_scroll,
        )
        self.btn_auto_scroll.pack(side="left", padx=2, pady=6)

        # 固定尺寸的协议控件槽位：无论内部内容是否显示，槽位尺寸都不变化
        self.protocol_controls_slot = ctk.CTkFrame(
            tb,
            width=530,
            height=CONTROL_HEIGHT,
            fg_color="transparent",
            corner_radius=0,
        )
        self.protocol_controls_slot.pack(
            side="left",
            padx=(10, 0),
            pady=6,
        )
        self.protocol_controls_slot.pack_propagate(False)

        # 协议控件实际容器，使用 place 放在槽位内，切换时只 place / place_forget
        self.protocol_controls_frame = ctk.CTkFrame(
            self.protocol_controls_slot,
            fg_color="transparent",
            corner_radius=0,
            width=530,
            height=CONTROL_HEIGHT,
        )
        self.protocol_controls_frame.place(x=0, y=0)

        ctk.CTkLabel(
            self.protocol_controls_frame,
            text="产品协议:",
            font=FONT_NORMAL,
            text_color="#374151",
            height=CONTROL_HEIGHT,
        ).pack(side="left", padx=(0, 4))

        self.product_proto_combo = ReadOnlyDropdown(
            self.protocol_controls_frame,
            values=self.protocol_manager.available_protocols() or ["串口3.0协议"],
            width=150, height=CONTROL_HEIGHT, default="串口3.0协议",
            command=self._on_protocol_selected,
        )
        self.product_proto_combo.pack(side="left", padx=2)

        self.import_protocol_btn = Btn(
            self.protocol_controls_frame, "导入Word协议",
            width=110, height=CONTROL_HEIGHT, command=self._import_word_protocol,
        )
        self.import_protocol_btn.pack(side="left", padx=2)

        self.view_protocol_btn = Btn(
            self.protocol_controls_frame, "查看协议",
            width=80, height=CONTROL_HEIGHT, command=self._view_current_protocol,
        )
        self.view_protocol_btn.pack(side="left", padx=2)

        self.btn_module_send = Btn(
            self.protocol_controls_frame, "模组发送", color="green",
            width=80, height=CONTROL_HEIGHT, command=self._module_send,
        )
        self.btn_module_send.pack(side="left", padx=2)

        # Big display area
        self.rxbox_frame = ctk.CTkFrame(self.receive, fg_color="#f8fafc", corner_radius=12)
        self.rxbox_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Icon + placeholder text
        self.rx_placeholder = ctk.CTkFrame(self.rxbox_frame, fg_color="transparent")
        self.rx_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            self.rx_placeholder, text="🗂", font=ctk.CTkFont(size=64),
            text_color="#cbd5e1"
        ).pack(pady=(0, 10))

        ctk.CTkLabel(
            self.rx_placeholder, text="等待接收数据...",
            font=ctk.CTkFont(size=14), text_color="#94a3b8"
        ).pack()

        # Text data area (initially hidden)
        self.rxbox = ctk.CTkTextbox(
            self.rxbox_frame, fg_color="white", corner_radius=12,
            border_width=1, border_color="#e2e8f0",
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none"
        )
        self.rxbox.pack(fill="both", expand=True, padx=0, pady=0)
        self.rxbox.pack_propagate(False)
        self.rxbox.place_forget()  # Hidden until data arrives

    # ─────────────────────────────────────────────────────────────────
    # LIBRARY PANEL (right)
    # ─────────────────────────────────────────────────────────────────
    def _build_library_panel(self, parent):
        self.library = Card(parent, width=440)
        self.library.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.library.grid_propagate(False)

        # Toolbar
        tb = ctk.CTkFrame(self.library, fg_color="transparent")
        tb.pack(fill="x", padx=8, pady=(10, 6))

        ctk.CTkLabel(
            tb, text="指令库",
            text_color="#202124",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        ).pack(side="left", padx=(12, 10), pady=8)

        Btn(tb, "HEX", color="blue", width=50, height=28).pack(side="left", padx=3)
        Btn(tb, "循环发送", width=70, height=28).pack(side="left", padx=3)
        Btn(tb, "配置循环", width=70, height=28).pack(side="left", padx=3)
        Btn(tb, "清空选中", width=70, height=28).pack(side="left", padx=3)
        Btn(tb, "新增", width=50, height=28, command=self._add_command).pack(side="left", padx=3)

        # Table
        table_frame = ctk.CTkFrame(self.library, fg_color="transparent")
        table_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        setup_tree_style()

        columns = ("序号", "名称", "CMD类型", "指令数据", "操作")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            style="Custom.Treeview", height=14
        )

        self.tree.heading("序号", text="序号")
        self.tree.heading("名称", text="名称")
        self.tree.heading("CMD类型", text="CMD类型")
        self.tree.heading("指令数据", text="指令数据")
        self.tree.heading("操作", text="操作")

        self.tree.column("序号", width=50, anchor="center")
        self.tree.column("名称", width=70, anchor="center")
        self.tree.column("CMD类型", width=70, anchor="center")
        self.tree.column("指令数据", width=90, anchor="center")
        self.tree.column("操作", width=130, anchor="center", stretch=False)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-1>", self._on_tree_click)

    # ─────────────────────────────────────────────────────────────────
    # SEND AREA (bottom)
    # ─────────────────────────────────────────────────────────────────
    def _build_send_area(self, parent):
        self.send = Card(parent, height=300)
        self.send.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.send.grid_propagate(False)

        self._build_send_left(self.send)
        self._build_send_middle(self.send)
        self._build_send_right(self.send)

    def _build_send_left(self, parent):
        left = ctk.CTkFrame(parent, fg_color="transparent", width=140)
        left.pack(
            side="left", fill="y",
            padx=(LEFT_CONTENT_PADDING, 4), pady=12,
        )
        left.pack_propagate(False)

        Label(
            left, "指令发送模式",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 10))

        self.btn_send_mode_hex = Btn(left, "协议模式", color="blue", width=110, height=30,
                                     command=lambda: self._set_send_mode("protocol"))
        self.btn_send_mode_hex.pack(anchor="w", pady=3)

        Btn(left, "HEX", width=110, height=30,
            command=lambda: self._set_send_mode("hex")).pack(anchor="w", pady=3)

        Btn(left, "ASCII", width=110, height=30,
            command=lambda: self._set_send_mode("ascii")).pack(anchor="w", pady=3)

    def _build_send_middle(self, parent):
        center = ctk.CTkFrame(parent, fg_color="transparent")
        center.pack(side="left", fill="both", expand=True, padx=4, pady=10)

        # Left sub - form fields
        form = ctk.CTkFrame(center, fg_color="transparent")
        form.pack(side="left", fill="y", padx=(0, 8), pady=0)

        Label(form, "协议参数", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        Label(form, "命令:", width=60).grid(row=1, column=0, sticky="w", padx=(0, 4), pady=3)
        self.cmd_combo = ReadOnlyDropdown(
            form, values=["0x20 心跳检测", "0x30 状态查询", "0x40 配置写入"],
            width=200, default="0x20 心跳检测"
        )
        self.cmd_combo.grid(row=1, column=1, columnspan=3, sticky="w", pady=3)

        Label(form, "快捷动作:", width=60).grid(row=2, column=0, sticky="w", padx=(0, 4), pady=3)
        self.quick_action_cb = ReadOnlyDropdown(
            form, values=["无", "快速启动", "快速停止"],
            width=200, default="无"
        )
        self.quick_action_cb.grid(row=2, column=1, columnspan=3, sticky="w", pady=3)

        Label(form, "方向:", width=60).grid(row=3, column=0, sticky="w", padx=(0, 4), pady=3)
        self.direction_cb = ReadOnlyDropdown(
            form, values=["模组发送", "主机发送", "双向"],
            width=200, default="模组发送"
        )
        self.direction_cb.grid(row=3, column=1, columnspan=3, sticky="w", pady=3)

        # Right sub - protocol attributes table
        attr_frame = ctk.CTkFrame(center, fg_color="transparent")
        attr_frame.pack(side="left", fill="both", expand=True, pady=0)

        Label(attr_frame, "协议属性:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 8))

        attr_cols = ("参数名称", "方向", "当前值", "说明/解析")
        attr_tree = ttk.Treeview(
            attr_frame, columns=attr_cols, show="headings",
            style="Custom.Treeview", height=3
        )
        for c, w in zip(attr_cols, [80, 50, 80, 140]):
            attr_tree.heading(c, text=c)
            attr_tree.column(c, width=w, anchor="center")

        attr_data = [
            ("heartbeat", "RX", "0x20", "心跳响应"),
            ("status", "TX", "0x01", "状态字节"),
            ("data_len", "RX", "N", "数据长度"),
        ]
        for row in attr_data:
            attr_tree.insert("", "end", values=row)

        attr_tree.pack(fill="x", pady=(0, 10))

        # JSON area
        Label(attr_frame, "字段 JSON:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 4))
        self.json_text = ctk.CTkTextbox(
            attr_frame, height=55, fg_color="white",
            border_color="#d1d5db", corner_radius=12,
            font=FONT_SMALL
        )
        self.json_text.pack(fill="x")
        self.json_text.insert("0.0", '{\n  "heartbeat": "0x20",\n  "status": "0x01",\n  "data": []\n}')

    def _build_send_right(self, parent):
        right = ctk.CTkFrame(parent, fg_color="transparent", width=260)
        right.pack(side="right", fill="y", padx=(4, 14), pady=12)
        right.pack_propagate(False)

        Label(right, "发送操作", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 10))

        # Row 1: 发送 / 清空 / 加回车
        r1 = ctk.CTkFrame(right, fg_color="transparent")
        r1.pack(fill="x", pady=3)
        Btn(r1, "发送", color="blue", width=70, height=30,
            command=self._send_data).pack(side="left", padx=(0, 4))
        Btn(r1, "清空输入", width=80, height=30,
            command=self._clear_input).pack(side="left", padx=4)
        Btn(r1, "加回车换行", width=90, height=30).pack(side="left", padx=(4, 0))

        # Row 2: 校验位
        r2 = ctk.CTkFrame(right, fg_color="transparent")
        r2.pack(fill="x", pady=8)
        Btn(r2, "自动追加校验位", width=110, height=28).pack(side="left", padx=(0, 4))
        self.add8_cb = ReadOnlyDropdown(
            r2, values=["ADD8", "CRC16", "XOR"],
            width=90, default="ADD8"
        )
        self.add8_cb.pack(side="left", padx=4)

        # Row 3: 自动发送
        r3 = ctk.CTkFrame(right, fg_color="transparent")
        r3.pack(fill="x", pady=3)
        Btn(r3, "自动发送", width=70, height=28).pack(side="left", padx=(0, 4))

        ctk.CTkLabel(r3, text="间隔(ms)", font=ctk.CTkFont(size=13),
                     text_color="#374151").pack(side="left", padx=4)

        self.interval_var = ctk.StringVar(value="1000")
        interval_entry = ctk.CTkEntry(
            r3, width=70, height=28, fg_color="white",
            border_color="#d1d5db", text_color="#1f2937",
            textvariable=self.interval_var, justify="center"
        )
        interval_entry.pack(side="left", padx=4)

    # ─────────────────────────────────────────────────────────────────
    # STATUSBAR
    # ─────────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        self.statusbar = ctk.CTkFrame(self.root, fg_color="white", height=36)
        self.statusbar.pack(side="bottom", fill="x", padx=10, pady=(4, 8))
        self.statusbar.pack_propagate(False)

        # Left
        left = ctk.CTkFrame(self.statusbar, fg_color="transparent")
        left.pack(side="left", fill="y", padx=18)

        ctk.CTkLabel(
            left, text="●", font=ctk.CTkFont(size=14),
            text_color=GREEN
        ).pack(side="left", padx=(0, 12))

        self.lbl_com = ctk.CTkLabel(
            left, text="COM3", font=ctk.CTkFont(size=12),
            text_color="#374151"
        )
        self.lbl_com.pack(side="left", padx=(0, 16))

        self.lbl_baud = ctk.CTkLabel(
            left, text="9600", font=ctk.CTkFont(size=12),
            text_color="#374151"
        )
        self.lbl_baud.pack(side="left", padx=(0, 16))

        # 同步预设的串口/波特率到状态栏
        if self.initial_port:
            self.lbl_com.configure(text=self.initial_port)

        # 取与下拉框一致的初始波特率，支持自定义值
        _initial_baud = (
            self.initial_baud.strip()
            if str(self.initial_baud).strip().isdigit()
            else "9600"
        )
        self.lbl_baud.configure(text=_initial_baud)

        self.lbl_storage = ctk.CTkLabel(
            left, text="未存储", font=ctk.CTkFont(size=12),
            text_color="#6b7280"
        )
        self.lbl_storage.pack(side="left", padx=(0, 16))

        self.lbl_lib_status = ctk.CTkLabel(
            left, text="已隐藏指令库", font=ctk.CTkFont(size=12),
            text_color="#6b7280"
        )
        self.lbl_lib_status.pack(side="left")

        # Right
        right = ctk.CTkFrame(self.statusbar, fg_color="transparent")
        right.pack(side="right", fill="y", padx=14)

        self.lbl_rx = ctk.CTkLabel(
            right, text="RX 0", font=ctk.CTkFont(size=12),
            text_color="#374151"
        )
        self.lbl_rx.pack(side="left", padx=(0, 16))

        self.lbl_tx = ctk.CTkLabel(
            right, text="TX 0", font=ctk.CTkFont(size=12),
            text_color="#374151"
        )
        self.lbl_tx.pack(side="left", padx=(0, 16))

        self.lbl_err = ctk.CTkLabel(
            right, text="错误 0", font=ctk.CTkFont(size=12),
            text_color="#374151"
        )
        self.lbl_err.pack(side="left", padx=(0, 16))

        self.lbl_buf = ctk.CTkLabel(
            right, text="缓冲 0B", font=ctk.CTkFont(size=12),
            text_color="#374151"
        )
        self.lbl_buf.pack(side="left")

    # ─────────────────────────────────────────────────────────────────
    # DATA & EVENT HANDLERS
    # ─────────────────────────────────────────────────────────────────
    def _scan_ports(self):
        """扫描串口并刷新 显示名称 -> 真实端口 映射。

        返回值只用于直接喂给下拉框的 ``values``，因此返回的是 display_name 列表。
        真实 COM 号需要通过 ``self.port_display_map`` 取出。
        """
        try:
            from serial_core.serial_worker import SerialWorker

            worker = SerialWorker()
            port_items = worker.scan_ports()

            self.port_display_map = {}

            display_values = []

            for item in port_items:
                display_name = item["display_name"]
                device = item["device"]

                display_values.append(display_name)
                self.port_display_map[display_name] = device

            if not display_values:
                self.port_display_map = {"未检测到串口": ""}
                return ["未检测到串口"]

            return display_values

        except Exception:
            self.port_display_map = {"未检测到串口": ""}
            return ["未检测到串口"]

    def _refresh_ports(self):
        display_values = self._scan_ports()
        self.com_port.set_values(display_values)
        if display_values:
            self.com_port.set(display_values[0])

    def _toggle_cfg(self):
        if self.config_expanded:
            self.serial_config_body.pack_forget()
            self.collapse_button.configure(text="展开 ▼")
            self.config_expanded = False
        else:
            self.serial_config_body.pack(
                fill="x",
                padx=(LEFT_CONTENT_PADDING, RIGHT_CONTENT_PADDING),
                pady=(0, 14),
                after=self.serial_config_header,
            )
            self.collapse_button.configure(text="收起 ▲")
            self.config_expanded = True
        self.update_idletasks()

    def _toggle_monitor(self):
        if self.monitoring:
            self.monitoring = False
            self.monitor_btn.configure(text="开始监控 ▶", fg_color=BLUE, text_color="white")
        else:
            selected_display_name = self.com_port.get()

            port = self.port_display_map.get(
                selected_display_name,
                ""
            )

            if not port:
                messagebox.showwarning("提示", "未检测到可用串口")
                return

            try:
                baud = self.baud_cb.get_valid_baud()
            except ValueError as error:
                messagebox.showwarning("波特率错误", str(error))
                return

            try:
                if self.worker:
                    self.worker.connect(port, baud)

                self.monitoring = True
                self.monitor_btn.configure(
                    text="停止监控 ■",
                    fg_color=RED,
                    text_color="white"
                )

                self.lbl_com.configure(text=port)

            except Exception as error:
                messagebox.showwarning("提示", f"无法打开串口：{error}")

    def _toggle_hex(self):
        self.hex_mode = not self.hex_mode

    def _toggle_storage(self):
        if not self.raw_saver.active:
            directory = self.path_entry.get().strip()
            base_name = self.filename_entry.get().strip()

            if not directory:
                messagebox.showwarning("提示", "请选择数据保存路径")
                return

            try:
                self.raw_saver.start(
                    directory=directory,
                    base_name=base_name,
                    display_mode="hex" if self.hex_mode else "ascii",
                    split_mb=50,
                )
            except Exception as error:
                messagebox.showerror("启动存储失败", str(error))
                return

            self.storage_btn.configure(
                text="停止存储数据",
                fg_color=RED,
                hover_color="#ef4444",
                border_color=RED,
            )
            self.lbl_storage.configure(text="正在存储", text_color="#16a34a")

        else:
            self.raw_saver.stop(flush=True)

            self.storage_btn.configure(
                text="开始存储数据",
                fg_color=BLUE,
                hover_color="#4096ff",
                border_color=BLUE,
            )
            self.lbl_storage.configure(text="未存储", text_color="#6b7280")

    def _toggle_parse_mode(self):
        self.parse_mode = not self.parse_mode

        if self.parse_mode:
            # 协议解析模式：绿底白字
            self.btn_parse_mode.configure(
                fg_color=GREEN,
                hover_color="#22c55e",
                text_color="#FFFFFF",
                border_color=GREEN,
                border_width=1,
            )

            # 恢复协议控件，但外层槽位尺寸始终不变
            self.protocol_controls_frame.place(
                x=0,
                y=0,
            )

        else:
            # 原始数据模式：白底黑字
            self.btn_parse_mode.configure(
                fg_color="#FFFFFF",
                hover_color="#F3F4F6",
                text_color="#202124",
                border_color="#D1D5DB",
                border_width=1,
            )

            # 只隐藏内部控件，不隐藏固定槽位
            self.protocol_controls_frame.place_forget()

        self.update_idletasks()

    def _toggle_auto_scroll(self):
        self.auto_scroll = not self.auto_scroll
        if self.auto_scroll:
            self.btn_auto_scroll.configure(fg_color=GREEN, text_color="white",
                                           border_width=0)
        else:
            self.btn_auto_scroll.configure(fg_color="#f3f4f6", text_color="#1f2937",
                                           border_width=1, border_color="#d1d5db")

    def _module_send(self):
        """协议模式组包发送。"""
        if not self.worker:
            messagebox.showwarning("提示", "串口未就绪")
            return

        if not self.monitoring:
            messagebox.showwarning("提示", "请先开始监控")
            return

        # 获取选中的命令
        cmd_text = self.cmd_combo.get().strip()
        if not cmd_text:
            messagebox.showwarning("提示", "请选择命令")
            return

        # 从命令文本中提取 cmd_code（尝试匹配 0xXX 格式）
        import re
        match = re.search(r'0x([0-9a-fA-F]+)', cmd_text)
        if not match:
            messagebox.showwarning("提示", f"无法从命令中解析命令字：{cmd_text}")
            return

        cmd_code = int(match.group(1), 16)

        # 获取方向
        direction = self.direction_cb.get().strip()
        if "响应" in direction or "response" in direction.lower():
            direction = "response"
        else:
            direction = "request"

        # 获取字段 JSON
        fields = None
        json_text = ""
        try:
            json_text = self.json_text.get("0.0", "end").strip()
            if json_text:
                fields = json.loads(json_text)
        except json.JSONDecodeError:
            pass  # 字段为空或非 JSON 时不传 fields

        try:
            frame = self.protocol_manager.encode_frame(
                cmd_code=cmd_code,
                direction=direction,
                fields=fields,
            )

            self.worker.send(frame)
            self._on_tx_sent(frame, time.time())

        except Exception as error:
            messagebox.showwarning("组包发送失败", str(error))

    def _send_data(self):
        """原始数据发送（HEX / ASCII 模式）。

        使用 json_text 作为输入源：HEX 模式下将文本内容当 HEX 字符串解析，
        ASCII 模式下直接编码为 UTF-8 发送。
        """
        if not self.worker:
            messagebox.showwarning("提示", "串口未就绪")
            return

        if not self.monitoring:
            messagebox.showwarning("提示", "请先开始监控")
            return

        text = self.json_text.get("0.0", "end").strip()
        if not text:
            return

        try:
            if self.hex_mode:
                # HEX 模式：解析十六进制字符串
                clean = text.replace(" ", "").replace("\n", "").replace("\r", "")
                data = bytes.fromhex(clean)
            else:
                data = text.encode("utf-8")

            self.worker.send(data)
            self._on_tx_sent(data, time.time())

        except Exception as error:
            messagebox.showwarning("发送失败", str(error))

    def _import_word_protocol(self):
        """导入 Word 协议文档。"""
        try:
            from protocol_parser.docx_importer import (
                import_and_save,
                check_docx_available,
                ImporterError,
            )
        except ImportError:
            messagebox.showerror("错误", "Word 导入模块未安装")
            return

        if not check_docx_available():
            messagebox.showerror("错误", "请先安装 python-docx：pip install python-docx")
            return

        file_path = filedialog.askopenfilename(
            title="选择 Word 协议文档",
            filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")],
        )

        if not file_path:
            return

        try:
            # 用户协议保存目录
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            protocols_dir = os.path.join(project_root, "data", "protocols", "imported")
            os.makedirs(protocols_dir, exist_ok=True)

            cfg, saved_path = import_and_save(file_path, protocols_dir)
            display_name = cfg.get("product", os.path.basename(file_path))

            # 加入协议管理器并自动选中
            self.protocol_manager.add_user_protocol(display_name, cfg)

            # 更新下拉框
            self.product_proto_combo.set_values(
                self.protocol_manager.available_protocols(),
                default=display_name,
            )

            # 切换到新协议
            self._on_protocol_selected(display_name)

            messagebox.showinfo("成功", f"协议已导入：{display_name}\n保存到：{saved_path}")

        except ImporterError as error:
            messagebox.showerror("导入失败", str(error))
        except Exception as error:
            messagebox.showerror("导入失败", f"解析 Word 文档时出错：{error}")

    def _view_current_protocol(self):
        """查看当前协议详情。"""
        cfg = self.protocol_manager.current_config()
        if cfg is None:
            messagebox.showwarning("提示", "未选择协议")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"协议详情 - {self.protocol_manager.current_name()}")
        dialog.geometry("700x600")
        dialog.transient(self)
        dialog.grab_set()

        # 白色卡片
        card = Card(dialog)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        # 协议名称
        Label(
            card,
            f"协议名称：{self.protocol_manager.current_name()}",
            font=FONT_TITLE,
        ).pack(anchor="w", padx=20, pady=(18, 10))

        # JSON 内容
        text_box = ctk.CTkTextbox(
            card,
            fg_color="#FFFFFF",
            border_color="#D7DEE8",
            border_width=1,
            corner_radius=6,
            font=FONT_SMALL,
            wrap="none",
        )
        text_box.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        json_str = json.dumps(cfg, ensure_ascii=False, indent=2)
        text_box.insert("0.0", json_str)
        text_box.configure(state="disabled")

        # 居中
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

    def _view_protocol(self):
        """兼容旧按钮名。"""
        self._view_current_protocol()

    def _on_protocol_selected(self, protocol_name):
        """切换协议时重建帧同步器。"""
        try:
            cfg = self.protocol_manager.select(protocol_name)
            self.frame_synchronizer = self.protocol_manager.create_synchronizer()
        except Exception as error:
            messagebox.showerror("协议加载失败", str(error))

    def _clear_rx(self):
        self.rxbox.delete("0.0", "end")
        self.rx_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self.rxbox.place_forget()

    def _clear_input(self):
        pass

    def _send_data(self):
        pass

    def _choose_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)

    def _set_send_mode(self, mode):
        for btn in [self.btn_send_mode_hex]:
            btn.configure(fg_color="#f3f4f6", text_color="#1f2937",
                          border_width=1, border_color="#d1d5db")
        self.btn_send_mode_hex.configure(fg_color=BLUE, text_color="white",
                                         border_width=0)

    def _on_serial_data(self, data):
        """串口回调线程：入队原始数据 + 转发到 UI 线程解析显示。"""
        timestamp = time.time()

        # 原始数据实时落盘（在工作线程中执行，不阻塞串口接收）
        if self.raw_saver.active:
            self.raw_saver.enqueue_rx(data, timestamp)

        # 转发到 UI 线程处理显示和协议解析
        self.after(0, self._process_received_data, data, timestamp)

    def _process_received_data(self, data, timestamp):
        """UI 线程：根据模式分流处理接收数据。"""
        self.rx_placeholder.place_forget()
        self.rxbox.place(relx=0, rely=0, relwidth=1, relheight=1)

        if not self.parse_mode:
            # 原始数据模式：直接显示 HEX 或 ASCII
            text = (
                data.hex(" ").upper()
                if self.hex_mode
                else data.decode("utf-8", errors="replace")
            )
            self.rxbox.insert("end", text + "\n")
        else:
            # 协议解析模式：帧同步 → parse_frame → 显示解析结果
            self._process_protocol_data(data, timestamp)

        if self.auto_scroll:
            self.rxbox.see("end")

    def _process_protocol_data(self, data, timestamp):
        """协议模式：通过 FrameSynchronizer 切帧后逐帧解析。"""
        if self.frame_synchronizer is None:
            self.rxbox.insert("end", f"[{self._fmt_ts(timestamp)}] 协议同步器未初始化\n")
            return

        try:
            frames = self.frame_synchronizer.feed(data)

            if not frames:
                # 半帧等待中，不显示
                return

            for frame in frames:
                try:
                    result = self.protocol_manager.parse_frame(frame.raw)
                    text = self._format_parse_result(result, timestamp)
                    self.rxbox.insert("end", text + "\n")

                    # 结构化日志
                    if self.result_logger:
                        try:
                            self.result_logger.log(result, timestamp)
                        except Exception:
                            pass

                except ProtocolError as error:
                    friendly, debug = classify_protocol_error(error)
                    self.rxbox.insert(
                        "end",
                        f"[{self._fmt_ts(timestamp)}] [RX] ERR {friendly} raw={to_hex(frame.raw)}\n",
                    )

        except Exception as error:
            self.rxbox.insert(
                "end",
                f"[{self._fmt_ts(timestamp)}] [RX] 解析异常: {error}\n",
            )

    def _format_parse_result(self, result, timestamp):
        """格式化 ParseResult 为可读字符串。"""
        ts = self._fmt_ts(timestamp)
        checksum_str = "✓" if result.checksum_ok else ("✗" if result.checksum_ok is False else "?")
        cmd = result.cmd_code or "??"
        name = result.cmd_name or "未知"
        direction = result.direction or ""

        lines = [f"[{ts}] RX  {name}  CMD={cmd}  Checksum={checksum_str}  {direction}"]

        # 解析字段
        for field in result.fields:
            if isinstance(field, dict):
                if field.get("type") == "separator":
                    continue
                fname = field.get("name", "")
                fval = field.get("text", field.get("value", ""))
                lines.append(f"  {fname} = {fval}")

        if result.error:
            lines.append(f"  ⚠ {result.error}")

        return "\n".join(lines)

    @staticmethod
    def _fmt_ts(ts):
        """格式化时间戳为 HH:MM:SS.fff。"""
        import datetime
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}"

    def _on_tx_sent(self, data, timestamp):
        """发送成功后回调：入队 TX 数据 + 更新 UI。"""
        if self.raw_saver.active:
            self.raw_saver.enqueue_tx(data, timestamp)

        self.after(0, self._update_tx_status, len(data))

    def _update_tx_status(self, length):
        """UI 线程：更新 TX 计数。"""
        try:
            current = self.lbl_tx.cget("text")
            # 提取当前数字
            import re
            match = re.search(r"\d+", current)
            count = int(match.group()) if match else 0
            count += 1
            self.lbl_tx.configure(text=f"TX: {count}")
        except Exception:
            pass

    def _on_storage_error(self, message):
        """存储错误回调（在工作线程中调用，通过 after 转发到 UI 线程）。"""
        self.after(0, self._show_storage_error, message)

    def _show_storage_error(self, message):
        """UI 线程：显示存储错误。"""
        try:
            self.lbl_storage.configure(text=message[:50], text_color="#dc2626")
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────
    # COMMANDS LIBRARY
    # ─────────────────────────────────────────────────────────────────
    def _load_commands(self):
        # 兼容父类 ctk.CTk.__init__ 早期调用，此时 self.tree 尚未创建
        if not hasattr(self, "tree"):
            return
        if os.path.exists(COMMANDS_JSON):
            try:
                with open(COMMANDS_JSON, "r", encoding="utf-8") as f:
                    self.commands = json.load(f)
            except Exception:
                self.commands = []
        else:
            self.commands = [
                {"name": "124", "type": "HEX", "data": "a5a5"},
                {"name": "aaa", "type": "HEX", "data": "e5e5"},
                {"name": "55", "type": "HEX", "data": "9898"},
                {"name": "214214", "type": "HEX", "data": "214214"},
            ]
        self._refresh_tree()

    def _save_commands(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(COMMANDS_JSON, "w", encoding="utf-8") as f:
            json.dump(self.commands, f, ensure_ascii=False, indent=2)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, cmd in enumerate(self.commands, 1):
            self.tree.insert("", "end", values=(
                i, cmd["name"], cmd["type"], cmd["data"], "操作"
            ))

    def _on_tree_select(self, event):
        selection = self.tree.selection()
        if selection:
            idx = self.tree.index(selection[0])
            self.selected_command_index = idx

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#5":
                item = self.tree.identify_row(event.y)
                if item:
                    idx = self.tree.index(item)
                    self._show_action_menu(idx, event.x_root, event.y_root)

    def _show_action_menu(self, idx, x, y):
        pass  # action buttons handled via inline UI in future

    def _add_command(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("新增指令")
        dlg.geometry("360x220")
        dlg.transient(self)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="名称:", font=FONT_NORMAL).pack(anchor="w", padx=20, pady=(16, 4))
        name_entry = ctk.CTkEntry(dlg, width=300)
        name_entry.pack(padx=20)

        ctk.CTkLabel(dlg, text="类型:", font=FONT_NORMAL).pack(anchor="w", padx=20, pady=(10, 4))
        type_cb = ReadOnlyDropdown(dlg, values=["HEX", "ASCII"], default="HEX", width=300)
        type_cb.pack(padx=20)

        ctk.CTkLabel(dlg, text="数据:", font=FONT_NORMAL).pack(anchor="w", padx=20, pady=(10, 4))
        data_entry = ctk.CTkEntry(dlg, width=300)
        data_entry.pack(padx=20)

        def save():
            name = name_entry.get().strip()
            typ = type_cb.get()
            data = data_entry.get().strip()
            if not name or not data:
                messagebox.showwarning("提示", "名称和数据不能为空")
                return
            self.commands.append({"name": name, "type": typ, "data": data})
            self._save_commands()
            self._refresh_tree()
            dlg.destroy()

        Btn(dlg, "保存", color="blue", width=100, command=save).pack(pady=16)

    # ─────────────────────────────────────────────────────────────────
    # TOGGLES
    # ─────────────────────────────────────────────────────────────────
    def _set_library_visible(self, visible):
        visible = bool(visible)
        self.library_visible = visible

        if visible:
            self.library.grid()
            self.nav_library_button.set_active(True)
            self.lbl_lib_status.configure(text="已显示指令库")
        else:
            self.library.grid_remove()
            self.nav_library_button.set_active(False)
            self.lbl_lib_status.configure(text="已隐藏指令库")

        self.update_idletasks()

    def _set_send_visible(self, visible):
        visible = bool(visible)
        self.send_visible = visible

        if visible:
            self.send.grid()
            self.nav_send_button.set_active(True)
        else:
            self.send.grid_remove()
            self.nav_send_button.set_active(False)

        self.update_idletasks()

    def _apply_initial_panel_state(self):
        self._set_library_visible(False)
        self._set_send_visible(False)

    def toggle_library(self):
        self._set_library_visible(not self.library_visible)

    def toggle_send(self):
        self._set_send_visible(not self.send_visible)

    def _toggle_topmost(self):
        enabled = not bool(self.attributes("-topmost"))
        self.attributes("-topmost", enabled)
        self.nav_topmost_button.set_active(enabled)

    def _open_add_serial_dialog(self):
        # 扫描串口，同时保存本次弹窗使用的 显示名 -> 实际 COM 号 映射
        port_values = self._scan_ports()
        dialog_port_map = dict(self.port_display_map)

        if not port_values:
            port_values = ["未检测到串口"]
            dialog_port_map = {"未检测到串口": ""}

        # 弹窗波特率使用与主窗口相同的可编辑组件和常用列表
        current_port_display = self.com_port.get()
        if current_port_display not in port_values:
            current_port_display = port_values[0]

        current_baud = self.baud_cb.get()
        if not current_baud.isdigit():
            current_baud = "9600"

        dialog = ctk.CTkToplevel(self)
        dialog.title("添加串口")
        dialog.geometry("460x300")
        dialog.resizable(False, False)
        dialog.configure(fg_color="#f0f2f5")
        dialog.transient(self)
        dialog.grab_set()

        # 主体白色卡片
        card = Card(dialog)
        card.pack(
            fill="both",
            expand=True,
            padx=16,
            pady=16,
        )

        Label(
            card,
            "添加串口",
            font=FONT_TITLE,
        ).pack(
            anchor="w",
            padx=20,
            pady=(18, 16),
        )

        # 串口
        port_row = ctk.CTkFrame(
            card,
            fg_color="transparent",
        )
        port_row.pack(
            fill="x",
            padx=20,
            pady=6,
        )

        Label(
            port_row,
            "串口：",
            width=70,
            height=32,
        ).pack(side="left")

        port_dropdown = ReadOnlyDropdown(
            port_row,
            values=port_values,
            width=320,
            height=32,
            default=current_port_display,
        )
        port_dropdown.pack(side="left")

        # 波特率
        baud_row = ctk.CTkFrame(
            card,
            fg_color="transparent",
        )
        baud_row.pack(
            fill="x",
            padx=20,
            pady=6,
        )

        Label(
            baud_row,
            "波特率：",
            width=70,
            height=32,
        ).pack(side="left")

        baud_dropdown = EditableBaudDropdown(
            baud_row,
            values=COMMON_BAUD_RATES,
            width=320,
            height=32,
            default=current_baud,
        )
        baud_dropdown.pack(side="left")

        button_row = ctk.CTkFrame(
            card,
            fg_color="transparent",
        )
        button_row.pack(
            fill="x",
            padx=20,
            pady=(22, 16),
        )

        def close_dialog():
            try:
                dialog.grab_release()
            except Exception:
                pass

            dialog.destroy()

            # 无论通过确认还是右上角关闭，都强制恢复添加串口按钮
            self.nav_add_button.reset_visual_state()

        def confirm_add():
            selected_display = port_dropdown.get()

            try:
                selected_baud = baud_dropdown.get_valid_baud()
            except ValueError as error:
                messagebox.showwarning(
                    "波特率错误",
                    str(error),
                    parent=dialog,
                )
                return

            selected_device = dialog_port_map.get(
                selected_display,
                "",
            )

            if not selected_device:
                messagebox.showwarning(
                    "提示",
                    "请选择有效串口。",
                    parent=dialog,
                )
                return

            close_dialog()

            # 新开独立进程，避免同一进程创建多个 CTk 根窗口
            self._launch_new_serial_tool(
                selected_device,
                selected_baud,
            )

        Btn(
            button_row,
            "确认添加",
            color="blue",
            width=140,
            height=34,
            command=confirm_add,
        ).pack(anchor="center")

        dialog.protocol(
            "WM_DELETE_WINDOW",
            close_dialog,
        )

        # 弹窗相对主窗口居中
        dialog.update_idletasks()

        x = (
            self.winfo_rootx()
            + (self.winfo_width() - dialog.winfo_width()) // 2
        )
        y = (
            self.winfo_rooty()
            + (self.winfo_height() - dialog.winfo_height()) // 2
        )

        dialog.geometry(f"+{x}+{y}")

        self.wait_window(dialog)

        # 再做一次兜底恢复
        self.nav_add_button.reset_visual_state()

    def _launch_new_serial_tool(self, port, baud):
        project_root = os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        )

        main_file = os.path.join(
            project_root,
            "main.py",
        )

        subprocess.Popen(
            [
                sys.executable,
                main_file,
                "--port",
                str(port),
                "--baud",
                str(baud),
            ],
            cwd=project_root,
        )

    def _open_save_log_dialog(self):
        file_path = filedialog.asksaveasfilename(
            title="保存日志",
            defaultextension=".txt",
            filetypes=[
                ("文本文件", "*.txt"),
                ("日志文件", "*.log"),
                ("所有文件", "*.*"),
            ],
        )

        if file_path:
            try:
                # 初始化 ResultLogger，保存解析结果到 .log 文件
                self.result_logger = ResultLogger(
                    path=file_path,
                    mode="compact",
                    rotate_mode="size",
                    max_bytes=10 * 1024 * 1024,
                    backup_count=10,
                )
                messagebox.showinfo("成功", f"解析日志将保存到：{file_path}")
            except Exception as error:
                messagebox.showerror("错误", f"创建日志文件失败：{error}")
                self.result_logger = None

    def _on_close(self):
        """窗口关闭时安全释放所有资源。"""
        try:
            if self.raw_saver.active:
                self.raw_saver.stop(flush=True)
        except Exception:
            pass

        try:
            if self.result_logger:
                self.result_logger.close()
        except Exception:
            pass

        try:
            if self.worker:
                self.worker.close()
        except Exception:
            pass

        self.destroy()
