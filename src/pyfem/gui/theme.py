from __future__ import annotations

from dataclasses import dataclass

APP_DISPLAY_NAME = "pyFEM Studio"
APP_WINDOW_TITLE = "pyFEM Studio | 结构分析工作台"
APP_SUBTITLE = "商业级结构有限元平台 GUI"


@dataclass(slots=True, frozen=True)
class TaskStatePresentation:
    """描述 GUI 任务状态的统一视觉表达。"""

    label: str
    foreground_color: str
    background_color: str
    border_color: str


def resolve_task_state_presentation(task_state: str) -> TaskStatePresentation:
    """根据任务状态返回统一的视觉配置。"""

    mapping = {
        "idle": TaskStatePresentation("空闲", "#284765", "#edf4fb", "#c4d8ea"),
        "running": TaskStatePresentation("运行中", "#7a4d0b", "#fff4d8", "#ead39a"),
        "success": TaskStatePresentation("完成", "#205e3b", "#e8f5eb", "#bad8c1"),
        "failed": TaskStatePresentation("失败", "#8b2230", "#fcebed", "#efbcc4"),
    }
    return mapping.get(task_state, mapping["idle"])


def build_pill_stylesheet(
    *,
    foreground_color: str,
    background_color: str,
    border_color: str,
    font_size: int = 11,
    font_weight: int = 600,
    padding: str = "3px 8px",
) -> str:
    """构建统一的轻量微标样式。"""

    return (
        "border-radius: 10px;"
        f"padding: {padding};"
        f"border: 1px solid {border_color};"
        f"background-color: {background_color};"
        f"color: {foreground_color};"
        f"font-size: {max(1, round(font_size * 0.75))}pt;"
        f"font-weight: {font_weight};"
    )


def build_main_window_stylesheet() -> str:
    """返回经典 CAE 工作台风格的主窗口样式表。"""

    return """
QMainWindow {
    background: #d9dee3;
    color: #182532;
}
QWidget {
    color: #182532;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 9pt;
}
QMenuBar {
    background: #e3e7eb;
    border-bottom: 1px solid #b5bec7;
    padding: 1px 6px;
}
QMenuBar::item {
    padding: 3px 8px;
    background: transparent;
}
QMenuBar::item:selected {
    background: #d4dbe2;
}
QMenu {
    background: #f4f6f8;
    border: 1px solid #b5bec7;
    padding: 4px;
}
QMenu::item {
    padding: 5px 24px 5px 10px;
}
QMenu::item:selected {
    background: #dbe2e8;
}
QToolBar {
    background: #e6eaee;
    border-bottom: 1px solid #bcc5cd;
    spacing: 1px;
    padding: 0px 4px;
}
QToolBar#ContextToolBar {
    background: #eceff2;
    min-height: 26px;
}
QToolBar#FileToolBar,
QToolBar#RunToolBar,
QToolBar#ViewToolBar,
QToolBar#SelectionToolBar,
QToolBar#ResultsToolBar,
QToolBar#MainToolBar {
    min-height: 28px;
}
QToolBar::separator {
    width: 1px;
    background: #c3ccd4;
    margin: 2px 4px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 2px 4px;
    min-height: 20px;
}
QToolButton:hover {
    background: #dbe2e8;
    border-color: #b7c1ca;
}
QToolButton:pressed,
QToolButton:checked {
    background: #ccd6df;
    border-color: #9eabb8;
}
QToolBar QComboBox,
QToolBar QLineEdit {
    min-height: 22px;
    padding: 1px 6px;
}
QLabel#ContextCaption,
QLabel#ToolboxCaption,
QLabel#BrowserMeta,
QLabel#ConsoleCaption,
QLabel#ViewportMeta {
    color: #566474;
    font-size: 8pt;
}
QLabel#ToolbarValue,
QLabel#ContextValue {
    color: #24384b;
    font-weight: 600;
}
QLabel#BrowserTitle,
QLabel#ToolboxTitle,
QLabel#ViewportStripTitle,
QLabel#ConsoleTitle,
QLabel#PromptModuleLabel {
    color: #182532;
    font-size: 9pt;
    font-weight: 700;
}
QLabel#SectionTitle {
    color: #16222f;
    font-size: 10pt;
    font-weight: 700;
}
QLabel#SectionCaption,
QLabel#EmptyCaption,
QLabel#ToolbarMeta,
QLabel#SoftText {
    color: #4e5e6f;
}
QLabel#EmptyTitle {
    color: #16222f;
    font-size: 13pt;
    font-weight: 700;
}
QFrame#NavigationDock,
QFrame#ModuleToolboxPane,
QWidget#ViewportPane,
QFrame#MessageConsolePane,
QFrame#BrowserHeaderCard,
QFrame#PanelCard,
QWidget#WorkspaceCard,
QFrame#OptionalDockContent {
    background: #eef1f4;
    border: 1px solid #bcc5ce;
    border-radius: 0px;
}
QFrame#PaneHeader,
QFrame#ToolboxHeader,
QFrame#MessageConsoleHeader,
QFrame#ViewportContextStrip,
QFrame#BrowserHeaderCard,
QFrame#PanelCard {
    background: #e5eaee;
    border: 1px solid #bcc5ce;
    border-radius: 0px;
}
QWidget#ViewportCanvasHost,
QFrame#ViewportCanvas {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #d8e0e8,
        stop:1 #c2ccd7);
    border: 1px solid #aeb8c2;
    border-top: none;
}
QFrame#NavigationDetailsPaneFrame,
QFrame#EmptyStateCard {
    background: #f5f7f9;
    border: 1px solid #c3ccd4;
}
QScrollArea#ModuleToolboxScroll,
QWidget#ModuleToolboxContent {
    background: #edf1f4;
}
QToolButton#ModuleToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 1px 1px;
    min-height: 38px;
    font-size: 8pt;
    font-weight: 600;
}
QToolButton#ModuleToolButton:hover {
    background: #e2e8ee;
    border-color: #bcc5ce;
}
QToolButton#ModuleToolButton:checked {
    background: #d7e0e8;
    border-color: #93a6b8;
}
QToolButton#WorkspaceEntryButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 1px 4px;
    min-height: 18px;
    color: #5a6978;
    font-size: 8pt;
}
QToolButton#WorkspaceEntryButton:hover {
    background: #e2e8ee;
    border-color: #bcc5ce;
}
QPushButton {
    background: #d7dde4;
    color: #182532;
    border: 1px solid #b4bec8;
    border-radius: 2px;
    padding: 4px 10px;
    min-height: 24px;
    font-weight: 600;
}
QPushButton:hover {
    background: #e0e6eb;
}
QPushButton:pressed {
    background: #cdd6de;
}
QPushButton:disabled {
    background: #eceff2;
    color: #83909c;
    border-color: #d0d7de;
}
QPushButton#SecondaryButton {
    background: #f5f7f9;
    color: #24415f;
    border: 1px solid #bcc5ce;
}
QPushButton#SecondaryButton:hover {
    background: #e8edf2;
}
QLineEdit,
QComboBox,
QPlainTextEdit,
QTableWidget,
QTextBrowser {
    background: #ffffff;
    border: 1px solid #b8c2cb;
    border-radius: 2px;
    padding: 4px 6px;
    selection-background-color: #d8e1e8;
    selection-color: #182532;
}
QComboBox::drop-down {
    width: 18px;
    border: none;
}
QComboBox::down-arrow {
    width: 8px;
    height: 8px;
}
QTabWidget::pane {
    border: 1px solid #c0c8d0;
    background: #f7f9fb;
    border-radius: 0px;
}
QTabBar::tab {
    background: #dde3e8;
    color: #425364;
    padding: 4px 8px;
    border: 1px solid #c0c8d0;
    border-bottom: none;
    margin-right: 1px;
}
QTabBar::tab:selected {
    background: #f7f9fb;
    color: #182532;
}
QTreeWidget,
QTableWidget {
    background: #fbfcfd;
    border: 1px solid #bcc5ce;
    alternate-background-color: #f5f7f9;
    gridline-color: #d7dee5;
}
QTreeWidget {
    show-decoration-selected: 1;
}
QTreeWidget::item,
QTableWidget::item {
    padding: 2px 4px;
}
QTreeWidget::item:hover,
QTableWidget::item:hover {
    background: #eef3f7;
}
QTreeWidget::item:selected,
QTableWidget::item:selected {
    background: #dbe4eb;
    color: #182532;
}
QHeaderView::section {
    background: #e8edf1;
    color: #405160;
    border: none;
    border-right: 1px solid #c0c8d0;
    border-bottom: 1px solid #c0c8d0;
    padding: 4px 6px;
    font-size: 8pt;
    font-weight: 600;
}
QPlainTextEdit#MessageConsole,
QPlainTextEdit#ConsolePlaceholder,
QPlainTextEdit#NavigationDetailsPane {
    background: #ffffff;
    border: 1px solid #bcc5ce;
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
    font-size: 9pt;
}
QGroupBox {
    background: #f5f7f9;
    border: 1px solid #c3ccd4;
    margin-top: 16px;
    padding: 16px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: 0px;
    padding: 0 6px 1px 6px;
    background: #f5f7f9;
    color: #344557;
}
QStatusBar {
    background: #e1e6ea;
    border-top: 1px solid #bcc5ce;
    min-height: 32px;
    padding: 3px 6px;
}
QStatusBar::item {
    border: none;
}
QStatusBar QLabel {
    min-height: 20px;
    padding: 0px;
}
QSplitter::handle {
    background: #ccd4db;
}
QSplitter::handle:hover {
    background: #b7c2cc;
}
"""


