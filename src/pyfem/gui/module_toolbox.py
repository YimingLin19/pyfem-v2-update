from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(slots=True, frozen=True)
class ToolboxButtonSpec:
    """描述模块工具箱中的一个按钮。"""

    key: str
    label: str
    action: QAction
    icon: QIcon
    tooltip: str


class ModuleToolbox(QWidget):
    """提供经典 CAE 风格的模块工具箱竖栏。"""

    FIXED_WIDTH = 72

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._buttons_by_key: dict[str, QToolButton] = {}
        self._buttons_by_action: dict[QAction, QToolButton] = {}
        self._current_module = "Part"
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("ModuleToolboxPane")
        self.setMinimumWidth(self.FIXED_WIDTH)
        self.setMaximumWidth(self.FIXED_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_frame = QFrame(self)
        header_frame.setObjectName("ToolboxHeader")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(4, 3, 4, 3)
        header_layout.setSpacing(2)

        self.title_label = QLabel("Tools", header_frame)
        self.title_label.setObjectName("ToolboxTitle")
        self.module_label = QLabel("Part", header_frame)
        self.module_label.setObjectName("ToolboxCaption")
        self.module_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.module_label)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setObjectName("ModuleToolboxScroll")

        self.content_widget = QWidget(self.scroll_area)
        self.content_widget.setObjectName("ModuleToolboxContent")
        self.grid_layout = QGridLayout(self.content_widget)
        self.grid_layout.setContentsMargins(2, 3, 2, 3)
        self.grid_layout.setHorizontalSpacing(1)
        self.grid_layout.setVerticalSpacing(4)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.content_widget)

        layout.addWidget(header_frame)
        layout.addWidget(self.scroll_area, 1)

    def set_module(self, module_name: str, button_specs: Sequence[ToolboxButtonSpec]) -> None:
        """按当前模块重建工具按钮。"""

        self._current_module = module_name
        short_name = module_name if len(module_name) <= 4 else f"{module_name[:3]}…"
        self.module_label.setText(short_name)
        self.module_label.setToolTip(module_name)
        self._clear_buttons()

        for index, spec in enumerate(button_specs):
            button = self._build_button(spec)
            self.grid_layout.addWidget(button, index, 0)
            self._buttons_by_key[spec.key] = button
            self._buttons_by_action[spec.action] = button
            self._button_group.addButton(button)

        if button_specs:
            first_button = self._buttons_by_key[button_specs[0].key]
            first_button.setChecked(True)

    def set_active_action(self, action: QAction | None) -> None:
        """同步当前高亮的工具按钮。"""

        if action is None:
            for button in self._buttons_by_action.values():
                button.setChecked(False)
            return

        button = self._buttons_by_action.get(action)
        if button is not None:
            button.setChecked(True)

    def _clear_buttons(self) -> None:
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            self._button_group.removeButton(widget)
            widget.deleteLater()
        self._buttons_by_key.clear()
        self._buttons_by_action.clear()

    def _build_button(self, spec: ToolboxButtonSpec) -> QToolButton:
        button = QToolButton(self.content_widget)
        button.setObjectName("ModuleToolButton")
        button.setText(self._format_button_label(spec.label))
        button.setIcon(spec.icon)
        button.setToolTip(spec.tooltip)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(16, 16))
        button.setMinimumHeight(44)
        button.setMaximumHeight(48)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(spec.action.trigger)
        spec.action.changed.connect(lambda action=spec.action: self._sync_action_state(action))
        self._sync_action_state(spec.action, button)
        return button

    def _format_button_label(self, label: str) -> str:
        """将窄栏中较长的按钮文字整理成更稳定的显示形式。"""

        normalized_label = str(label).strip()
        if "\n" in normalized_label or " " not in normalized_label:
            return normalized_label
        head, tail = normalized_label.rsplit(" ", 1)
        return f"{head}\n{tail}"

    def _sync_action_state(self, action: QAction, button: QToolButton | None = None) -> None:
        target_button = button or self._buttons_by_action.get(action)
        if target_button is None:
            return
        target_button.setEnabled(action.isEnabled())
        target_button.setToolTip(action.toolTip() or action.text())
