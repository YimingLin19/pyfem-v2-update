"""分析程序运行时接口。"""

from pyfem.procedures.base import ProcedureReport, ProcedureRuntime

__all__ = [
    "ImplicitDynamicProcedure",
    "ModalProcedure",
    "NewmarkParameters",
    "ProcedureReport",
    "ProcedureRuntime",
    "StaticNonlinearProcedure",
    "StaticLinearProcedure",
    "StepProcedureRuntime",
]


def __getattr__(name: str):
    if name == "StaticLinearProcedure":
        from pyfem.procedures.static_linear import StaticLinearProcedure

        return StaticLinearProcedure
    if name == "ModalProcedure":
        from pyfem.procedures.modal import ModalProcedure

        return ModalProcedure
    if name == "StaticNonlinearProcedure":
        from pyfem.procedures.static_nonlinear import StaticNonlinearProcedure

        return StaticNonlinearProcedure
    if name == "ImplicitDynamicProcedure":
        from pyfem.procedures.implicit_dynamic import ImplicitDynamicProcedure

        return ImplicitDynamicProcedure
    if name == "NewmarkParameters":
        from pyfem.procedures.implicit_dynamic import NewmarkParameters

        return NewmarkParameters
    if name == "StepProcedureRuntime":
        from pyfem.procedures.support import StepProcedureRuntime

        return StepProcedureRuntime
    raise AttributeError(f"module 'pyfem.procedures' has no attribute {name!r}")
