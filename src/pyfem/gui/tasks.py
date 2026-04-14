"""GUI 后台任务模型。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal, Slot


class GuiTaskWorker(QObject):
    """定义运行在后台线程中的最小 worker。"""

    started = Signal(str)
    log_message = Signal(str)
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    finished = Signal(str)

    def __init__(self, task_name: str, workload: Callable[[Callable[[str], None]], Any]) -> None:
        super().__init__()
        self._task_name = task_name
        self._workload = workload

    @Slot()
    def run(self) -> None:
        """在后台线程中执行实际任务。"""

        self.started.emit(self._task_name)
        try:
            result = self._workload(self.log_message.emit)
        except Exception as error:
            message = str(error).strip() or f"{type(error).__name__}"
            self.failed.emit(self._task_name, message)
        else:
            self.succeeded.emit(self._task_name, result)
        finally:
            self.finished.emit(self._task_name)


@dataclass(slots=True)
class GuiTaskHandle:
    """描述一个活动中的 GUI 后台任务。"""

    task_name: str
    thread: QThread
    worker: GuiTaskWorker
    on_success: Callable[[Any], None]
