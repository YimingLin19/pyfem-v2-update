"""基础类型与异常定义。"""

from pyfem.foundation.errors import CompilationError, ModelValidationError, PyFEMError, RegistryError
from pyfem.foundation.types import DofLocation, ElementLocation, Matrix, NodeLocation, StateMap, Vector
from pyfem.foundation.version import CORE_VERSION

__all__ = [
    "CompilationError",
    "CORE_VERSION",
    "DofLocation",
    "ElementLocation",
    "Matrix",
    "ModelValidationError",
    "NodeLocation",
    "PyFEMError",
    "RegistryError",
    "StateMap",
    "Vector",
]
