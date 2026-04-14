"""自由度布局定义。"""

from __future__ import annotations

from dataclasses import dataclass

from pyfem.foundation.errors import RegistryError

UX = "UX"
UY = "UY"
UZ = "UZ"
RX = "RX"
RY = "RY"
RZ = "RZ"


@dataclass(slots=True, frozen=True)
class DofLayout:
    """定义单元类型对应的节点自由度布局。"""

    type_key: str
    node_dof_names: tuple[str, ...]


class DofLayoutRegistry:
    """统一管理单元类型到节点自由度布局的映射。"""

    def __init__(self) -> None:
        """初始化自由度布局注册表并加载默认布局。"""

        self._layouts: dict[str, DofLayout] = {}
        self.register_layout(DofLayout(type_key="C3D8", node_dof_names=(UX, UY, UZ)))
        self.register_layout(DofLayout(type_key="CPS4", node_dof_names=(UX, UY)))
        self.register_layout(DofLayout(type_key="B21", node_dof_names=(UX, UY, RZ)))

    def register_layout(self, layout: DofLayout) -> None:
        """注册一个完整的自由度布局对象。"""

        self._layouts[layout.type_key] = layout

    def register_type(self, type_key: str, node_dof_names: tuple[str, ...]) -> None:
        """用类型名称与自由度序列注册布局。"""

        self.register_layout(DofLayout(type_key=type_key, node_dof_names=node_dof_names))

    def get_layout(self, type_key: str) -> DofLayout:
        """获取指定单元类型的自由度布局。"""

        try:
            return self._layouts[type_key]
        except KeyError as error:
            raise RegistryError(f"未注册单元类型 {type_key} 的自由度布局。") from error

    def has_layout(self, type_key: str) -> bool:
        """判断是否已注册指定单元类型的自由度布局。"""

        return type_key in self._layouts
