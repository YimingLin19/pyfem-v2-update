"""最小 pygments.util 兼容定义。"""

from __future__ import annotations


class ClassNotFound(Exception):
    """兼容 pytest 主题错误分支的异常类型。"""


class OptionError(Exception):
    """兼容 pytest 配置错误分支的异常类型。"""
