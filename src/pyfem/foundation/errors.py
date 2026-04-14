"""项目统一异常定义。"""


class PyFEMError(Exception):
    """定义项目级基础异常。"""


class ModelValidationError(PyFEMError):
    """表示模型定义校验失败。"""


class RegistryError(PyFEMError):
    """表示运行时提供者注册表配置错误。"""


class CompilationError(PyFEMError):
    """表示从模型到运行时的编译过程失败。"""


class SolverError(PyFEMError):
    """表示装配、求解或分析程序执行失败。"""
