"""pyFEM v2 核心包。"""

from pyfem.compiler import CompiledModel, Compiler, RuntimeRegistry
from pyfem.foundation import CORE_VERSION
from pyfem.kernel import DofManager
from pyfem.modeldb import ModelDB

__version__ = CORE_VERSION

__all__ = ["CompiledModel", "Compiler", "CORE_VERSION", "DofManager", "ModelDB", "RuntimeRegistry", "__version__"]
