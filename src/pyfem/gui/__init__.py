"""图形界面接入层公共入口。"""

from __future__ import annotations

from importlib import import_module

_LAZY_EXPORTS = {
    "GuiMeshGeometry": ("pyfem.gui.shell", "GuiMeshGeometry"),
    "GuiModelNavigationSnapshot": ("pyfem.gui.shell", "GuiModelNavigationSnapshot"),
    "GuiModelSummary": ("pyfem.gui.shell", "GuiModelSummary"),
    "GuiResultsEntry": ("pyfem.gui.shell", "GuiResultsEntry"),
    "GuiResultsLoadResult": ("pyfem.gui.shell", "GuiResultsLoadResult"),
    "GuiResultsViewContext": ("pyfem.gui.shell", "GuiResultsViewContext"),
    "GuiRunProcessRequest": ("pyfem.gui.shell", "GuiRunProcessRequest"),
    "GuiShell": ("pyfem.gui.shell", "GuiShell"),
    "GuiShellState": ("pyfem.gui.shell", "GuiShellState"),
    "GuiTaskHandle": ("pyfem.gui.tasks", "GuiTaskHandle"),
    "GuiTaskWorker": ("pyfem.gui.tasks", "GuiTaskWorker"),
    "ResultsBrowser": ("pyfem.gui.results_browser", "ResultsBrowser"),
    "WorkbenchNavigationPanel": ("pyfem.gui.navigation_panel", "WorkbenchNavigationPanel"),
    "PyFEMMainWindow": ("pyfem.gui.main_window", "PyFEMMainWindow"),
    "ResultsViewportHost": ("pyfem.gui.viewport", "ResultsViewportHost"),
    "create_gui_application": ("pyfem.gui.app", "create_gui_application"),
    "main": ("pyfem.gui.app", "main"),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> object:
    """按需加载 GUI 导出，避免包初始化阶段触发重型依赖链。"""

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value
