"""线性代数 backend 抽象与 SciPy 实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy
import scipy.linalg

from pyfem.foundation.errors import SolverError


class LinearAlgebraBackend(ABC):
    """定义线性代数 backend 的正式接口。"""

    @abstractmethod
    def solve_linear_system(self, matrix: numpy.ndarray, rhs: numpy.ndarray) -> numpy.ndarray:
        """求解线性方程组。"""

    @abstractmethod
    def solve_generalized_eigenproblem(
        self,
        stiffness: numpy.ndarray,
        mass: numpy.ndarray,
        num_modes: int,
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        """求解广义特征值问题。"""


class SciPyBackend(LinearAlgebraBackend):
    """提供基于 SciPy 的密集线性代数实现。"""

    def solve_linear_system(self, matrix: numpy.ndarray, rhs: numpy.ndarray) -> numpy.ndarray:
        """调用 SciPy 求解线性方程组。"""

        dense_matrix = self._as_dense_matrix(matrix)
        dense_rhs = self._as_dense_vector(rhs)
        if dense_matrix.shape[0] != dense_rhs.shape[0]:
            raise SolverError("线性方程组矩阵与右端向量维度不一致。")
        return numpy.asarray(scipy.linalg.solve(dense_matrix, dense_rhs, assume_a="gen"), dtype=float)

    def solve_generalized_eigenproblem(
        self,
        stiffness: numpy.ndarray,
        mass: numpy.ndarray,
        num_modes: int,
    ) -> tuple[numpy.ndarray, numpy.ndarray]:
        """调用 SciPy 求解广义特征值问题。"""

        dense_stiffness = self._as_dense_matrix(stiffness)
        dense_mass = self._as_dense_matrix(mass)
        if dense_stiffness.shape != dense_mass.shape:
            raise SolverError("广义特征值问题的刚度矩阵与质量矩阵维度不一致。")
        if dense_stiffness.shape[0] == 0:
            raise SolverError("当前系统没有可用于模态分析的自由度。")
        if num_modes <= 0:
            raise SolverError("模态数必须为正整数。")

        eigenvalues, eigenvectors = scipy.linalg.eigh(dense_stiffness, dense_mass)
        positive_mask = numpy.logical_and(numpy.isfinite(eigenvalues), eigenvalues > 1.0e-12)
        filtered_values = numpy.asarray(eigenvalues[positive_mask], dtype=float)
        filtered_vectors = numpy.asarray(eigenvectors[:, positive_mask], dtype=float)
        if filtered_values.size == 0:
            raise SolverError("未得到正特征值，无法形成有效模态结果。")

        mode_count = min(num_modes, filtered_values.size)
        return filtered_values[:mode_count], filtered_vectors[:, :mode_count]

    def _as_dense_matrix(self, matrix: numpy.ndarray) -> numpy.ndarray:
        dense_matrix = numpy.asarray(matrix, dtype=float)
        if dense_matrix.ndim != 2 or dense_matrix.shape[0] != dense_matrix.shape[1]:
            raise SolverError("线性代数 backend 仅接受二维方阵。")
        return dense_matrix

    def _as_dense_vector(self, vector: numpy.ndarray) -> numpy.ndarray:
        dense_vector = numpy.asarray(vector, dtype=float)
        if dense_vector.ndim != 1:
            raise SolverError("线性代数 backend 仅接受一维向量。")
        return dense_vector
