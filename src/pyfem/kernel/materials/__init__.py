"""材料运行时接口。"""

from pyfem.kernel.materials.base import MaterialResponse, MaterialRuntime, MaterialUpdateResult
from pyfem.kernel.materials.elastic_isotropic import ElasticIsotropicRuntime
from pyfem.kernel.materials.j2_plasticity import J2PlasticityRuntime

__all__ = [
    "ElasticIsotropicRuntime",
    "J2PlasticityRuntime",
    "MaterialResponse",
    "MaterialRuntime",
    "MaterialUpdateResult",
]
