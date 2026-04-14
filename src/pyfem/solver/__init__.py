"""求解器层公共入口。"""

from pyfem.solver.assembler import Assembler, ReducedSystem
from pyfem.solver.backend import LinearAlgebraBackend, SciPyBackend
from pyfem.solver.problem import DiscreteProblem
from pyfem.solver.state import GlobalKinematicState, ProblemState, RuntimeState, StateManager

__all__ = [
    "Assembler",
    "DiscreteProblem",
    "GlobalKinematicState",
    "LinearAlgebraBackend",
    "ProblemState",
    "ReducedSystem",
    "RuntimeState",
    "SciPyBackend",
    "StateManager",
]
