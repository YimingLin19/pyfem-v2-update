from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class MessageConsolePanel(QFrame):
    """提供消息区与 Python Console 页签。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("MessageConsolePane")
        self.setMinimumHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_frame = QFrame(self)
        header_frame.setObjectName("MessageConsoleHeader")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(6)

        self.title_label = QLabel("Messages", header_frame)
        self.title_label.setObjectName("ConsoleTitle")
        self.summary_label = QLabel("运行日志、结果反馈与控制台输出显示在这里。", header_frame)
        self.summary_label.setObjectName("ConsoleCaption")
        self.clear_button = QPushButton("Clear", header_frame)
        self.clear_button.setObjectName("SecondaryButton")
        self.clear_button.setMinimumHeight(22)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.summary_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.clear_button)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setObjectName("MessageConsoleTabs")
        self.tab_widget.setDocumentMode(True)

        messages_page = QWidget(self.tab_widget)
        messages_layout = QVBoxLayout(messages_page)
        messages_layout.setContentsMargins(6, 6, 6, 6)
        messages_layout.setSpacing(4)
        self.messages_edit = QPlainTextEdit(messages_page)
        self.messages_edit.setObjectName("MessageConsole")
        self.messages_edit.setReadOnly(True)
        self.messages_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.messages_edit.setPlaceholderText("作业日志、结果状态和占位反馈会显示在这里。")
        messages_layout.addWidget(self.messages_edit, 1)

        console_page = QWidget(self.tab_widget)
        console_layout = QVBoxLayout(console_page)
        console_layout.setContentsMargins(10, 8, 10, 10)
        console_layout.setSpacing(6)
        console_title = QLabel("Python Console", console_page)
        console_title.setObjectName("SectionTitle")
        console_hint = QLabel("Python Console 当前为结构占位，后续在此接入正式脚本控制台。", console_page)
        console_hint.setObjectName("EmptyCaption")
        console_hint.setWordWrap(True)
        console_hint.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.console_placeholder = QPlainTextEdit(console_page)
        self.console_placeholder.setObjectName("ConsolePlaceholder")
        self.console_placeholder.setReadOnly(True)
        self.console_placeholder.setPlainText(">>> Python Console 占位\n>>> 后续在此接入正式脚本控制台。")
        console_layout.addWidget(console_title)
        console_layout.addWidget(console_hint)
        console_layout.addWidget(self.console_placeholder, 1)

        self.tab_widget.addTab(messages_page, "Messages")
        self.tab_widget.addTab(console_page, "Python Console")

        layout.addWidget(header_frame)
        layout.addWidget(self.tab_widget, 1)

    def show_python_console(self) -> None:
        """切换到 Python Console 页签。"""

        self.tab_widget.setCurrentIndex(1)

    def show_messages(self) -> None:
        """切换到消息页签。"""

        self.tab_widget.setCurrentIndex(0)
