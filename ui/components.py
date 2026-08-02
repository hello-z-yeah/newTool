"""Reusable PySide6 widgets used by the serial protocol application."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, Iterator

from PySide6.QtCore import QEvent, QObject, QPoint, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFocusEvent, QFont, QFontMetrics, QIntValidator, QMouseEvent, QPalette, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QProxyStyle,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOption,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from .theme import (
    APP_BUTTON_HEIGHT,
    BORDER,
    BUTTON_HEIGHT,
    BUTTON_HOVER_SHADOW_BLUR,
    BUTTON_PRESSED_SHADOW_BLUR,
    BUTTON_SHADOW_BLUR,
    BUTTON_SHADOW_HOVER,
    BUTTON_SHADOW_NORMAL,
    BUTTON_SHADOW_OFFSET_Y,
    BUTTON_SHADOW_PRESSED,
    BUTTON_SHADOW_RED,
    BUTTON_SHADOW_PAD_X,
    BUTTON_SHADOW_PAD_Y,
    CARD_BG,
    CMDLIB_ACTION_PAD_X,
    CMDLIB_ACTION_PAD_Y,
    CMDLIB_SEND_BUTTON_WIDTH,
    CMDLIB_ROW_HEIGHT,
    CMDLIB_ROW_MIN_HEIGHT,
    COMBO_POPUP_QSS,
    COMBOBOX_QSS,
    CONTROL_HEIGHT,
    CONTROL_ROW_MIN_HEIGHT,
    LIBRARY_ACTION_WIDTH,
    LIBRARY_GRID_COLOR,
    LIBRARY_HEADER_HEIGHT,
    LIBRARY_MAX_ROWS,
    LIBRARY_NAME_WIDTH,
    LIBRARY_ROW_HEIGHT,
    LIBRARY_TYPE_WIDTH,
    RX_FONT_DEFAULT_SIZE,
    RX_FONT_MAX_SIZE,
    RX_FONT_MIN_SIZE,
    RX_FONT_STEP,
    SELECTED_BG,
    TEXT,
    UI_FONT_FAMILY,
)


# ui.components 不直接依赖业务逻辑；CommandLibraryStore 仅用于 normalize_mode
# （与 app.py 共用同一套合法 mode 校验）。
# 放 import 在主题之后，避免跨模块循环引用。
try:
    from ..core.command_library import CommandLibraryStore  # noqa: E402
except Exception:  # pragma: no cover - 仅作为直接单测 / 导入失败兜底
    class _FallbackStore:  # type: ignore[override]
        MODES = ("hex", "ascii")

        @staticmethod
        def normalize_mode(mode: str) -> str:
            value = str(mode or "").strip().lower()
            return value if value in _FallbackStore.MODES else "hex"

    CommandLibraryStore = _FallbackStore


@contextmanager
def signals_blocked(widget: QObject) -> Iterator[None]:
    blocker = QSignalBlocker(widget)
    try:
        yield
    finally:
        del blocker


class CardFrame(QFrame):
    """White rounded card used for the five main application sections."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)


class OutlineFrame(QFrame):
    """Light grey outlined content container."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("outline", True)


class IntegerLineEdit(QLineEdit):
    """只允许输入指定范围内的整数。

    保留 value()/setValue()/setRange() 接口，方便替换原来的 QSpinBox。
    """

    valueChanged = Signal(int)

    def __init__(
        self,
        value=0,
        minimum=0,
        maximum=100000,
        parent=None,
    ):
        super().__init__(parent)

        self._minimum = int(minimum)
        self._maximum = int(maximum)

        self._last_valid_value = (
            self._normalize(value)
        )

        self.setObjectName(
            "IntegerLineEdit"
        )

        self.setValidator(
            QIntValidator(
                self._minimum,
                self._maximum,
                self,
            )
        )

        self.setText(
            str(self._last_valid_value)
        )

        self.setAlignment(
            Qt.AlignCenter
        )

        self.editingFinished.connect(
            self._commit_value
        )

        self.returnPressed.connect(
            self._commit_value
        )

    def _normalize(self, value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = self._minimum

        return max(
            self._minimum,
            min(
                self._maximum,
                number,
            ),
        )

    def _commit_value(self):
        text = self.text().strip()

        if not text:
            self.setText(
                str(
                    self._last_valid_value
                )
            )
            return

        value = self._normalize(text)

        old_value = (
            self._last_valid_value
        )

        self._last_valid_value = value

        self.setText(
            str(value)
        )

        if value != old_value:
            self.valueChanged.emit(
                value
            )

    def value(self):
        return int(
            self._last_valid_value
        )

    def setValue(self, value):
        value = self._normalize(value)

        changed = (
            value
            != self._last_valid_value
        )

        self._last_valid_value = value

        self.setText(
            str(value)
        )

        if changed:
            self.valueChanged.emit(
                value
            )

    def setRange(
        self,
        minimum,
        maximum,
    ):
        self._minimum = int(minimum)
        self._maximum = int(maximum)

        self.setValidator(
            QIntValidator(
                self._minimum,
                self._maximum,
                self,
            )
        )

        self.setValue(
            self._last_valid_value
        )


class GrayComboArrowStyle(QProxyStyle):
    """保留Qt当前平台原生箭头形状，只将箭头颜色调整为灰色。"""

    def drawPrimitive(
        self,
        element,
        option,
        painter,
        widget=None,
    ):
        if (
            element
            == QStyle.PE_IndicatorArrowDown
            and isinstance(widget, QComboBox)
        ):
            styled_option = QStyleOption(
                option
            )

            palette = QPalette(
                styled_option.palette
            )

            arrow_color = QColor(
                "#7B8494"
            )

            palette.setColor(
                QPalette.ButtonText,
                arrow_color,
            )

            palette.setColor(
                QPalette.Text,
                arrow_color,
            )

            palette.setColor(
                QPalette.WindowText,
                arrow_color,
            )

            styled_option.palette = palette

            super().drawPrimitive(
                element,
                styled_option,
                painter,
                widget,
            )

            return

        super().drawPrimitive(
            element,
            option,
            painter,
            widget,
        )


def add_combo_item(
    combo: QComboBox,
    text,
    user_data=None,
    full_text=None,
) -> None:
    """Common helper: add a combo item and keep ToolTipRole for hover preview.

    Parameters
    ----------
    combo:
        Target combo (typically UnifiedComboBox).
    text:
        Display label (saved in DisplayRole & UserData fallback order unchanged
        by this helper).
    user_data:
        Value stored in Qt.UserRole via the native addItem(text, userData) API.
    full_text:
        Full content shown in status-bar hover preview.  Falls back to ``text``
        when not provided.  Stored in Qt.ItemDataRole.ToolTipRole.
    """
    combo.addItem(str(text), user_data)
    index = combo.count() - 1
    tip = str(full_text if full_text is not None else text)
    combo.setItemData(index, tip, Qt.ItemDataRole.ToolTipRole)


class UnifiedComboBox(QComboBox):
    """全程序统一下拉框。

    * 顶部控件 + 底部弹出列表视觉上是一个整体，中间无线/无缝隙；
    * 右侧箭头区域与主体同背景，绝不割裂；
    * 鼠标悬停任意选项时，发出 ``optionHovered(status_name, full_text)``
      信号给主窗口状态栏做预览；
    * 鼠标悬停本体时也发出当前选中项的状态栏预览；
    * 列表关闭后立即清除焦点蓝框；
    * 保留 Qt 原生箭头，颜色由 :class:`GrayComboArrowStyle` 调成灰色。
    """

    optionHovered = Signal(str, str)
    optionHoverCleared = Signal()

    def __init__(
        self,
        parent=None,
        *,
        status_name: str = "",
    ):
        super().__init__(parent)

        self._status_name = str(status_name).strip()

        self.setObjectName("UnifiedComboBox")
        self.setProperty("popupOpen", False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 必须保存引用，否则 QProxyStyle 可能被 GC 回收
        self._gray_arrow_style = GrayComboArrowStyle(self.style())
        self.setStyle(self._gray_arrow_style)

        # 控件级样式：白色框 + 15px 圆角，展开时下边框消失
        self.setStyleSheet(COMBOBOX_QSS)

        view = self.view()
        view.setObjectName("UnifiedComboView")
        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)

        # 下拉列表级样式：左右/下边框，下方圆角 18px，border-top: none
        view.setStyleSheet(COMBO_POPUP_QSS)

        # 悬停选项 -> 状态栏预览
        from PySide6.QtCore import QModelIndex  # noqa: WPS433 - local to avoid circular top-level

        view.entered.connect(self._on_option_hovered)
        view.viewport().installEventFilter(self)
        self._QModelIndex = QModelIndex

        # 本体悬停时：当前选项变化 -> 刷新状态栏显示
        self.currentIndexChanged.connect(self._refresh_hover_status)

    # ------------------------------------------------------------------
    # Hover preview (status-bar integration)
    # ------------------------------------------------------------------
    def _current_full_text(self) -> str:
        """获取当前选中项的完整内容（用于本体悬停提示）。"""
        index = self.currentIndex()
        if index >= 0:
            full_text = self.itemData(index, Qt.ItemDataRole.ToolTipRole)
            if full_text:
                return str(full_text).strip()
        return str(self.currentText() or "").strip()

    def _refresh_hover_status(self) -> None:
        """当前选中项变化且鼠标仍在本体上时，刷新状态栏显示。"""
        if not self.underMouse():
            return
        full_text = self._current_full_text()
        if full_text:
            self.optionHovered.emit(self._status_name, full_text)

    def _apply_hover_glow(self) -> None:
        """本体悬停时的视觉处理（当前由 QSS :hover 负责，保留钩子）。"""
        self.update()

    def _apply_normal_glow(self) -> None:
        """本体离开时的视觉处理（当前由 QSS 负责，保留钩子）。"""
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._apply_hover_glow()
        full_text = self._current_full_text()
        if full_text:
            self.optionHovered.emit(self._status_name, full_text)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        # 列表打开时，鼠标会从本体移动到弹出列表，
        # 此时不要提前清除状态栏提示。
        if not bool(self.property("popupOpen")):
            self.optionHoverCleared.emit()
            self._apply_normal_glow()
        super().leaveEvent(event)

    def _on_option_hovered(self, index) -> None:
        if not isinstance(index, self._QModelIndex) or not index.isValid():
            self.optionHoverCleared.emit()
            return

        full_text = index.data(Qt.ItemDataRole.ToolTipRole)
        if not full_text:
            full_text = index.data(Qt.ItemDataRole.DisplayRole)
        full_text = str(full_text or "").strip()

        if not full_text:
            self.optionHoverCleared.emit()
            return

        self.optionHovered.emit(self._status_name, full_text)

    def eventFilter(self, watched, event):  # noqa: N802 - Qt API
        view = self.view()
        if view is not None and watched is view.viewport():
            if event.type() in (QEvent.Type.Leave, QEvent.Type.Hide):
                self.optionHoverCleared.emit()
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Popup lifecycle
    # ------------------------------------------------------------------
    def hidePopup(self) -> None:  # noqa: N802 - Qt API
        super().hidePopup()

        self.setProperty("popupOpen", False)
        self._repolish()

        # 关闭/选中后立即清理状态栏提示 + 释放焦点，去掉蓝框
        self.optionHoverCleared.emit()
        QTimer.singleShot(0, self.clearFocus)

    def showPopup(self) -> None:  # noqa: N802 - Qt API
        self.setProperty("popupOpen", True)
        self._repolish()
        super().showPopup()
        QTimer.singleShot(0, self._merge_popup_geometry)

    # ------------------------------------------------------------------
    # Geometry / styling helpers
    # ------------------------------------------------------------------
    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()

    def _merge_popup_geometry(self) -> None:
        view = self.view()
        popup = view.window()
        if popup is None:
            return

        popup.setObjectName("UnifiedComboPopup")
        popup.setContentsMargins(0, 0, 0, 0)
        view.setContentsMargins(0, 0, 0, 0)

        # 外层 QFrame 透明：真正的边框只由 QListView 负责（避免双外框）
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setStyleSheet(
            """
            QFrame#UnifiedComboPopup {
                background: transparent;
                border: none;
            }
            """
        )

        global_pos = self.mapToGlobal(QPoint(0, 0))
        current_geometry = popup.geometry()

        # 默认与上方下拉框等宽，列表向上覆盖 1px 消除中间空隙
        popup_width = self.width()
        popup_y = global_pos.y() + self.height() - 1

        popup.setGeometry(
            global_pos.x(),
            popup_y,
            popup_width,
            current_geometry.height(),
        )
        popup.update()


def ComboBox(
    parent=None,
    *,
    editable: bool = False,
    status_name: str = "",
):
    """下拉框工厂函数，全程序统一使用。"""
    combo = UnifiedComboBox(parent, status_name=status_name)
    combo.setEditable(editable)
    return combo


class StateButton(QPushButton):
    """Three-state button with an optional persistent checked state.

    Supported roles (set via ``role`` argument or :meth:`set_role`):

    * ``"toggle"`` (default for any checkable button):
      ``:checked`` -> deep green fill. Covers: 指令发送 / 指令库 / 置顶 /
      协议解析模式 / 自动滚动 / 循环发送 / 协议模式 / 自动追加校验位 /
      自动发送 / 加回车换行 / HEX格式 等普通开关。
    * ``"danger"``: used only for the "stop" running action buttons.
      ``:checked`` -> solid red fill.  Covers: 停止监控 / 停止存储数据.
    * ``"action"``: plain transient push button (never changes fill color
      on press).  Used for 刷新 / 清空 / 配置循环 / 发送 等一次性动作.

    The pressed appearance is identical to the checked appearance for the
    matching role, so momentary toggles feel the same as persistent toggles.
    """

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        checkable: bool = False,
        shadow: bool = True,
        role: str | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("stateButton", True)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._hovered = False
        self._pressed = False
        self._shadow_enabled = shadow
        self._shadow: QGraphicsDropShadowEffect | None = None

        if role is None:
            role = "toggle" if checkable else "action"
        self.set_role(role)

        if shadow:
            self._shadow = QGraphicsDropShadowEffect(self)
            self.setGraphicsEffect(self._shadow)

        self.toggled.connect(self._update_shadow)
        self.pressed.connect(self._on_pressed_signal)
        self.released.connect(self._on_released_signal)
        self._update_shadow()

    def role(self) -> str:
        value = self.property("role")
        if isinstance(value, str) and value:
            return value
        return "toggle" if self.isCheckable() else "action"

    def set_role(self, role: str) -> None:
        if role not in {"toggle", "danger", "action"}:
            role = "toggle" if self.isCheckable() else "action"
        self.setProperty("role", role)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        self._update_shadow()

    def set_active(self, active: bool) -> None:
        if not self.isCheckable():
            self.setCheckable(True)
        self.setChecked(bool(active))
        self._update_shadow()

    def set_disabled(self, disabled: bool) -> None:
        self.setDisabled(bool(disabled))
        self._update_shadow()

    def _on_pressed_signal(self) -> None:
        self._pressed = True
        self._update_shadow()

    def _on_released_signal(self) -> None:
        self._pressed = False
        self._update_shadow()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        self._hovered = True
        self._update_shadow()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        self._hovered = False
        self._pressed = False
        self._update_shadow()
        super().leaveEvent(event)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self._update_shadow()

    def _update_shadow(self) -> None:
        if self._shadow is None:
            return

        if not self.isEnabled():
            color = QColor("#EEF0F3")
            blur = 5
            offset = 1
        elif self.isChecked() or self._pressed:
            # Persistent toggles use semantic colors; momentary action buttons
            # keep a neutral pressed shadow.
            if self.role() == "danger":
                shadow_color = BUTTON_SHADOW_RED
            elif self.role() == "toggle":
                shadow_color = BUTTON_SHADOW_PRESSED
            else:
                shadow_color = "#CBD5E1"
            color = QColor(shadow_color)
            blur = BUTTON_PRESSED_SHADOW_BLUR
            offset = 1
        elif self._hovered:
            color = QColor(BUTTON_SHADOW_HOVER)
            color.setAlpha(145)
            blur = BUTTON_HOVER_SHADOW_BLUR
            offset = BUTTON_SHADOW_OFFSET_Y
        else:
            color = QColor(BUTTON_SHADOW_NORMAL)
            color.setAlpha(125)
            blur = BUTTON_SHADOW_BLUR
            offset = BUTTON_SHADOW_OFFSET_Y

        self._shadow.setColor(color)
        self._shadow.setBlurRadius(blur)
        self._shadow.setOffset(0, offset)


class SegmentToggle(QWidget):
    """分段切换控件：一个外框 + 两个互斥段（默认 HEX / ASCII）。

    * 视觉：未选中 = 默认按钮样式；选中 = 绿色高亮。
    * 信号：只使用统一的 ``valueChanged(str)``（小写，"hex" / "ascii"）。
      ``modeChanged(str)`` 作为旧代码的兼容别名同时发出，不建议新代码继续使用。
    * 内部通过 ``QPushButton.clicked.connect(lambda _checked=False: _select_value(...))``
      显式忽略 ``clicked(bool)`` 传入的布尔参数，避免把 True / False 当成字符串 mode。
    """

    modeChanged = Signal(str)
    valueChanged = Signal(str)

    def __init__(
        self,
        left_text: str = "HEX",
        right_text: str = "ASCII",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CmdLibModeSwitch")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(CONTROL_HEIGHT)

        self._left_value = str(left_text).strip().lower()
        self._right_value = str(right_text).strip().lower()
        self._value = self._left_value

        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self.left_button = QPushButton(left_text, self)
        self.left_button.setCheckable(True)
        self.left_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.left_button.setMinimumWidth(48)
        self._group.addButton(self.left_button)

        self.right_button = QPushButton(right_text, self)
        self.right_button.setCheckable(True)
        self.right_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.right_button.setMinimumWidth(56)
        self._group.addButton(self.right_button)

        outer.addWidget(self.left_button)
        outer.addWidget(self.right_button)

        # —— 关键：显式忽略 clicked(bool) 传入的布尔参数，
        #    永远用 _left_value / _right_value 这两个字符串，
        #    避免 lambda 的默认值被 True/False 覆盖。
        self.left_button.clicked.connect(
            lambda _checked=False: self._select_value(self._left_value)
        )
        self.right_button.clicked.connect(
            lambda _checked=False: self._select_value(self._right_value)
        )

        self.setValue(self._left_value, emit_signal=False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _select_value(self, value: str) -> None:
        normalized = str(value or "").strip().lower()
        if normalized not in {self._left_value, self._right_value}:
            return

        changed = normalized != self._value
        self._value = normalized
        self._apply_checked_state()

        if changed:
            self.valueChanged.emit(normalized)
            self.modeChanged.emit(normalized)

    def _apply_checked_state(self) -> None:
        left_selected = self._value == self._left_value

        # QSignalBlocker：同步视觉状态时，不要再触发 left/right 各自的 clicked
        left_blocker = QSignalBlocker(self.left_button)
        right_blocker = QSignalBlocker(self.right_button)
        try:
            self.left_button.setChecked(left_selected)
            self.right_button.setChecked(not left_selected)
        finally:
            # 显式 del 确保立即解除阻塞
            del left_blocker
            del right_blocker

    # ------------------------------------------------------------------
    # Public API（推荐直接使用 value/setValue；set_mode/mode 为兼容旧名）
    # ------------------------------------------------------------------
    def setValue(
        self,
        value: str,
        *,
        emit_signal: bool = False,
    ) -> None:
        normalized = str(value or "").strip().lower()
        if normalized not in {self._left_value, self._right_value}:
            return

        changed = normalized != self._value
        self._value = normalized
        self._apply_checked_state()

        if emit_signal and changed:
            self.valueChanged.emit(normalized)
            self.modeChanged.emit(normalized)

    def value(self) -> str:
        return self._value

    # ---------- 兼容旧代码的别名 ----------
    def set_mode(self, mode: str, *, block_external: bool = True) -> None:
        self.setValue(mode, emit_signal=not block_external)

    def mode(self) -> str:
        return self.value()

    def hex_button(self) -> QPushButton:
        return self.left_button

    def ascii_button(self) -> QPushButton:
        return self.right_button


class ReorderableCycleTable(QTableWidget):
    """QTableWidget 只负责拖动视觉与目标行计算；真正的顺序重排在外部 QTimer.singleShot(0) 后执行。

    关键约束（必须严格遵守，否则 cellWidget + Qt InternalMove 会双移动导致 C++ 崩溃）：
    * ``dropEvent`` 中绝对不能调用 ``super().dropEvent(event)``；
    * ``dropEvent`` 中绝对不能执行 ``setRowCount / removeRow / insertRow / clearContents /
      setCellWidget`` 或任何重建控件的操作；
    * 只计算 ``(source_row, target_row)`` 两个整数，并用 ``QTimer.singleShot(0)`` 延后
      发出 ``rowsReordered``。
    """

    rowsReordered = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._drag_source_row = -1
        self._drop_pending = False

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        # 拖动由第一列☰或行空白区域发起；单击普通单元格不会立即误触编辑
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)

    # ------------------------------------------------------------------
    # Drag helpers
    # ------------------------------------------------------------------
    def startDrag(self, supported_actions):  # noqa: N802
        source_row = self.currentRow()
        if source_row < 0:
            return
        self._drag_source_row = int(source_row)
        super().startDrag(supported_actions)

    def dropEvent(self, event):  # noqa: N802
        """仅计算目标位置，不修改任何表格结构；重建动作延后到 QTimer.singleShot(0)。"""
        if self._drop_pending:
            event.ignore()
            return

        source_row = int(self._drag_source_row)
        total_rows = int(self.rowCount())

        if not (0 <= source_row < total_rows):
            event.ignore()
            self._drag_source_row = -1
            return

        position = event.position().toPoint()
        index = self.indexAt(position)
        if index.isValid():
            target_row = int(index.row())
            target_rect = self.visualRect(index)
            # 落在目标行下半部分：插入该行之后
            if position.y() > target_rect.center().y():
                target_row += 1
        else:
            # 拖到表格下方空白区：放到最后
            target_row = total_rows

        # 从前面拖到后面：pop 之后目标索引需要 -1
        if source_row < target_row:
            target_row -= 1
        # 钳制到合法区间（0..total_rows-1）
        target_row = max(0, min(target_row, total_rows - 1)) if total_rows else 0

        if source_row == target_row:
            event.ignore()
            self._drag_source_row = -1
            return

        self._drop_pending = True
        self._drag_source_row = -1

        # 自己处理顺序，不再走 Qt 原生 InternalMove（避免与我们之后的重建双移动崩溃）
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

        # 等 Qt 拖放事件栈完全 unwound 再对外触发重排 + 重建
        QTimer.singleShot(
            0,
            lambda source=source_row, target=target_row: self._emit_deferred_reorder(
                source, target
            ),
        )

    def _emit_deferred_reorder(self, source_row: int, target_row: int) -> None:
        try:
            self.rowsReordered.emit(int(source_row), int(target_row))
        finally:
            self._drop_pending = False


class HoverScrollController(QObject):
    """Show a vertical scroll bar only while hovered and content overflows."""

    def __init__(self, area: QAbstractScrollArea, *, hide_delay_ms: int = 80) -> None:
        super().__init__(area)
        self.area = area
        self.hide_delay_ms = max(0, int(hide_delay_ms))
        self._inside = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._confirm_leave)

        self.area.installEventFilter(self)
        self.area.viewport().installEventFilter(self)
        self.area.verticalScrollBar().installEventFilter(self)
        self.area.verticalScrollBar().rangeChanged.connect(self.refresh)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            self._hide_timer.stop()
            self._inside = True
            self.refresh()
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self._hide_timer.start(self.hide_delay_ms)
        elif event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Wheel,
            QEvent.Type.MouseMove,
        ):
            QTimer.singleShot(0, self.refresh)
        return super().eventFilter(watched, event)

    def has_overflow(self) -> bool:
        bar = self.area.verticalScrollBar()
        return bar.maximum() > bar.minimum()

    def refresh(self, *_args: object) -> None:
        show = self._inside and self.has_overflow() and self.area.isVisible()
        target = (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            if show
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if self.area.verticalScrollBarPolicy() != target:
            self.area.setVerticalScrollBarPolicy(target)

    def reset(self) -> None:
        self.area.verticalScrollBar().setValue(0)
        self._inside = False
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _confirm_leave(self) -> None:
        local = self.area.mapFromGlobal(QCursor.pos())
        self._inside = self.area.rect().contains(local)
        self.refresh()


class CellLineEdit(QLineEdit):
    """Borderless table editor that reports its logical row."""

    activated = Signal(int)
    commitRequested = Signal(int)

    def __init__(self, row: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.row_index = row
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrame(False)
        self.setStyleSheet(
            "QLineEdit { border: none; border-radius: 0; background: transparent; "
            "padding: 0 4px; } QLineEdit:focus { border: none; background: #FFFFFF; }"
        )
        self.editingFinished.connect(lambda: self.commitRequested.emit(self.row_index))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.activated.emit(self.row_index)
        super().mousePressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:  # noqa: N802
        self.activated.emit(self.row_index)
        super().focusInEvent(event)


class CommandLibraryTable(QTableWidget):
    """Fixed 40-row HEX/ASCII command library with direct cell editing."""

    rowSelected = Signal(int)
    rowCommitRequested = Signal(int, str, str)
    sendRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(LIBRARY_MAX_ROWS, 4, parent)
        self._updating = False
        self._mode = "hex"
        self._real_count = 0
        self._name_edits: list[CellLineEdit] = []
        self._data_edits: list[CellLineEdit] = []
        self._type_items: list[QTableWidgetItem] = []
        self._send_buttons: list[StateButton] = []
        # 统一按钮宽度，不随内容变化
        self._send_button_width = CMDLIB_SEND_BUTTON_WIDTH

        self.setHorizontalHeaderLabels(["名称", "CMD类型", "指令数据", "操作"])
        self.verticalHeader().setVisible(False)
        # 统一固定行高（40px = 按钮高 32 + 上下 4px 内边距），禁止单行自适应
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setDefaultSectionSize(CMDLIB_ROW_HEIGHT)
        self.verticalHeader().setMinimumSectionSize(CMDLIB_ROW_HEIGHT)
        self.horizontalHeader().setFixedHeight(LIBRARY_HEADER_HEIGHT)

        # 列宽策略保持稳定：滚动条常显槽位不变时不会改变列宽
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.setColumnWidth(0, LIBRARY_NAME_WIDTH)
        self.setColumnWidth(1, LIBRARY_TYPE_WIDTH)
        # 操作列宽度 = 按钮宽(58) + 左右内边距各5 + 安全余量 8
        self.setColumnWidth(
            3,
            CMDLIB_SEND_BUTTON_WIDTH + CMDLIB_ACTION_PAD_X * 2 + 8,
        )

        # 滚动条常显：消除显/隐藏时导致列宽跳动
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setShowGrid(True)
        self.setGridStyle(Qt.PenStyle.SolidLine)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setStyleSheet(
            f"QTableWidget {{ gridline-color: {LIBRARY_GRID_COLOR}; }}"
            "QHeaderView::section { border: none; }"
        )

        self._build_rows()
        self.currentCellChanged.connect(self._on_current_cell_changed)

    def _build_rows(self) -> None:
        for row in range(LIBRARY_MAX_ROWS):
            name_edit = CellLineEdit(row, self)
            name_edit.activated.connect(self.select_row)
            name_edit.commitRequested.connect(self._emit_commit)
            self.setCellWidget(row, 0, name_edit)
            self._name_edits.append(name_edit)

            type_item = QTableWidgetItem("HEX")
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            type_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.setItem(row, 1, type_item)
            self._type_items.append(type_item)

            data_edit = CellLineEdit(row, self)
            data_edit.activated.connect(self.select_row)
            data_edit.commitRequested.connect(self._emit_commit)
            self.setCellWidget(row, 2, data_edit)
            self._data_edits.append(data_edit)

            # 使用与主发送按钮相同的公共类 StateButton，仅宽度收窄
            send_button = StateButton("发送", self)
            # 不再使用单独的 tableButton 样式角色，复用主按钮样式
            # 统一尺寸：高度与主发送按钮完全一致（APP_BUTTON_HEIGHT）
            send_button.setFixedHeight(APP_BUTTON_HEIGHT)
            send_button.setFixedWidth(CMDLIB_SEND_BUTTON_WIDTH)
            send_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            send_button.clicked.connect(
                lambda _checked=False, index=row: self.sendRequested.emit(index)
            )

            # 发送按钮装入居中容器：上下各 4px 内边距，按钮竖向完整显示
            action_container = QWidget(self)
            action_container.setObjectName("CommandActionCell")
            action_container.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            action_layout = QHBoxLayout(action_container)
            action_layout.setContentsMargins(
                CMDLIB_ACTION_PAD_X,
                CMDLIB_ACTION_PAD_Y,
                CMDLIB_ACTION_PAD_X,
                CMDLIB_ACTION_PAD_Y,
            )
            action_layout.setSpacing(0)
            action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            action_layout.addWidget(send_button, 0, Qt.AlignmentFlag.AlignCenter)
            self.setCellWidget(row, 3, action_container)
            self._send_buttons.append(send_button)

    def set_items(self, items: Iterable[dict], mode: str) -> None:
        values = list(items)[:LIBRARY_MAX_ROWS]
        self._mode = CommandLibraryStore.normalize_mode(mode)
        mode_text = self._mode.upper()
        self._real_count = len(values)
        self._updating = True
        try:
            for row in range(LIBRARY_MAX_ROWS):
                item = values[row] if row < len(values) else None
                name = str(item.get("name", "")) if item else ""
                payload = str(item.get("payload", item.get("data", ""))) if item else ""

                # 关键：type 永远由当前页面 mode 决定，不再信任旧数据里的 type 字段。
                # 以前 ASCII 页面也会出现 HEX，就是这里写死或沿用了 item["type"]。
                cmd_type = mode_text

                with signals_blocked(self._name_edits[row]):
                    self._name_edits[row].setText(name)
                with signals_blocked(self._data_edits[row]):
                    self._data_edits[row].setText(payload)
                self._type_items[row].setText(cmd_type)
                self._send_buttons[row].setEnabled(bool(payload.strip()))
        finally:
            self._updating = False

    def selected_index(self) -> int | None:
        row = self.currentRow()
        return row if row >= 0 else None

    def focus_first_empty(self, real_count: int) -> None:
        row = min(max(0, int(real_count)), LIBRARY_MAX_ROWS - 1)
        self.select_row(row)
        self.scrollToItem(self.item(row, 1), QAbstractItemView.ScrollHint.PositionAtCenter)
        self._name_edits[row].setFocus(Qt.FocusReason.OtherFocusReason)
        self._name_edits[row].setCursorPosition(len(self._name_edits[row].text()))

    def select_row(self, row: int) -> None:
        if 0 <= row < LIBRARY_MAX_ROWS:
            self.setCurrentCell(row, 0)
            self.selectRow(row)
            self.rowSelected.emit(row)

    def row_values(self, row: int) -> tuple[str, str]:
        return self._name_edits[row].text().strip(), self._data_edits[row].text().strip()

    def _emit_commit(self, row: int) -> None:
        if self._updating or not 0 <= row < LIBRARY_MAX_ROWS:
            return
        name, payload = self.row_values(row)
        self.rowCommitRequested.emit(row, name, payload)

    def _on_current_cell_changed(self, current_row: int, _current_column: int, *_args: int) -> None:
        if current_row >= 0:
            self.rowSelected.emit(current_row)


def set_button_width_for_texts(button, texts, extra_width: int = 28) -> None:
    """根据按钮可能出现的所有文案，提前固定最小宽度。

    用于开始/停止、展开/收起、HEX/ASCII 等状态切换按钮，避免切换时重新布局
    或文字被裁切。
    """
    metrics = QFontMetrics(button.font())
    text_width = max(metrics.horizontalAdvance(str(text)) for text in texts)
    button.setFixedWidth(text_width + int(extra_width))


class ZoomableDataView(QPlainTextEdit):
    """实时数据显示框。

    * 默认复制全局 QApplication 字体（继承全局加粗），只覆盖字号和可选字体族；
    * 默认字号 ``RX_FONT_DEFAULT_SIZE``（与主界面字号一致）；
    * ``Ctrl + 鼠标滚轮`` 调整字号（范围 RX_FONT_MIN~MAX）；
    * 普通滚轮仍用于上下滚动；
    * 通过 ``displayStatsChanged`` 发出当前显示内容字节数与总行数统计。
    """

    fontSizeChanged = Signal(int)
    displayStatsChanged = Signal(int, int)

    def __init__(
        self,
        parent=None,
        *,
        font_size=RX_FONT_DEFAULT_SIZE,
    ):
        super().__init__(parent)
        self.setObjectName("ReceiveDataView")

        self._font_size = self._clamp_size(font_size)
        self._apply_font()
        # 80ms 内重复触发只统计一次
        self._stats_timer: QTimer | None = None

    @staticmethod
    def _clamp_size(value) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = RX_FONT_DEFAULT_SIZE
        return max(
            RX_FONT_MIN_SIZE,
            min(
                RX_FONT_MAX_SIZE,
                value,
            ),
        )

    def _apply_font(self):
        # 复制全局字体，保留全局加粗设置
        font = QFont(QApplication.font())
        font.setPointSize(self._font_size)
        self.setFont(font)
        document = self.document()
        if document is not None:
            document.setDefaultFont(font)
        self.viewport().update()

    def setDataFontSize(self, size):
        size = self._clamp_size(size)
        if size == self._font_size:
            return
        self._font_size = size
        self._apply_font()
        self.fontSizeChanged.emit(size)

    def dataFontSize(self) -> int:
        return self._font_size

    # ------------------------------------------------------------
    # 显示内容统计：字节数 + 总行数（防抖 80ms）
    # ------------------------------------------------------------
    def scheduleDisplayStatsUpdate(self) -> None:
        """在插入/清空/裁剪/重渲染完成后调用，触发防抖统计。"""
        if self._stats_timer is None:
            self._stats_timer = QTimer(self)
            self._stats_timer.setSingleShot(True)
            self._stats_timer.timeout.connect(self._emit_display_stats)
        self._stats_timer.start(80)

    def _emit_display_stats(self) -> None:
        document = self.document()
        if document is None:
            self.displayStatsChanged.emit(0, 0)
            return
        text = self.toPlainText()
        # 按 UTF-8 计算字节数，占位提示文字会因空文本自动变成 0 行 0 字节
        byte_count = len(text.encode("utf-8", errors="replace")) if text else 0
        line_count = 0
        if text:
            line_count = int(document.blockCount())
        self.displayStatsChanged.emit(int(byte_count), int(line_count))

    def clear(self) -> None:
        # 保持 QPlainTextEdit.clear 语义，同时安排一次统计归零
        super().clear()
        self.scheduleDisplayStatsUpdate()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.setDataFontSize(self._font_size + RX_FONT_STEP)
            elif delta < 0:
                self.setDataFontSize(self._font_size - RX_FONT_STEP)
            event.accept()
            return
        # 没按Ctrl时正常滚动数据
        super().wheelEvent(event)
