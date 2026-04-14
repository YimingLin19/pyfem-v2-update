"""最小 DiffLexer 兼容实现。"""

from __future__ import annotations

from pygments.lexer import Lexer


class DiffLexer(Lexer):
    """为 pytest 提供的占位 DiffLexer。"""
