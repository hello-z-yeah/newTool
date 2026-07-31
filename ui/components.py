import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from PIL import Image, ImageDraw

BLUE = "#1677FF"
GREEN = "#16a34a"
RED = "#dc2626"
GRAY_BG = "#f3f4f6"
GRAY_BORDER = "#d1d5db"
GRAY_HOVER = "#e5e7eb"
TEXT_DARK = "#1f2937"
TEXT_MID = "#4b5563"
TEXT_LIGHT = "#6b7280"
HEADER_BG = "#f8fafc"

# =========================
# 全局按钮布局参数
# =========================
BUTTON_GAP_X = 8
BUTTON_GAP_Y = 6
BUTTON_PAD_X = BUTTON_GAP_X // 2
BUTTON_PAD_Y = BUTTON_GAP_Y // 2

# =========================
# 常用波特率列表（从小到大排列）
# =========================
COMMON_BAUD_RATES = [
    "4800",
    "9600",
    "14400",
    "19200",
    "28800",
    "38400",
    "56000",
    "57600",
    "76800",
    "115200",
    "128000",
    "230400",
    "256000",
    "460800",
    "500000",
    "512000",
    "576000",
    "600000",
    "750000",
    "921600",
    "1000000",
    "2000000",
]

# =========================
# 全局字体
# =========================

# 推荐：现代、圆润、显示稳定
FONT_FAMILY = "Microsoft YaHei UI"

# 更明显的圆体可以改成：
# FONT_FAMILY = "YouYuan"
# 或：
# FONT_FAMILY = "幼圆"

FONT_SMALL = (FONT_FAMILY, 11, "bold")
FONT_NORMAL = (FONT_FAMILY, 13, "bold")
FONT_TITLE = (FONT_FAMILY, 14, "bold")
FONT_LARGE = (FONT_FAMILY, 16, "bold")
HEIGHT_HEADER = 36


def Card(parent, **kw):
    defaults = dict(fg_color="white", corner_radius=12, border_width=1, border_color="#e2e8f0")
    defaults.update(kw)
    return ctk.CTkFrame(parent, **defaults)


def Btn(parent, text, color="normal", width=None, command=None, height=30, font=None, **kw):
    palette = {
        "normal":  {"fg": "#ffffff",       "text": TEXT_DARK, "hover": GRAY_HOVER,  "border": GRAY_BORDER},
        "blue":    {"fg": BLUE,            "text": "#ffffff", "hover": "#4096ff",  "border": BLUE},
        "green":   {"fg": GREEN,           "text": "#ffffff", "hover": "#22c55e",  "border": GREEN},
        "red":     {"fg": RED,             "text": "#ffffff", "hover": "#ef4444",  "border": RED},
        "outline": {"fg": GRAY_BG,         "text": TEXT_DARK, "hover": GRAY_HOVER,  "border": GRAY_BORDER},
        "active":  {"fg": BLUE,            "text": "#ffffff", "hover": "#4096ff",  "border": BLUE},
        "white":   {"fg": "#ffffff",       "text": TEXT_DARK, "hover": GRAY_HOVER,  "border": GRAY_BORDER},
    }
    p = palette.get(color, palette["normal"])
    btn = ctk.CTkButton(
        parent,
        text=text,
        width=width or len(text) * 10 + 28,
        height=height,
        corner_radius=6,
        fg_color=p["fg"],
        text_color=p["text"],
        hover_color=p["hover"],
        border_width=1,
        border_color=p["border"],
        command=command,
        font=font or FONT_NORMAL,#修改字体
        **kw,
    )
    return btn


def IconBtn(parent, icon, color="normal", command=None, size=28, **kw):
    palette = {
        "normal": {"fg": "#ffffff", "text": TEXT_DARK, "hover": GRAY_HOVER, "border": GRAY_BORDER},
        "blue":   {"fg": BLUE,      "text": "#ffffff", "hover": "#4096ff", "border": BLUE},
        "green":  {"fg": GREEN,     "text": "#ffffff", "hover": "#22c55e", "border": GREEN},
        "red":    {"fg": RED,       "text": "#ffffff", "hover": "#ef4444", "border": RED},
    }
    p = palette.get(color, palette["normal"])
    btn = ctk.CTkButton(
        parent,
        text=icon,
        width=size,
        height=size,
        corner_radius=4,
        fg_color=p["fg"],
        text_color=p["text"],
        hover_color=p["hover"],
        border_width=1,
        border_color=p["border"],
        command=command,
        font=FONT_TITLE,
        **kw,
    )
    return btn


def pack_button(widget, side="left", **kwargs):
    """统一使用 pack 布局的按钮外部间距。"""
    kwargs.setdefault("padx", BUTTON_PAD_X)
    kwargs.setdefault("pady", BUTTON_PAD_Y)
    widget.pack(side=side, **kwargs)
    return widget


def grid_button(widget, row, column, **kwargs):
    """统一使用 grid 布局的按钮外部间距。"""
    kwargs.setdefault("padx", BUTTON_PAD_X)
    kwargs.setdefault("pady", BUTTON_PAD_Y)
    widget.grid(row=row, column=column, **kwargs)
    return widget


def Label(parent, text, **kw):
    defaults = dict(text_color=TEXT_DARK, font=FONT_NORMAL, anchor="w")
    defaults.update(kw)
    return ctk.CTkLabel(parent, text=text, **defaults)


def WhiteComboBox(parent, values, width=150, default=None, state="readonly", **kw):
    defaults = dict(
        fg_color="#FFFFFF",
        border_color="#D7DEE8",
        button_color="#FFFFFF",
        button_hover_color="#F3F5F7",
        text_color="#202124",
        dropdown_fg_color="#FFFFFF",
        dropdown_hover_color="#EAF3FF",
        dropdown_text_color="#202124",
        corner_radius=5,
        border_width=1,
    )
    defaults.update(kw)
    cb = ctk.CTkComboBox(parent, values=values, width=width, state=state, **defaults)
    if default is not None:
        cb.set(default)
    return cb



def _make_chevron_image(size=12, color="#374151"):
    """生成抗锯齿的向下箭头图标。"""
    scale = 4
    canvas_size = size * scale

    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    stroke = max(2, scale * 2)
    left = int(canvas_size * 0.22)
    middle_x = int(canvas_size * 0.50)
    right = int(canvas_size * 0.78)
    top = int(canvas_size * 0.38)
    bottom = int(canvas_size * 0.66)

    draw.line(
        [(left, top), (middle_x, bottom), (right, top)],
        fill=color,
        width=stroke,
        joint="curve",
    )

    image = image.resize((size, size), Image.Resampling.LANCZOS)

    return ctk.CTkImage(
        light_image=image,
        dark_image=image,
        size=(size, size),
    )


class ReadOnlyDropdown(ctk.CTkFrame):
    """只读下拉框：弹层与控件等宽，并支持再次点击收起。"""

    _open_instance = None

    def __init__(
        self,
        master,
        values,
        width=180,
        height=30,
        variable=None,
        command=None,
        default=None,
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )

        self._width = width
        self._height = height
        self._command = command
        self._values = list(values) if values else [""]
        self._popup = None
        # 弹层父容器（主窗口或弹窗），下拉列表作为其内部浮动 Frame
        self._popup_parent = None
        self._outside_bind_id = None
        self._configure_bind_id = None
        self._bind_job = None

        # 防止弹层尚未创建完成就被 Configure 事件关闭
        self._building_popup = False

        initial_value = default if default in self._values else self._values[0]
        self.variable = variable or ctk.StringVar(value=initial_value)

        self.configure(width=width, height=height)
        self.pack_propagate(False)
        self.grid_propagate(False)

        # 只负责绘制完整边框。
        self._border_entry = ctk.CTkEntry(
            self,
            width=width,
            height=height,
            fg_color="#FFFFFF",
            border_color="#D7DEE8",
            border_width=1,
            corner_radius=6,
            state="disabled",
        )
        self._border_entry.place(x=0, y=0)

        self.value_label = ctk.CTkLabel(
            self,
            textvariable=self.variable,
            width=max(20, width - 44),
            height=height - 4,
            anchor="w",
            fg_color="#FFFFFF",
            text_color="#202124",
            font=FONT_TITLE,
            cursor="hand2",
        )
        self.value_label.place(x=10, y=2)

        self._chevron_image = _make_chevron_image(size=12)
        self.arrow_button = ctk.CTkButton(
            self,
            text="",
            image=self._chevron_image,
            width=28,
            height=height - 4,
            corner_radius=4,
            fg_color="#FFFFFF",
            hover_color="#F3F5F7",
            border_width=0,
            command=self._toggle_popup,
            cursor="hand2",
        )
        self.arrow_button.place(x=width - 30, y=2)

        # 整个控件都可点击；父子控件的事件不会自动冒泡，因此不会重复触发。
        self.bind("<Button-1>", self._toggle_popup)
        self._border_entry.bind("<Button-1>", self._toggle_popup)
        self.value_label.bind("<Button-1>", self._toggle_popup)

    def _pixel_to_logical(self, value):
        try:
            return int(
                round(
                    self._reverse_widget_scaling(
                        value
                    )
                )
            )
        except Exception:
            return int(round(value))

    def _on_parent_configure(self, event=None):
        if self._building_popup:
            return

        if self._popup is None:
            return

        # 仅主窗口真正移动或改变尺寸时关闭
        root = self.winfo_toplevel()

        if event is not None and event.widget is not root:
            return

        self.after_idle(self._close_popup)

    def _toggle_popup(self, event=None):
        if self._building_popup:
            return

        if self._popup is not None:
            try:
                if self._popup.winfo_exists():
                    self._close_popup()
                    return "break"
            except Exception:
                self._popup = None

        self._open_popup()
        return "break"

    def _open_popup(self):
        if self._building_popup:
            return

        if not self._values:
            return

        # 同一时间只允许一个自定义下拉框打开。
        other = ReadOnlyDropdown._open_instance
        if other is not None and other is not self:
            try:
                other._close_popup()
            except Exception:
                pass
        ReadOnlyDropdown._open_instance = self

        self._building_popup = True

        try:
            self.update_idletasks()

            popup_parent = self.winfo_toplevel()
            popup_parent.update_idletasks()

            # winfo_* 返回的是物理像素
            x_pixels = (
                self.winfo_rootx()
                - popup_parent.winfo_rootx()
            )
            y_pixels = (
                self.winfo_rooty()
                - popup_parent.winfo_rooty()
                + self.winfo_height()
                + 1
            )

            # 防止下拉框超出窗口右侧（物理像素判断）
            parent_width_pixels = popup_parent.winfo_width()
            popup_width_pixels = self.winfo_width()
            if popup_width_pixels <= 1:
                popup_width_pixels = self._width
            if x_pixels + popup_width_pixels > parent_width_pixels:
                x_pixels = max(
                    0,
                    parent_width_pixels - popup_width_pixels - 4,
                )

            # 屏幕底部空间不足时，改为向上弹出
            screen_height = self.winfo_screenheight()
            popup_height_pixels_est = (
                min(max(len(self._values), 1), 8) * self.winfo_height() + 2
                if self.winfo_height() > 1 else self._height * 8
            )
            if self.winfo_rooty() + popup_height_pixels_est > screen_height:
                y_pixels = (
                    self.winfo_rooty()
                    - popup_parent.winfo_rooty()
                    - popup_height_pixels_est
                    - 1
                )

            # 转换为 CustomTkinter 使用的逻辑坐标
            popup_x = self._pixel_to_logical(x_pixels)
            popup_y = self._pixel_to_logical(y_pixels)

            popup_width = self._width
            row_height = self._height
            max_visible_rows = 8
            visible_rows = min(
                max(len(self._values), 1),
                max_visible_rows,
            )
            popup_height = visible_rows * row_height + 2

            self._popup_parent = popup_parent

            self._popup = ctk.CTkFrame(
                popup_parent,
                width=popup_width,
                height=popup_height,
                fg_color="#FFFFFF",
                border_width=1,
                border_color="#D7DEE8",
                corner_radius=6,
            )
            self._popup.place(x=popup_x, y=popup_y)
            self._popup.pack_propagate(False)
            self._popup.grid_propagate(False)
            self._popup.lift()

            # 项目较少时使用普通 Frame
            if len(self._values) <= max_visible_rows:
                list_frame = ctk.CTkFrame(
                    self._popup,
                    width=popup_width - 2,
                    height=popup_height - 2,
                    fg_color="#FFFFFF",
                    corner_radius=5,
                )
            else:
                # 必须先确保 popup 已完成布局，再创建滚动框
                self._popup.update_idletasks()

                list_frame = ctk.CTkScrollableFrame(
                    self._popup,
                    width=popup_width - 2,
                    height=popup_height - 2,
                    fg_color="#FFFFFF",
                    corner_radius=5,
                    scrollbar_button_color="#CBD5E1",
                    scrollbar_button_hover_color="#94A3B8",
                )

            list_frame.pack(fill="both", expand=True, padx=1, pady=1)
            list_frame.pack_propagate(False)

            for value in self._values:
                self._create_popup_item(list_frame, value, row_height)

            self._popup.update_idletasks()
            self._popup.lift()

        except Exception:
            # 创建失败时清理半成品，避免残留无效 Canvas
            self._destroy_popup_only()
            raise

        finally:
            self._building_popup = False

        # 必须等整个弹层构建完成后再绑定事件
        self.after_idle(self._bind_popup_events)

    def _create_popup_item(self, parent, value, row_height):
        selected = str(value) == self.variable.get()

        item = ctk.CTkButton(
            parent,
            text=str(value),
            height=row_height,
            anchor="w",
            corner_radius=0,
            fg_color="#EAF3FF" if selected else "#FFFFFF",
            hover_color="#D6E9FF",
            text_color="#202124",
            border_width=0,
            font=FONT_NORMAL,
            cursor="hand2",
            command=lambda selected_value=value: self._select(selected_value),
        )
        item.pack(fill="x", padx=0, pady=0)

    def _bind_popup_events(self):
        if self._building_popup:
            return

        if self._popup is None:
            return

        try:
            if not self._popup.winfo_exists():
                return
        except Exception:
            return

        root = self.winfo_toplevel()

        if self._outside_bind_id is None:
            self._outside_bind_id = root.bind(
                "<Button-1>",
                self._on_root_click,
                add="+",
            )

        if self._configure_bind_id is None:
            self._configure_bind_id = root.bind(
                "<Configure>",
                self._on_parent_configure,
                add="+",
            )

    @staticmethod
    def _is_descendant(widget, ancestor):
        current = widget
        while current is not None:
            if current == ancestor:
                return True
            try:
                current = current.master
            except Exception:
                break
        return False

    def _on_root_click(self, event):
        if self._popup is None:
            return

        # 点击原下拉框时，由 _toggle_popup 负责开关
        if self._is_descendant(event.widget, self):
            return

        # 点击下拉列表内部时不能提前关闭
        if self._is_descendant(event.widget, self._popup):
            return

        self._close_popup()

    def _destroy_popup_only(self):
        popup = self._popup

        # 必须先清空引用，避免 destroy 过程中再次触发关闭
        self._popup = None
        self._popup_parent = None

        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass

        if ReadOnlyDropdown._open_instance is self:
            ReadOnlyDropdown._open_instance = None

    def _close_popup(self):
        if self._building_popup:
            return

        root = self.winfo_toplevel()

        if self._outside_bind_id is not None:
            try:
                root.unbind("<Button-1>", self._outside_bind_id)
            except Exception:
                pass
            self._outside_bind_id = None

        if self._configure_bind_id is not None:
            try:
                root.unbind("<Configure>", self._configure_bind_id)
            except Exception:
                pass
            self._configure_bind_id = None

        self._destroy_popup_only()

    def _select(self, value):
        self.variable.set(value)
        if self._command is not None:
            self._command(value)
        self._close_popup()

    def get(self):
        return self.variable.get()

    def set(self, value):
        self.variable.set(value)

    def set_values(self, values, default=None):
        self._values = list(values) if values else ["未检测到串口"]
        current = self.variable.get()
        if default in self._values:
            self.variable.set(default)
        elif current not in self._values:
            self.variable.set(self._values[0])


class EditableBaudDropdown(ctk.CTkFrame):
    """可输入、可下拉选择的波特率控件。

    仅用于波特率字段，串口/数据位/停止位等仍使用 ReadOnlyDropdown。
    弹层为主窗口内部浮动 CTkFrame，不创建 Toplevel，主窗口不会失焦。
    """

    def __init__(
        self,
        master,
        values,
        width=120,
        height=30,
        default="9600",
        command=None,
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )

        self._width = width
        self._height = height
        self._values = [str(v) for v in values] if values else ["9600"]
        self._command = command
        self._popup = None
        self._popup_parent = None
        self._outside_bind_id = None
        self._configure_bind_id = None
        self._bind_job = None

        # 防止弹层尚未创建完成就被 Configure 事件关闭
        self._building_popup = False

        # 防重复触发：值变化时才执行 command
        self._last_confirmed_value = str(default)

        self.variable = ctk.StringVar(value=str(default))

        self.pack_propagate(False)
        self.grid_propagate(False)

        # 可编辑输入框
        self.entry = ctk.CTkEntry(
            self,
            width=width,
            height=height,
            textvariable=self.variable,
            fg_color="#FFFFFF",
            border_color="#D7DEE8",
            border_width=1,
            corner_radius=6,
            text_color="#202124",
            font=FONT_NORMAL,
            placeholder_text="",
        )
        self.entry.place(x=0, y=0)

        # 整数输入校验：仅允许数字和暂时清空
        validate_command = (
            self.register(self._validate_typing),
            "%P",
        )
        self.entry.configure(
            validate="key",
            validatecommand=validate_command,
        )

        self._chevron_image = _make_chevron_image(size=12)

        # 箭头按钮
        self.arrow_button = ctk.CTkButton(
            self,
            text="",
            image=self._chevron_image,
            width=28,
            height=height - 4,
            corner_radius=4,
            fg_color="#FFFFFF",
            hover_color="#F3F5F7",
            border_width=0,
            cursor="hand2",
            command=self._toggle_popup,
        )
        self.arrow_button.place(
            x=width - 30,
            y=2,
        )

        self.entry.bind("<Return>", self._confirm_input)
        self.entry.bind("<FocusOut>", self._validate_after_focus)

    def _pixel_to_logical(self, value):
        try:
            return int(
                round(
                    self._reverse_widget_scaling(
                        value
                    )
                )
            )
        except Exception:
            return int(round(value))

    def _on_parent_configure(self, event=None):
        if self._building_popup:
            return

        if self._popup is None:
            return

        # 仅主窗口真正移动或改变尺寸时关闭
        root = self.winfo_toplevel()

        if event is not None and event.widget is not root:
            return

        self.after_idle(self._close_popup)

    # ---------- 输入校验 ----------

    def _validate_typing(self, new_value):
        # 允许暂时清空，方便重新输入
        if new_value == "":
            return True
        return new_value.isdigit()

    def get_valid_baud(self):
        value = self.variable.get().strip()

        if not value:
            raise ValueError("波特率不能为空")

        if not value.isdigit():
            raise ValueError("波特率必须是正整数")

        baud = int(value)

        if baud <= 0:
            raise ValueError("波特率必须大于 0")

        if baud > 10000000:
            raise ValueError("波特率不能超过 10000000")

        return baud

    def _confirm_input(self, event=None):
        try:
            baud = self.get_valid_baud()
            # 统一格式，去除开头的 0
            self.variable.set(str(baud))
            self._fire_command_if_changed(str(baud))
        except ValueError:
            self.variable.set("9600")

        self._close_popup()

    def _validate_after_focus(self, event=None):
        value = self.variable.get().strip()

        if value == "":
            self.variable.set("9600")
            self._fire_command_if_changed("9600")
            return

        try:
            baud = self.get_valid_baud()
            normalized = str(baud)
            self.variable.set(normalized)
            self._fire_command_if_changed(normalized)
        except ValueError:
            self.variable.set("9600")
            self._fire_command_if_changed("9600")

    def _fire_command_if_changed(self, value):
        """只有值真正变化时才触发 command，避免 Enter/FocusOut 双重触发。"""
        if value == self._last_confirmed_value:
            return
        self._last_confirmed_value = value
        if self._command is not None:
            try:
                self._command(value)
            except Exception:
                pass

    # ---------- 弹层开关 ----------

    def _toggle_popup(self, event=None):
        if self._building_popup:
            return

        if self._popup is not None:
            try:
                if self._popup.winfo_exists():
                    self._close_popup()
                    return
            except Exception:
                self._popup = None

        self._open_popup()

    def _open_popup(self):
        if self._building_popup:
            return

        if not self._values:
            return

        self._building_popup = True

        try:
            self.update_idletasks()

            popup_parent = self.winfo_toplevel()
            popup_parent.update_idletasks()

            # winfo_* 返回的是物理像素
            x_pixels = (
                self.winfo_rootx()
                - popup_parent.winfo_rootx()
            )
            y_pixels = (
                self.winfo_rooty()
                - popup_parent.winfo_rooty()
                + self.winfo_height()
                + 1
            )

            # 防止下拉框超出窗口右侧（物理像素判断）
            parent_width_pixels = popup_parent.winfo_width()
            popup_width_pixels = self.winfo_width()
            if popup_width_pixels <= 1:
                popup_width_pixels = self._width
            if x_pixels + popup_width_pixels > parent_width_pixels:
                x_pixels = max(
                    0,
                    parent_width_pixels - popup_width_pixels - 4,
                )

            # 屏幕底部空间不足时，改为向上弹出
            screen_height = self.winfo_screenheight()
            popup_height_pixels_est = (
                min(max(len(self._values), 1), 10) * self.winfo_height() + 2
                if self.winfo_height() > 1 else self._height * 10
            )
            if self.winfo_rooty() + popup_height_pixels_est > screen_height:
                y_pixels = (
                    self.winfo_rooty()
                    - popup_parent.winfo_rooty()
                    - popup_height_pixels_est
                    - 1
                )

            # 转换为 CustomTkinter 使用的逻辑坐标
            popup_x = self._pixel_to_logical(x_pixels)
            popup_y = self._pixel_to_logical(y_pixels)

            popup_width = self._width
            row_height = self._height
            max_visible_rows = 10
            visible_rows = min(
                max(len(self._values), 1),
                max_visible_rows,
            )
            popup_height = visible_rows * row_height + 2

            self._popup_parent = popup_parent

            self._popup = ctk.CTkFrame(
                popup_parent,
                width=popup_width,
                height=popup_height,
                fg_color="#FFFFFF",
                border_width=1,
                border_color="#D7DEE8",
                corner_radius=6,
            )
            self._popup.place(x=popup_x, y=popup_y)
            self._popup.pack_propagate(False)
            self._popup.grid_propagate(False)
            self._popup.lift()

            # 使用 CTkScrollableFrame 支持滚动查看所有波特率
            self._popup.update_idletasks()

            list_frame = ctk.CTkScrollableFrame(
                self._popup,
                width=popup_width - 2,
                height=popup_height - 2,
                fg_color="#FFFFFF",
                corner_radius=5,
                scrollbar_button_color="#CBD5E1",
                scrollbar_button_hover_color="#94A3B8",
            )

            list_frame.pack(fill="both", expand=True, padx=1, pady=1)

            for value in self._values:
                self._create_popup_item(list_frame, value, row_height)

            self._popup.update_idletasks()
            self._popup.lift()

        except Exception:
            # 创建失败时清理半成品，避免残留无效 Canvas
            self._destroy_popup_only()
            raise

        finally:
            self._building_popup = False

        # 必须等整个弹层构建完成后再绑定事件
        self.after_idle(self._bind_popup_events)

    def _create_popup_item(self, parent, value, row_height):
        selected = str(value) == self.variable.get()

        item = ctk.CTkButton(
            parent,
            text=str(value),
            height=row_height,
            anchor="w",
            corner_radius=0,
            fg_color="#EAF3FF" if selected else "#FFFFFF",
            hover_color="#D6E9FF",
            text_color="#202124",
            border_width=0,
            font=FONT_NORMAL,
            cursor="hand2",
            command=lambda selected_value=value: self._select(selected_value),
        )
        item.pack(fill="x", padx=0, pady=0)

    def _bind_popup_events(self):
        if self._building_popup:
            return

        if self._popup is None:
            return

        try:
            if not self._popup.winfo_exists():
                return
        except Exception:
            return

        root = self.winfo_toplevel()

        if self._outside_bind_id is None:
            self._outside_bind_id = root.bind(
                "<Button-1>",
                self._on_root_click,
                add="+",
            )

        if self._configure_bind_id is None:
            self._configure_bind_id = root.bind(
                "<Configure>",
                self._on_parent_configure,
                add="+",
            )

    @staticmethod
    def _is_descendant(widget, ancestor):
        current = widget
        while current is not None:
            if current == ancestor:
                return True
            try:
                current = current.master
            except Exception:
                break
        return False

    def _on_root_click(self, event):
        if self._popup is None:
            return

        # 点击原控件时由 _toggle_popup 处理
        if self._is_descendant(event.widget, self):
            return

        # 点击下拉列表内部时不提前关闭
        if self._is_descendant(event.widget, self._popup):
            return

        self._close_popup()

    def _destroy_popup_only(self):
        popup = self._popup

        # 必须先清空引用，避免 destroy 过程中再次触发关闭
        self._popup = None
        self._popup_parent = None

        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass

    def _close_popup(self):
        if self._building_popup:
            return

        root = self.winfo_toplevel()

        if self._outside_bind_id is not None:
            try:
                root.unbind("<Button-1>", self._outside_bind_id)
            except Exception:
                pass
            self._outside_bind_id = None

        if self._configure_bind_id is not None:
            try:
                root.unbind("<Configure>", self._configure_bind_id)
            except Exception:
                pass
            self._configure_bind_id = None

        self._destroy_popup_only()

    def _select(self, value):
        normalized = str(value)
        self.variable.set(normalized)
        self._fire_command_if_changed(normalized)
        self._close_popup()

        # 选择后将光标放回输入框
        self.entry.focus_set()
        self.entry.icursor("end")

    # ---------- 公共接口（与 ReadOnlyDropdown 保持一致） ----------

    def get(self):
        return self.variable.get().strip()

    def set(self, value):
        normalized = str(value)
        self.variable.set(normalized)
        # set() 仅同步状态，不触发 command
        self._last_confirmed_value = normalized

    def set_values(self, values, default=None):
        self._values = [str(v) for v in values] if values else ["9600"]
        if default is not None:
            self.variable.set(str(default))


class NavItem(ctk.CTkFrame):
    """导航按钮项：白底灰边框圆角样式。"""

    def __init__(
        self,
        master,
        text,
        icon="",
        command=None,
        width=100,
        height=32,
        active=False,
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color="white",
            corner_radius=8,
            border_width=1,
            border_color="#d1d5db",
        )

        self.command = command
        self._active = active

        self.label = ctk.CTkLabel(
            self,
            text=f"{icon}  {text}".strip(),
            width=width,
            height=height,
            fg_color="transparent",
            text_color="#202124",
            font=ctk.CTkFont(
                family="Microsoft YaHei UI",
                size=13,
                weight="bold" if active else "normal",
            ),
            anchor="center",
        )
        self.label.pack(fill="both", expand=True)

        if command is not None:
            self.configure(cursor="hand2")
            self.label.configure(cursor="hand2")

            self.bind("<Button-1>", self._click)
            self.label.bind("<Button-1>", self._click)

            self.bind("<Enter>", self._enter)
            self.label.bind("<Enter>", self._enter)

            self.bind("<Leave>", self._leave)
            self.label.bind("<Leave>", self._leave)

    def _click(self, event=None):
        if self.command:
            self.command()

    def _enter(self, event=None):
        if self.command and not self._active:
            self.configure(fg_color="#F3F6FA", border_color="#9ca3af")
            self.label.configure(fg_color="#F3F6FA")

    def _leave(self, event=None):
        if not self._active:
            self.configure(fg_color="white", border_color="#d1d5db")
            self.label.configure(fg_color="transparent")


def NavTitle(parent, text, icon="", width=132):
    return NavItem(
        parent,
        text=text,
        icon=icon,
        command=None,
        width=width,
        height=48,
    )


def TabBtn(
    parent,
    text,
    icon="",
    command=None,
    active=False,
    width=132,
):
    return NavItem(
        parent,
        text=text,
        icon=icon,
        command=command,
        width=width,
        height=48,
    )


class NavActionButton(ctk.CTkButton):
    """顶部导航按钮，支持 toggle 和 action 两种模式。"""

    NORMAL_BG = "#FFFFFF"
    NORMAL_TEXT = "#202124"
    NORMAL_BORDER = "#FFFFFF"

    ACTIVE_BG = "#1677FF"
    ACTIVE_TEXT = "#FFFFFF"
    ACTIVE_BORDER = "#1677FF"

    def __init__(
        self,
        master,
        text,
        command=None,
        mode="toggle",
        width=110,
        height=30,
        initial_active=False,
    ):
        self._user_command = command
        self._mode = mode
        self._active = bool(initial_active)
        self._mouse_inside = False

        super().__init__(
            master,
            text=text,
            width=width,
            height=height,
            corner_radius=0,
            border_width=0,
            fg_color=self.NORMAL_BG,
            text_color=self.NORMAL_TEXT,
            border_color=self.NORMAL_BORDER,
            hover=False,
            font=FONT_NORMAL,
            command=self._handle_click,
        )

        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

        self._refresh_style()

    def _refresh_style(self):
        highlighted = self._active or self._mouse_inside

        if highlighted:
            self.configure(
                fg_color=self.ACTIVE_BG,
                text_color=self.ACTIVE_TEXT,
                border_color=self.ACTIVE_BORDER,
            )
        else:
            self.configure(
                fg_color=self.NORMAL_BG,
                text_color=self.NORMAL_TEXT,
                border_color=self.NORMAL_BORDER,
            )

    def _on_enter(self, event=None):
        self._mouse_inside = True
        self._refresh_style()

    def _on_leave(self, event=None):
        self._mouse_inside = False
        self._refresh_style()

    def _handle_click(self):
        if self._mode == "toggle":
            # 业务函数负责调用 set_active() 同步状态
            if self._user_command is not None:
                self._user_command()

        elif self._mode == "action":
            self._active = True
            self._refresh_style()
            self.update_idletasks()

            try:
                if self._user_command is not None:
                    self._user_command()
            finally:
                self.reset_visual_state()

    def reset_visual_state(self):
        """强制恢复为黑字白底的默认视觉状态。

        用于 action 模式弹出模态对话框的场景：鼠标仍停在按钮上时，
        `_mouse_inside` 会保持 True，导致 `_refresh_style()` 仍判断为高亮。
        这里同时清掉 active 和 mouse_inside，确保按钮恢复默认外观。
        """
        self._active = False
        self._mouse_inside = False

        self.configure(
            fg_color=self.NORMAL_BG,
            text_color=self.NORMAL_TEXT,
            border_color=self.NORMAL_BORDER,
        )

    def set_active(self, active):
        self._active = bool(active)
        self._refresh_style()

    def is_active(self):
        return self._active


def setup_tree_style():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        "Custom.Treeview",
        background="white",
        foreground=TEXT_DARK,
        fieldbackground="white",
        borderwidth=0,
        rowheight=28,
        font=FONT_SMALL,
    )
    style.configure(
        "Custom.Treeview.Heading",
        background=HEADER_BG,
        foreground=TEXT_DARK,
        borderwidth=0,
        relief="flat",
        font=FONT_NORMAL,
        padding=(8, 6),
    )
    style.map(
        "Custom.Treeview",
        background=[("selected", "#dbeafe")],
        foreground=[("selected", TEXT_DARK)],
    )
    return style

def apply_global_font(widget, font=FONT_NORMAL):
    """递归修改整个界面的 CustomTkinter 字体。"""

    supported_widgets = (
        ctk.CTkLabel,
        ctk.CTkButton,
        ctk.CTkEntry,
        ctk.CTkTextbox,
        ctk.CTkComboBox,
        ctk.CTkOptionMenu,
        ctk.CTkCheckBox,
        ctk.CTkRadioButton,
        ctk.CTkSwitch,
    )

    for child in widget.winfo_children():
        try:
            if isinstance(child, supported_widgets):
                child.configure(font=font)

            if isinstance(child, ctk.CTkComboBox):
                child.configure(dropdown_font=font)

            if isinstance(child, ctk.CTkOptionMenu):
                child.configure(dropdown_font=font)

        except (TypeError, ValueError):
            # 部分特殊控件可能不支持某个字体参数
            pass

        apply_global_font(child, font)
