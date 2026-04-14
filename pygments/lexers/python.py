"""最小 PythonLexer 兼容实现。"""

from __future__ import annotations

from pygments.lexer import Lexer


class PythonLexer(Lexer):
    """为 pytest 提供的占位 PythonLexer。"""
