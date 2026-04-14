"""相互作用运行时接口。"""

from pyfem.kernel.interactions.base import InteractionRuntime
from pyfem.kernel.interactions.noop import NoOpInteractionRuntime

__all__ = ["InteractionRuntime", "NoOpInteractionRuntime"]
