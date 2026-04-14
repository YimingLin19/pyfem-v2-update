"""PySide6 GUI 应用入口。"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtWidgets import QApplication

from pyfem.gui.main_window import PyFEMMainWindow


def create_gui_application(argv: Sequence[str] | None = None) -> QApplication:
    """创建或复用当前 Qt 应用实例。"""

    application = QApplication.instance()
    if application is not None:
        return application
    resolved_argv = list(sys.argv if argv is None else argv)
    return QApplication(resolved_argv)


def main(argv: Sequence[str] | None = None) -> int:
    """启动 pyFEM Studio GUI。"""

    application = create_gui_application(argv)
    window = PyFEMMainWindow()
    window.showMaximized()
    return application.exec()
