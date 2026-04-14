"""为本仓库 pytest 门禁提供的最小 pygments 兼容层。"""

from __future__ import annotations

from pygments import util


def highlight(source: str, lexer: object, formatter: object) -> str:
    """返回未经高亮处理的源码文本。"""

    del lexer
    del formatter
    return source


__all__ = ["highlight", "util"]
