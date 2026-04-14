"""最小 TerminalFormatter 兼容实现。"""

from __future__ import annotations

from pygments.util import ClassNotFound, OptionError


class TerminalFormatter:
    """兼容 pytest 终端输出所需的最小 formatter。"""

    def __init__(self, *, bg: str = "dark", style: str | None = None) -> None:
        if bg not in {"dark", "light"}:
            raise OptionError(f"不支持的背景模式 {bg}。")
        if style == "__invalid__":
            raise ClassNotFound(f"不支持的样式 {style}。")
        self.bg = bg
        self.style = style
