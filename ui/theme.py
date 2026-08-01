"""PySide6 visual theme for the serial protocol tool.

The runtime UI no longer depends on CustomTkinter.  All colours, dimensions and
QSS rules are kept here so the application can be restyled from one place.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Core palette
# ---------------------------------------------------------------------------
APP_BG = "#F1F3F6"
CARD_BG = "#FFFFFF"
CONTROL_BG = "#FFFFFF"
TEXT = "#111827"
TEXT_SECONDARY = "#4B5563"
TEXT_MUTED = "#8A97AA"
TEXT_DISABLED = "#A5ADB8"
BORDER = "#D9DEE7"
BORDER_LIGHT = "#E6EAF0"
HEADER_BG = "#F5F7FA"
SELECTED_BG = "#DCEBFF"
BLUE = "#096DD9"
BLUE_HOVER = "#1677FF"
GREEN = "#16A34A"
RED = "#DC2626"

# ============================================================
# 全局字体
# ============================================================
UI_FONT_FAMILY = "Microsoft YaHei UI"
UI_FONT_POINT_SIZE = 9

# 实时数据框默认字号与主界面完全一致
RX_FONT_DEFAULT_SIZE = UI_FONT_POINT_SIZE

# Ctrl + 滚轮允许的字号范围
RX_FONT_MIN_SIZE = 9
RX_FONT_MAX_SIZE = 22
RX_FONT_STEP = 1

# 保留原有命名的字体别名，确保旧代码兼容（最终统一用 UI_FONT_*）
FONT_FAMILY = UI_FONT_FAMILY
MONO_FONT_FAMILY = "Consolas"
# FONT_SIZE / SMALL_FONT_SIZE / TITLE_FONT_SIZE 改为像素值，用于 build_stylesheet
FONT_SIZE = 13  # px（≈10pt * 1.33 DPI ratio baseline）
SMALL_FONT_SIZE = 12
TITLE_FONT_SIZE = 14

# ============================================================
# 全局布局尺寸
# ============================================================

# 主窗口各白色区域距离窗口左右边缘
PAGE_MARGIN_X = 7
PAGE_MARGIN_Y = 6

# 每个白色区域内部左右、上下留白
SECTION_PADDING_X = 10
SECTION_PADDING_Y = 6

# 同一区域每一行之间的竖向距离
SECTION_ROW_GAP = 6

# 同一行各元素之间的横向距离
CONTROL_GAP_X = 8

# 普通控件统一高度
CONTROL_HEIGHT = 32
BUTTON_HEIGHT = 32

# 带阴影按钮需要预留的安全空间
BUTTON_SHADOW_PAD_X = 2
BUTTON_SHADOW_PAD_Y = 2

# 一行需要容纳按钮本体和上下阴影
CONTROL_ROW_MIN_HEIGHT = BUTTON_HEIGHT + BUTTON_SHADOW_PAD_Y * 2

# ------------------------------------------------------------
# 派生的卡片尺寸常量（依赖上面的统一常量计算）
# ------------------------------------------------------------
CARD_RADIUS = 10
CONTROL_RADIUS = 8
SMALL_CONTROL_HEIGHT = 28
# CARD_GAP 与 SECTION_ROW_GAP 保持一致，避免卡片之间、卡片内行间距不统一
CARD_GAP = SECTION_ROW_GAP
CARD_OUTER_MARGIN = PAGE_MARGIN_Y
CARD_INNER_MARGIN = SECTION_PADDING_Y

NAV_HEIGHT = BUTTON_HEIGHT + SECTION_PADDING_Y * 2
CONFIG_COLLAPSED_HEIGHT = CONTROL_ROW_MIN_HEIGHT + SECTION_PADDING_Y * 2
CONFIG_EXPANDED_HEIGHT = CONTROL_ROW_MIN_HEIGHT * 2 + SECTION_ROW_GAP + SECTION_PADDING_Y * 2
STATUS_HEIGHT = 38
SEND_CARD_HEIGHT = 164

LIBRARY_MAX_ROWS = 40
LIBRARY_HEADER_HEIGHT = 32
LIBRARY_ROW_HEIGHT = 27
LIBRARY_GRID_COLOR = "#E6EAF0"
LIBRARY_NAME_WIDTH = 125
LIBRARY_TYPE_WIDTH = 90
LIBRARY_ACTION_WIDTH = 78

# 指令库发送按钮单元格留白与基础行高（统一40行共用）
CMDLIB_ACTION_PAD_X = 5
CMDLIB_ACTION_PAD_Y = 4
CMDLIB_ROW_MIN_HEIGHT = 36

# ---------------------------------------------------------------------------
# Unified combo-box constants & component-level QSS (applied at widget init)
# ---------------------------------------------------------------------------
COMBOBOX_QSS = """
QComboBox#UnifiedComboBox {
    padding-left: 11px;
    padding-right: 30px;

    background-color: #FFFFFF;
    color: #111827;

    border: 1px solid #C8CDD5;
    border-radius: 10px;

    outline: none;
}

QComboBox#UnifiedComboBox:hover {
    background-color: #FAFBFC;
    border: 1px solid #AEB6C2;
}

QComboBox#UnifiedComboBox:focus {
    background-color: #FFFFFF;
    border: 1px solid #C8CDD5;
    outline: none;
}

QComboBox#UnifiedComboBox[popupOpen="true"] {
    background-color: #FFFFFF;

    border: 1px solid #C8CDD5;
    border-bottom: none;

    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}

QComboBox#UnifiedComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;

    background-color: transparent;
    border: none;
    border-left: none;

    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}

QComboBox#UnifiedComboBox::drop-down:hover {
    background-color: transparent;
    border: none;
}

QComboBox#UnifiedComboBox QLineEdit {
    background-color: transparent;
    color: #111827;
    border: none;
    outline: none;

    selection-background-color: #E8EEF7;
    selection-color: #111827;
}

QComboBox#UnifiedComboBox:disabled {
    background-color: #F4F5F7;
    color: #9CA3AF;
    border: 1px solid #E5E7EB;
}
"""

COMBO_POPUP_QSS = """
QListView#UnifiedComboView {
    background-color: #FFFFFF;
    color: #111827;

    border: 1px solid #C8CDD5;
    border-top: none;

    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;

    padding-top: 2px;
    padding-bottom: 4px;

    outline: none;
}

QListView#UnifiedComboView::item {
    min-height: 30px;
    padding-left: 11px;
    padding-right: 11px;

    background-color: #FFFFFF;
    color: #111827;
    border: none;
}

QListView#UnifiedComboView::item:hover {
    background-color: #F1F4F8;
    color: #111827;
    border: none;
}

QListView#UnifiedComboView::item:selected {
    background-color: #F1F4F8;
    color: #111827;
    border: none;
    outline: none;
}

QListView#UnifiedComboView::item:selected:!active {
    background-color: #FFFFFF;
    color: #111827;
}
"""

# ---------------------------------------------------------------------------
# Unified button state palette
# Default  : white bg, light border, dark text
# Active   : deep-green fill + white text (all common checkable/toggle buttons)
# Stop     : solid red fill + white text (监控 / 数据存储 停止动作态)
# Segment  : segmented toggle for cmd lib HEX / ASCII switch
# ---------------------------------------------------------------------------
COLOR_BTN_DEFAULT_BG = "#FFFFFF"
COLOR_BTN_DEFAULT_BORDER = "#D9DEE7"
COLOR_BTN_DEFAULT_TEXT = "#111827"

COLOR_BTN_HOVER_BG = "#F8FAFC"
COLOR_BTN_HOVER_BORDER = "#C7D2E3"
COLOR_BTN_HOVER_TEXT = "#111827"

COLOR_BTN_PRESSED_BG = "#EEF2F7"
COLOR_BTN_PRESSED_BORDER = "#C7D2E3"
COLOR_BTN_PRESSED_TEXT = "#111827"

COLOR_BTN_ACTIVE_GREEN_BG = "#1F9D46"
COLOR_BTN_ACTIVE_GREEN_BORDER = "#1F9D46"
COLOR_BTN_ACTIVE_GREEN_TEXT = "#FFFFFF"

COLOR_BTN_ACTIVE_GREEN_HOVER_BG = "#18853B"
COLOR_BTN_ACTIVE_GREEN_HOVER_BORDER = "#18853B"

COLOR_BTN_ACTIVE_GREEN_PRESSED_BG = "#146E31"
COLOR_BTN_ACTIVE_GREEN_PRESSED_BORDER = "#146E31"

COLOR_BTN_STOP_RED_BG = "#E53935"
COLOR_BTN_STOP_RED_BORDER = "#E53935"
COLOR_BTN_STOP_RED_TEXT = "#FFFFFF"

COLOR_BTN_STOP_RED_HOVER_BG = "#D32F2F"
COLOR_BTN_STOP_RED_HOVER_BORDER = "#D32F2F"

COLOR_BTN_STOP_RED_PRESSED_BG = "#B71C1C"
COLOR_BTN_STOP_RED_PRESSED_BORDER = "#B71C1C"

COLOR_BTN_DISABLED_BG = "#F5F6F8"
COLOR_BTN_DISABLED_TEXT = "#A5ADB8"
COLOR_BTN_DISABLED_BORDER = "#EEF0F3"

COLOR_BTN_SHADOW_DEFAULT = "#D9DEE7"
COLOR_BTN_SHADOW_HOVER = "#73B3FF"
COLOR_BTN_SHADOW_GREEN = "#1F9D46"
COLOR_BTN_SHADOW_RED = "#E53935"
COLOR_BTN_SHADOW_DISABLED = "#EEF0F3"

COLOR_SEGMENT_BG = "#F3F4F6"
COLOR_SEGMENT_BORDER = "#D9DEE7"
COLOR_SEGMENT_ACTIVE_BG = COLOR_BTN_ACTIVE_GREEN_BG
COLOR_SEGMENT_ACTIVE_TEXT = COLOR_BTN_ACTIVE_GREEN_TEXT
COLOR_SEGMENT_ACTIVE_HOVER_BG = COLOR_BTN_ACTIVE_GREEN_HOVER_BG
COLOR_SEGMENT_INACTIVE_BG = "#FFFFFF"
COLOR_SEGMENT_INACTIVE_TEXT = "#111827"
COLOR_SEGMENT_INACTIVE_HOVER_BG = "#F8FAFC"

# ---------------------------------------------------------------------------
# Legacy StateButton palette (kept for BUTTON_SHADOW_BLUR / radii)
# ---------------------------------------------------------------------------
BUTTON_BG_NORMAL = COLOR_BTN_DEFAULT_BG
BUTTON_TEXT_NORMAL = COLOR_BTN_DEFAULT_TEXT
BUTTON_BORDER_NORMAL = COLOR_BTN_DEFAULT_BORDER
BUTTON_SHADOW_NORMAL = COLOR_BTN_SHADOW_DEFAULT

BUTTON_BG_HOVER = COLOR_BTN_HOVER_BG
BUTTON_TEXT_HOVER = COLOR_BTN_HOVER_TEXT
BUTTON_BORDER_HOVER = COLOR_BTN_HOVER_BORDER
BUTTON_SHADOW_HOVER = COLOR_BTN_SHADOW_HOVER

BUTTON_BG_PRESSED = COLOR_BTN_ACTIVE_GREEN_BG
BUTTON_TEXT_PRESSED = COLOR_BTN_ACTIVE_GREEN_TEXT
BUTTON_BORDER_PRESSED = COLOR_BTN_ACTIVE_GREEN_BORDER
BUTTON_SHADOW_PRESSED = COLOR_BTN_SHADOW_GREEN

BUTTON_BG_DISABLED = COLOR_BTN_DISABLED_BG
BUTTON_TEXT_DISABLED = COLOR_BTN_DISABLED_TEXT
BUTTON_BORDER_DISABLED = COLOR_BTN_DISABLED_BORDER
BUTTON_SHADOW_DISABLED = COLOR_BTN_SHADOW_DISABLED

# Legacy red shadow variant used only for danger stop buttons
BUTTON_SHADOW_RED = COLOR_BTN_SHADOW_RED

BUTTON_BORDER_WIDTH = 2
BUTTON_RADIUS = 10
BUTTON_SHADOW_BLUR = 7
BUTTON_HOVER_SHADOW_BLUR = 10
BUTTON_PRESSED_SHADOW_BLUR = 5
BUTTON_SHADOW_OFFSET_Y = 1

# ---------------------------------------------------------------------------
# Qt sub-control resources
# Combo boxes use the native Qt/Windows arrow drawn via QProxyStyle (gray).
# Spin-box arrows keep the small bundled SVGs because Windows native steppers
# are visually inconsistent with the rest of the interface.
# ---------------------------------------------------------------------------
from pathlib import Path
_ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"
SPIN_ARROW_UP = (_ICON_DIR / "spin_up.svg").as_posix()
SPIN_ARROW_DOWN = (_ICON_DIR / "spin_down.svg").as_posix()


def build_stylesheet() -> str:
    """Return the application-wide Qt style sheet."""
    return f"""
    QWidget {{
        color: {TEXT};
    }}

    QMainWindow, QWidget#AppRoot {{
        background: {APP_BG};
    }}

    QFrame[card="true"] {{
        background: {CARD_BG};
        border: 1px solid transparent;
        border-radius: {CARD_RADIUS}px;
    }}

    QFrame[outline="true"] {{
        background: {CONTROL_BG};
        border: 1px solid {BORDER};
        border-radius: {CONTROL_RADIUS}px;
    }}

    QLabel[muted="true"] {{
        color: {TEXT_MUTED};
    }}

    QLabel[title="true"] {{
        font-weight: 600;
    }}

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
        background: {CONTROL_BG};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px 8px;
        selection-background-color: {SELECTED_BG};
        selection-color: {TEXT};
    }}

    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {BLUE_HOVER};
    }}

    /* ---------------------------------------------------------------
       Unified combo boxes: native gray Qt arrow, connected popup,
       no persistent focus rectangle, bottom-bar hover-preview hints.
       --------------------------------------------------------------- */
    QComboBox#UnifiedComboBox {{
        padding-left: 11px;
        padding-right: 30px;

        background-color: #FFFFFF;
        color: #111827;

        border: 1px solid #C8CDD5;
        border-radius: 10px;

        outline: none;
    }}

    QComboBox#UnifiedComboBox:hover {{
        background-color: #FAFBFC;
        border: 1px solid #AEB6C2;
    }}

    QComboBox#UnifiedComboBox:focus {{
        background-color: #FFFFFF;
        border: 1px solid #C8CDD5;
        outline: none;
    }}

    /* 展开后，下拉框变成整个组合框的顶部 */
    QComboBox#UnifiedComboBox[popupOpen="true"] {{
        background-color: #FFFFFF;

        border: 1px solid #C8CDD5;
        border-bottom: none;

        border-top-left-radius: 10px;
        border-top-right-radius: 10px;

        border-bottom-left-radius: 0px;
        border-bottom-right-radius: 0px;
    }}

    /* 箭头区域与输入区域使用同一背景，绝不割裂 */
    QComboBox#UnifiedComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;

        width: 30px;

        background-color: transparent;

        border: none;
        border-left: none;

        border-top-right-radius: 10px;
        border-bottom-right-radius: 10px;
    }}

    QComboBox#UnifiedComboBox::drop-down:hover {{
        background-color: transparent;
        border: none;
    }}

    /* 保留 PySide6 原生箭头，不设置 image/svg；颜色由 GrayComboArrowStyle 控制 */

    /* 可编辑下拉框的文本输入区 */
    QComboBox#UnifiedComboBox QLineEdit {{
        background-color: transparent;
        color: #111827;

        border: none;
        outline: none;

        selection-background-color: #E8EEF7;
        selection-color: #111827;
    }}

    QComboBox#UnifiedComboBox:disabled {{
        background-color: #F4F5F7;
        color: #9CA3AF;

        border: 1px solid #E5E7EB;
    }}

    /* ---------------------------------------------------------------
       Integer input boxes: plain line-edit integer entry, no steppers
       --------------------------------------------------------------- */
    QLineEdit#IntegerLineEdit {{
        padding: 0px 9px;

        background-color: #FFFFFF;
        color: #111827;

        border: 1px solid #D9DEE7;
        border-radius: 8px;

        selection-background-color: #E8EEF7;
        selection-color: #111827;
    }}

    QLineEdit#IntegerLineEdit:hover {{
        background-color: #F8FAFC;
        border: 1px solid #D9DEE7;
    }}

    QLineEdit#IntegerLineEdit:focus {{
        background-color: #FFFFFF;
        border: 1px solid #7DB2FF;
    }}

    /* ================================================================
       StateButton: three roles
         - default/hover/pressed : white base
         - :checked + [role="toggle"]   -> deep-green fill (所有普通开关)
         - :checked + [role="danger"]   -> solid red fill (停止监控/存储)
       ---------------------------------------------------------------- */
    QPushButton[stateButton="true"] {{
        background: {COLOR_BTN_DEFAULT_BG};
        color: {COLOR_BTN_DEFAULT_TEXT};
        border: {BUTTON_BORDER_WIDTH}px solid {COLOR_BTN_DEFAULT_BORDER};
        border-radius: {BUTTON_RADIUS}px;
        padding: 4px 11px;
        font-weight: 600;
        min-height: 18px;
    }}

    QPushButton[stateButton="true"]:hover {{
        background: {COLOR_BTN_HOVER_BG};
        color: {COLOR_BTN_HOVER_TEXT};
        border-color: {COLOR_BTN_HOVER_BORDER};
    }}

    QPushButton[stateButton="true"]:pressed {{
        background: {COLOR_BTN_PRESSED_BG};
        color: {COLOR_BTN_PRESSED_TEXT};
        border-color: {COLOR_BTN_PRESSED_BORDER};
        padding-top: 5px;
        padding-bottom: 3px;
    }}

    /* 普通 toggle (指令发送 / 指令库 / 置顶 / 协议解析 / 自动滚动 / 循环发送 / 协议模式 /
       自动追加校验位 / 自动发送 / 加回车换行 / HEX格式 等) */
    QPushButton[stateButton="true"][role="toggle"]:checked {{
        background: {COLOR_BTN_ACTIVE_GREEN_BG};
        color: {COLOR_BTN_ACTIVE_GREEN_TEXT};
        border-color: {COLOR_BTN_ACTIVE_GREEN_BORDER};
        padding-top: 5px;
        padding-bottom: 3px;
    }}

    QPushButton[stateButton="true"][role="toggle"]:checked:hover {{
        background: {COLOR_BTN_ACTIVE_GREEN_HOVER_BG};
        border-color: {COLOR_BTN_ACTIVE_GREEN_HOVER_BORDER};
    }}

    QPushButton[stateButton="true"][role="toggle"]:checked:pressed {{
        background: {COLOR_BTN_ACTIVE_GREEN_PRESSED_BG};
        border-color: {COLOR_BTN_ACTIVE_GREEN_PRESSED_BORDER};
    }}

    /* 危险停止态 (停止监控 / 停止存储数据) */
    QPushButton[stateButton="true"][role="danger"]:checked {{
        background: {COLOR_BTN_STOP_RED_BG};
        color: {COLOR_BTN_STOP_RED_TEXT};
        border-color: {COLOR_BTN_STOP_RED_BORDER};
        padding-top: 5px;
        padding-bottom: 3px;
    }}

    QPushButton[stateButton="true"][role="danger"]:checked:hover {{
        background: {COLOR_BTN_STOP_RED_HOVER_BG};
        border-color: {COLOR_BTN_STOP_RED_HOVER_BORDER};
    }}

    QPushButton[stateButton="true"][role="danger"]:checked:pressed {{
        background: {COLOR_BTN_STOP_RED_PRESSED_BG};
        border-color: {COLOR_BTN_STOP_RED_PRESSED_BORDER};
    }}

    /* 默认 fallback (无 role 属性)：为了保持旧代码兼容性，统一按深绿色激活 */
    QPushButton[stateButton="true"]:checked {{
        background: {COLOR_BTN_ACTIVE_GREEN_BG};
        color: {COLOR_BTN_ACTIVE_GREEN_TEXT};
        border-color: {COLOR_BTN_ACTIVE_GREEN_BORDER};
        padding-top: 5px;
        padding-bottom: 3px;
    }}

    QPushButton[stateButton="true"]:checked:hover {{
        background: {COLOR_BTN_ACTIVE_GREEN_HOVER_BG};
        border-color: {COLOR_BTN_ACTIVE_GREEN_HOVER_BORDER};
    }}

    QPushButton[stateButton="true"]:disabled {{
        background: {COLOR_BTN_DISABLED_BG};
        color: {COLOR_BTN_DISABLED_TEXT};
        border-color: {COLOR_BTN_DISABLED_BORDER};
    }}

    /* ================================================================
       Command Library HEX / ASCII segmented switch
       (一个整体控件，左右两段，选中段为深绿色)
       ---------------------------------------------------------------- */
    QWidget#CmdLibModeSwitch {{
        background: {COLOR_SEGMENT_BG};
        border: 1px solid {COLOR_SEGMENT_BORDER};
        border-radius: 12px;
    }}

    QWidget#CmdLibModeSwitch > QPushButton {{
        background: {COLOR_SEGMENT_INACTIVE_BG};
        color: {COLOR_SEGMENT_INACTIVE_TEXT};
        border: none;
        border-radius: 10px;
        padding: 4px 12px;
        font-weight: 600;
        min-height: 18px;
    }}

    QWidget#CmdLibModeSwitch > QPushButton:hover {{
        background: {COLOR_SEGMENT_INACTIVE_HOVER_BG};
    }}

    QWidget#CmdLibModeSwitch > QPushButton:checked {{
        background: {COLOR_SEGMENT_ACTIVE_BG};
        color: {COLOR_SEGMENT_ACTIVE_TEXT};
    }}

    QWidget#CmdLibModeSwitch > QPushButton:checked:hover {{
        background: {COLOR_SEGMENT_ACTIVE_HOVER_BG};
    }}

    QPushButton[stateButton="true"][tableButton="true"] {{
        min-width: 58px;
        max-width: 58px;
        min-height: 28px;
        max-height: 28px;
        padding: 2px 8px;
        border-width: 1px;
        border-radius: 7px;
        font-weight: 600;
    }}

    QPushButton[stateButton="true"][tableButton="true"]:hover {{
        color: {COLOR_BTN_ACTIVE_GREEN_BG};
        border-color: {COLOR_BTN_ACTIVE_GREEN_BORDER};
    }}

    QPushButton[stateButton="true"][tableButton="true"]:disabled {{
        background: {COLOR_BTN_DISABLED_BG};
        color: {COLOR_BTN_DISABLED_TEXT};
        border-color: {COLOR_BTN_DISABLED_BORDER};
    }}

    QPlainTextEdit#ReceiveDataView {{
        padding: 8px;
        background: {CONTROL_BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}

    QPlainTextEdit#ReceiveDataView:focus {{
        border: 1px solid {BORDER};
    }}

    QTableWidget {{
        background: {CARD_BG};
        alternate-background-color: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 6px;
        gridline-color: {LIBRARY_GRID_COLOR};
        selection-background-color: {SELECTED_BG};
        selection-color: {TEXT};
        outline: 0;
    }}

    QTableWidget::item {{
        padding: 2px 6px;
    }}

    QHeaderView::section {{
        background: {HEADER_BG};
        color: {TEXT};
        border: none;
        padding: 5px 6px;
        font-weight: 600;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
        margin: 2px 1px 2px 1px;
    }}

    QScrollBar::handle:vertical {{
        background: #C4CCD7;
        min-height: 24px;
        border-radius: 4px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: #8F9AAA;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
        border: none;
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 9px;
        margin: 1px 2px 1px 2px;
    }}

    QScrollBar::handle:horizontal {{
        background: #C4CCD7;
        min-width: 24px;
        border-radius: 4px;
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
        border: none;
        width: 0px;
    }}

    /* ---------------------------------------------------------------
       Table modern scrollbars (always-visible slot: stable column widths)
       --------------------------------------------------------------- */
    QTableView QScrollBar:vertical,
    QTableWidget QScrollBar:vertical {{
        width: 10px;

        margin: 2px 1px 2px 1px;

        background: #F4F6F9;

        border: none;
        border-radius: 5px;
    }}

    QTableView QScrollBar::handle:vertical,
    QTableWidget QScrollBar::handle:vertical {{
        min-height: 32px;

        background: #C8D0DB;

        border: none;
        border-radius: 4px;
    }}

    QTableView QScrollBar::handle:vertical:hover,
    QTableWidget QScrollBar::handle:vertical:hover {{
        background: #9DA8B7;
    }}

    QTableView QScrollBar::add-line:vertical,
    QTableView QScrollBar::sub-line:vertical,
    QTableWidget QScrollBar::add-line:vertical,
    QTableWidget QScrollBar::sub-line:vertical {{
        height: 0px;
        background: transparent;
        border: none;
    }}

    QTableView QScrollBar::add-page:vertical,
    QTableView QScrollBar::sub-page:vertical,
    QTableWidget QScrollBar::add-page:vertical,
    QTableWidget QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    QSplitter::handle {{
        background: transparent;
        width: {CARD_GAP}px;
    }}

    QToolTip {{
        background: {CARD_BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 4px 6px;
    }}
    """
