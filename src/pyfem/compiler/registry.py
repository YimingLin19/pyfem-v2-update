"""运行时与 IO 扩展统一注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pyfem.compiler.dof_layout import DofLayout, DofLayoutRegistry
from pyfem.compiler.requests import (
    ConstraintBuildRequest,
    ElementBuildRequest,
    InteractionBuildRequest,
    MaterialBuildRequest,
    ProcedureBuildRequest,
    SectionBuildRequest,
)
from pyfem.foundation.errors import RegistryError
from pyfem.foundation.version import CORE_VERSION
from pyfem.kernel.constraints import ConstraintRuntime
from pyfem.kernel.elements import ElementRuntime
from pyfem.kernel.interactions import InteractionRuntime
from pyfem.kernel.materials import MaterialRuntime
from pyfem.kernel.sections import SectionRuntime
from pyfem.mesh import ElementRecord
from pyfem.plugins.manifest import PluginManifest
from pyfem.procedures.base import ProcedureRuntime

ExtensionFactory = Callable[..., object]


class MaterialRuntimeProvider(ABC):
    """定义材料运行时提供者接口。"""

    @abstractmethod
    def build(self, request: MaterialBuildRequest) -> MaterialRuntime:
        """根据材料定义构建材料运行时对象。"""


class SectionRuntimeProvider(ABC):
    """定义截面运行时提供者接口。"""

    @abstractmethod
    def build(self, request: SectionBuildRequest) -> SectionRuntime:
        """根据截面定义构建截面运行时对象。"""


class ElementRuntimeProvider(ABC):
    """定义单元运行时提供者接口。"""

    def describe_dof_names(
        self,
        element: ElementRecord,
        section_runtime: SectionRuntime | None,
        material_runtime: MaterialRuntime | None,
    ) -> tuple[str, ...]:
        """返回兼容旧接口的节点自由度名称序列。"""

        return ()

    @abstractmethod
    def build(self, request: ElementBuildRequest) -> ElementRuntime:
        """根据单元定义构建单元运行时对象。"""


class ConstraintRuntimeProvider(ABC):
    """定义约束运行时提供者接口。"""

    @abstractmethod
    def build(self, request: ConstraintBuildRequest) -> ConstraintRuntime:
        """根据约束定义构建约束运行时对象。"""


class InteractionRuntimeProvider(ABC):
    """定义相互作用运行时提供者接口。"""

    @abstractmethod
    def build(self, request: InteractionBuildRequest) -> InteractionRuntime:
        """根据相互作用定义构建相互作用运行时对象。"""


class ProcedureRuntimeProvider(ABC):
    """定义分析程序运行时提供者接口。"""

    @abstractmethod
    def build(self, request: ProcedureBuildRequest) -> ProcedureRuntime:
        """根据分析步骤定义构建分析程序运行时对象。"""


class RuntimeRegistry:
    """统一管理运行时 provider、IO 扩展与插件 manifest。"""

    def __init__(self) -> None:
        """初始化空的统一注册表并加载内置扩展。"""

        self._material_providers: dict[str, MaterialRuntimeProvider] = {}
        self._section_providers: dict[str, SectionRuntimeProvider] = {}
        self._element_providers: dict[str, ElementRuntimeProvider] = {}
        self._constraint_providers: dict[str, ConstraintRuntimeProvider] = {}
        self._interaction_providers: dict[str, InteractionRuntimeProvider] = {}
        self._procedure_providers: dict[str, ProcedureRuntimeProvider] = {}
        self._importers: dict[str, ExtensionFactory] = {}
        self._results_writers: dict[str, ExtensionFactory] = {}
        self._results_readers: dict[str, ExtensionFactory] = {}
        self._exporters: dict[str, ExtensionFactory] = {}
        self._plugin_manifests: dict[str, PluginManifest] = {}
        self._core_version = CORE_VERSION
        self._dof_layouts = DofLayoutRegistry()

        from pyfem.compiler.builtin_registry import register_builtin_extensions

        register_builtin_extensions(self)

    def register_material(self, material_type: str, provider: MaterialRuntimeProvider) -> None:
        """注册材料运行时提供者。"""

        self._material_providers[material_type] = provider

    def register_section(self, section_type: str, provider: SectionRuntimeProvider) -> None:
        """注册截面运行时提供者。"""

        self._section_providers[section_type] = provider

    def register_element(self, type_key: str, provider: ElementRuntimeProvider) -> None:
        """注册单元运行时提供者。"""

        self._element_providers[type_key] = provider

    def register_constraint(self, constraint_type: str, provider: ConstraintRuntimeProvider) -> None:
        """注册约束运行时提供者。"""

        self._constraint_providers[constraint_type] = provider

    def register_interaction(self, interaction_type: str, provider: InteractionRuntimeProvider) -> None:
        """注册相互作用运行时提供者。"""

        self._interaction_providers[interaction_type] = provider

    def register_procedure(self, procedure_type: str, provider: ProcedureRuntimeProvider) -> None:
        """注册分析程序运行时提供者。"""

        self._procedure_providers[procedure_type] = provider

    def register_importer(self, format_key: str, factory: ExtensionFactory) -> None:
        """注册模型 importer 工厂。"""

        self._register_factory(self._importers, "模型导入器", format_key, factory)

    def register_results_writer(self, backend_key: str, factory: ExtensionFactory) -> None:
        """注册结果 writer 工厂。"""

        self._register_factory(self._results_writers, "结果 writer", backend_key, factory)

    def register_results_reader(self, backend_key: str, factory: ExtensionFactory) -> None:
        """注册结果 reader 工厂。"""

        self._register_factory(self._results_readers, "结果 reader", backend_key, factory)

    def register_exporter(self, format_key: str, factory: ExtensionFactory) -> None:
        """注册结果 exporter 工厂。"""

        self._register_factory(self._exporters, "结果 exporter", format_key, factory)

    def register_plugin_manifest(self, manifest: PluginManifest) -> None:
        """注册插件 manifest 元数据。"""

        if manifest.name in self._plugin_manifests:
            raise RegistryError(f"插件 manifest {manifest.name} 已存在，禁止重复注册。")
        self._plugin_manifests[manifest.name] = manifest

    def register_dof_layout(self, type_key: str, node_dof_names: tuple[str, ...]) -> None:
        """注册指定单元类型的自由度布局。"""

        self._dof_layouts.register_type(type_key=type_key, node_dof_names=node_dof_names)

    def get_dof_layout(self, type_key: str) -> DofLayout:
        """获取指定单元类型的自由度布局。"""

        return self._dof_layouts.get_layout(type_key)

    @property
    def core_version(self) -> str:
        """返回当前平台注册表声明的核心版本。"""

        return self._core_version

    def find_material_provider(self, material_type: str) -> MaterialRuntimeProvider | None:
        """查找指定类型的材料运行时提供者。"""

        return self._material_providers.get(material_type)

    def find_section_provider(self, section_type: str) -> SectionRuntimeProvider | None:
        """查找指定类型的截面运行时提供者。"""

        return self._section_providers.get(section_type)

    def find_element_provider(self, type_key: str) -> ElementRuntimeProvider | None:
        """查找指定类型的单元运行时提供者。"""

        return self._element_providers.get(type_key)

    def find_constraint_provider(self, constraint_type: str) -> ConstraintRuntimeProvider | None:
        """查找指定类型的约束运行时提供者。"""

        return self._constraint_providers.get(constraint_type)

    def find_interaction_provider(self, interaction_type: str) -> InteractionRuntimeProvider | None:
        """查找指定类型的相互作用运行时提供者。"""

        return self._interaction_providers.get(interaction_type)

    def find_procedure_provider(self, procedure_type: str) -> ProcedureRuntimeProvider | None:
        """查找指定类型的分析程序运行时提供者。"""

        return self._procedure_providers.get(procedure_type)

    def find_importer_factory(self, format_key: str) -> ExtensionFactory | None:
        """查找指定格式的模型 importer 工厂。"""

        return self._importers.get(format_key)

    def find_results_writer_factory(self, backend_key: str) -> ExtensionFactory | None:
        """查找指定后端的结果 writer 工厂。"""

        return self._results_writers.get(backend_key)

    def find_results_reader_factory(self, backend_key: str) -> ExtensionFactory | None:
        """查找指定后端的结果 reader 工厂。"""

        return self._results_readers.get(backend_key)

    def find_exporter_factory(self, format_key: str) -> ExtensionFactory | None:
        """查找指定格式的结果 exporter 工厂。"""

        return self._exporters.get(format_key)

    def find_plugin_manifest(self, plugin_name: str) -> PluginManifest | None:
        """查找指定插件 manifest。"""

        return self._plugin_manifests.get(plugin_name)

    def get_material_provider(self, material_type: str) -> MaterialRuntimeProvider:
        """获取指定类型的材料运行时提供者。"""

        provider = self.find_material_provider(material_type)
        if provider is None:
            raise RegistryError(f"未注册材料类型 {material_type} 的运行时提供者。")
        return provider

    def get_section_provider(self, section_type: str) -> SectionRuntimeProvider:
        """获取指定类型的截面运行时提供者。"""

        provider = self.find_section_provider(section_type)
        if provider is None:
            raise RegistryError(f"未注册截面类型 {section_type} 的运行时提供者。")
        return provider

    def get_element_provider(self, type_key: str) -> ElementRuntimeProvider:
        """获取指定类型的单元运行时提供者。"""

        provider = self.find_element_provider(type_key)
        if provider is None:
            raise RegistryError(f"未注册单元类型 {type_key} 的运行时提供者。")
        return provider

    def get_constraint_provider(self, constraint_type: str) -> ConstraintRuntimeProvider:
        """获取指定类型的约束运行时提供者。"""

        provider = self.find_constraint_provider(constraint_type)
        if provider is None:
            raise RegistryError(f"未注册约束类型 {constraint_type} 的运行时提供者。")
        return provider

    def get_interaction_provider(self, interaction_type: str) -> InteractionRuntimeProvider:
        """获取指定类型的相互作用运行时提供者。"""

        provider = self.find_interaction_provider(interaction_type)
        if provider is None:
            raise RegistryError(f"未注册相互作用类型 {interaction_type} 的运行时提供者。")
        return provider

    def get_procedure_provider(self, procedure_type: str) -> ProcedureRuntimeProvider:
        """获取指定类型的分析程序运行时提供者。"""

        provider = self.find_procedure_provider(procedure_type)
        if provider is None:
            raise RegistryError(f"未注册分析程序类型 {procedure_type} 的运行时提供者。")
        return provider

    def get_importer_factory(self, format_key: str) -> ExtensionFactory:
        """获取指定格式的模型 importer 工厂。"""

        return self._get_factory(self._importers, "模型导入器", format_key)

    def get_results_writer_factory(self, backend_key: str) -> ExtensionFactory:
        """获取指定后端的结果 writer 工厂。"""

        return self._get_factory(self._results_writers, "结果 writer", backend_key)

    def get_results_reader_factory(self, backend_key: str) -> ExtensionFactory:
        """获取指定后端的结果 reader 工厂。"""

        return self._get_factory(self._results_readers, "结果 reader", backend_key)

    def get_exporter_factory(self, format_key: str) -> ExtensionFactory:
        """获取指定格式的结果 exporter 工厂。"""

        return self._get_factory(self._exporters, "结果 exporter", format_key)

    def get_plugin_manifest(self, plugin_name: str) -> PluginManifest:
        """获取指定插件 manifest。"""

        manifest = self.find_plugin_manifest(plugin_name)
        if manifest is None:
            raise RegistryError(f"未注册插件 manifest {plugin_name}。")
        return manifest

    def create_importer(self, format_key: str, *args: Any, **kwargs: Any) -> Any:
        """创建指定格式的模型 importer。"""

        return self.get_importer_factory(format_key)(*args, **kwargs)

    def create_results_writer(self, backend_key: str, *args: Any, **kwargs: Any) -> Any:
        """创建指定后端的结果 writer。"""

        return self.get_results_writer_factory(backend_key)(*args, **kwargs)

    def create_results_reader(self, backend_key: str, *args: Any, **kwargs: Any) -> Any:
        """创建指定后端的结果 reader。"""

        return self.get_results_reader_factory(backend_key)(*args, **kwargs)

    def create_exporter(self, format_key: str, *args: Any, **kwargs: Any) -> Any:
        """创建指定格式的结果 exporter。"""

        return self.get_exporter_factory(format_key)(*args, **kwargs)

    def _register_factory(
        self,
        registry: dict[str, ExtensionFactory],
        category_name: str,
        key: str,
        factory: ExtensionFactory,
    ) -> None:
        """向指定扩展点类别注册工厂并执行重复校验。"""

        if key in registry:
            raise RegistryError(f"{category_name} {key} 已存在，禁止重复注册。")
        registry[key] = factory

    def _get_factory(self, registry: dict[str, ExtensionFactory], category_name: str, key: str) -> ExtensionFactory:
        """从指定扩展点类别获取工厂并在缺失时 fail-fast。"""

        factory = registry.get(key)
        if factory is None:
            raise RegistryError(f"未注册{category_name} {key}。")
        return factory
