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

    # ------------------------------------------------------------------
    # Hover preview (status-bar integration)
    # ------------------------------------------------------------------
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
    """Segmented toggle switch rendered as one unified control.

    Used by the command library toolbar for the HEX / ASCII mode switch.
    The outer widget (objectName = ``CmdLibModeSwitch``) draws a single
    rounded frame; the inner segments are mutually exclusive ``QPushButton``
    children.  Clicking a segment emits :attr:`modeChanged` with the
    corresponding lower-case mode (``"hex"`` / ``"ascii"``).
    """

    modeChanged = Signal(str)

    def __init__(
        self,
        left_label: str = "HEX",
        right_label: str = "ASCII",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CmdLibModeSwitch")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(CONTROL_HEIGHT)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self._segments: dict[str, QPushButton] = {}

        left_btn = QPushButton(left_label, self)
        left_btn.setCheckable(True)
        left_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        left_btn.setMinimumWidth(48)
        self._group.addButton(left_btn)
        self._segments[left_label.lower()] = left_btn
        outer.addWidget(left_btn)

        right_btn = QPushButton(right_label, self)
        right_btn.setCheckable(True)
        right_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        right_btn.setMinimumWidth(56)
        self._group.addButton(right_btn)
        self._segments[right_label.lower()] = right_btn
        outer.addWidget(right_btn)

        left_btn.clicked.connect(lambda _c=False, m=left_label.lower(): self._on_segment_clicked(m))
        right_btn.clicked.connect(lambda _c=False, m=right_label.lower(): self._on_segment_clicked(m))

    def _on_segment_clicked(self, mode: str) -> None:
        self.set_mode(mode, block_external=False)

    def mode(self) -> str | None:
        for key, btn in self._segments.items():
            if btn.isChecked():
                return key
        return None

    def set_mode(self, mode: str, *, block_external: bool = True) -> None:
        key = str(mode).lower()
        if key not in self._segments:
            return
        for k, btn in self._segments.items():
            was_checked = btn.isChecked()
            if block_external:
                with signals_blocked(btn):
                    btn.setChecked(k == key)
            else:
                btn.setChecked(k == key)
            if k == key and not was_checked:
                self.modeChanged.emit(k)

    def hex_button(self) -> QPushButton:
        return self._segments["hex"]

    def ascii_button(self) -> QPushButton:
        return self._segments["ascii"]


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
        self._send_button_width = 78

        self.setHorizontalHeaderLabels(["名称", "CMD类型", "指令数据", "操作"])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(LIBRARY_ROW_HEIGHT)
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
        self.setColumnWidth(3, LIBRARY_ACTION_WIDTH)

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

    @staticmethod
    def _command_row_height(send_button) -> int:
        button_height = max(
            send_button.minimumSizeHint().height(),
            send_button.sizeHint().height(),
            send_button.minimumHeight(),
        )
        return max(
            CMDLIB_ROW_MIN_HEIGHT,
            button_height + CMDLIB_ACTION_PAD_Y * 2,
        )

    def _build_rows(self) -> None:
        resolved_row_height: int | None = None
        resolved_action_width: int | None = None

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

            send_button = StateButton("发送", self, shadow=False)
            send_button.setProperty("tableButton", True)
            send_button.setFixedSize(58, 28)
            send_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            send_button.clicked.connect(lambda _checked=False, index=row: self.sendRequested.emit(index))

            # 发送按钮装入居中容器：用主题统一留白，避免阴影/按钮被裁切
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

            send_button.ensurePolished()
            current_row_height = self._command_row_height(send_button)
            button_size = send_button.sizeHint()
            current_action_width = max(
                LIBRARY_ACTION_WIDTH,
                button_size.width() + CMDLIB_ACTION_PAD_X * 2 + 4,
            )
            if resolved_row_height is None:
                resolved_row_height = current_row_height
                resolved_action_width = current_action_width

        # 所有 40 行 + 垂直表头使用统一固定行高，禁止后续自动压缩裁切按钮
        v_header = self.verticalHeader()
        v_header.setDefaultSectionSize(resolved_row_height or CMDLIB_ROW_MIN_HEIGHT)
        v_header.setMinimumSectionSize(resolved_row_height or CMDLIB_ROW_MIN_HEIGHT)
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        if resolved_action_width is not None:
            self.setColumnWidth(3, resolved_action_width)

    def set_items(self, items: Iterable[dict], mode: str) -> None:
        values = list(items)[:LIBRARY_MAX_ROWS]
        self._mode = str(mode or "hex").lower()
        mode_text = self._mode.upper()
        self._real_count = len(values)
        self._updating = True
        try:
            for row in range(LIBRARY_MAX_ROWS):
                item = values[row] if row < len(values) else None
                name = str(item.get("name", "")) if item else ""
                payload = str(item.get("payload", item.get("data", ""))) if item else ""
                cmd_type = str(item.get("type", mode_text)).upper() if item else mode_text

                with signals_blocked(self._name_edits[row]):
                    self._name_edits[row].setText(name)
                with signals_blocked(self._data_edits[row]):
                    self._data_edits[row].setText(payload)
                self._type_items[row].setText(cmd_type or mode_text)
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

    * 默认使用 ``UI_FONT_FAMILY`` + ``RX_FONT_DEFAULT_SIZE``，与主界面一致；
    * ``Ctrl + 鼠标滚轮`` 调整字号（范围 RX_FONT_MIN~MAX）；
    * 普通滚轮仍用于上下滚动。
    """

    fontSizeChanged = Signal(int)

    def __init__(
        self,
        parent=None,
        *,
        font_family: str = UI_FONT_FAMILY,
        font_size: int = RX_FONT_DEFAULT_SIZE,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ReceiveDataView")

        self._font_family = str(font_family or UI_FONT_FAMILY)
        self._font_size = self._clamp_font_size(font_size)
        self._apply_data_font()

    @staticmethod
    def _clamp_font_size(value) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = RX_FONT_DEFAULT_SIZE
        return max(RX_FONT_MIN_SIZE, min(RX_FONT_MAX_SIZE, value))

    def _apply_data_font(self) -> None:
        app = QApplication.instance()
        font = QFont(app.font()) if app is not None else QFont()
        if self._font_family:
            font.setFamily(self._font_family)
        font.setPointSize(max(1, int(self._font_size)))
        self.setFont(font)
        document = self.document()
        if document is not None:
            document.setDefaultFont(font)
        self.viewport().update()

    def setDataFontSize(self, size) -> None:
        size = self._clamp_font_size(size)
        if size == self._font_size:
            return
        self._font_size = size
        self._apply_data_font()
        self.fontSizeChanged.emit(size)

    def dataFontSize(self) -> int:
        return self._font_size

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                new_size = self._font_size + RX_FONT_STEP
            elif delta < 0:
                new_size = self._font_size - RX_FONT_STEP
            else:
                event.accept()
                return
            self.setDataFontSize(new_size)
            event.accept()
            return
        super().wheelEvent(event)
