"""单元运行时的公共数值工具。"""

from __future__ import annotations

import math

import numpy

from pyfem.foundation.types import Matrix, Vector


def as_matrix(values: numpy.ndarray) -> Matrix:
    """将数组转换为矩阵元组。"""

    return tuple(tuple(float(item) for item in row) for row in values.tolist())


def as_vector(values: numpy.ndarray) -> Vector:
    """将数组转换为向量元组。"""

    return tuple(float(item) for item in values.tolist())


def gauss_points_2() -> tuple[tuple[float, float], ...]:
    """?????? Gauss ????"""

    point = 1.0 / math.sqrt(3.0)
    return ((-point, 1.0), (point, 1.0))


def gauss_points_2x2() -> tuple[tuple[float, float, float], ...]:
    """返回二维 2x2 Gauss 积分点。"""

    point = 1.0 / math.sqrt(3.0)
    return (
        (-point, -point, 1.0),
        (point, -point, 1.0),
        (point, point, 1.0),
        (-point, point, 1.0),
    )


def gauss_points_2x2x2() -> tuple[tuple[float, float, float, float], ...]:
    """返回三维 2x2x2 Gauss 积分点。"""

    point = 1.0 / math.sqrt(3.0)
    return (
        (-point, -point, -point, 1.0),
        (point, -point, -point, 1.0),
        (point, point, -point, 1.0),
        (-point, point, -point, 1.0),
        (-point, -point, point, 1.0),
        (point, -point, point, 1.0),
        (point, point, point, 1.0),
        (-point, point, point, 1.0),
    )
