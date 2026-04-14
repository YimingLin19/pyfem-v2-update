"""插件 manifest 发现、校验与注册外壳。"""

from __future__ import annotations

import importlib
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pyfem.foundation.errors import RegistryError
from pyfem.plugins.manifest import PluginManifest, parse_plugin_manifest

if TYPE_CHECKING:
    from pyfem.compiler import RuntimeRegistry

RegisterPluginFunction = Callable[[object], object | None]


@dataclass(slots=True, frozen=True)
class DiscoveredPluginManifest:
    """描述一次发现到的插件 manifest。"""

    manifest: PluginManifest
    path: Path


@dataclass(slots=True)
class PluginDiscoveryService:
    """封装插件 manifest 的最小发现、校验与注册逻辑。"""

    manifest_filename: str = "plugin.json"

    def discover(self, *search_roots: str | Path) -> tuple[DiscoveredPluginManifest, ...]:
        """在给定目录或文件中发现插件 manifest。"""

        discovered_paths: set[Path] = set()
        for search_root in search_roots:
            resolved_root = Path(search_root)
            if resolved_root.is_file():
                discovered_paths.add(resolved_root)
                continue
            if resolved_root.is_dir():
                discovered_paths.update(path for path in resolved_root.rglob(self.manifest_filename) if path.is_file())
                continue
            raise RegistryError(f"插件发现路径不存在: {resolved_root}")

        return tuple(self.load_manifest(path) for path in sorted(discovered_paths))

    def load_manifest(self, path: str | Path) -> DiscoveredPluginManifest:
        """从文件加载单个插件 manifest。"""

        resolved_path = Path(path)
        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RegistryError(f"插件 manifest 文件 {resolved_path} 不是合法 JSON。") from error
        if not isinstance(payload, dict):
            raise RegistryError(f"插件 manifest 文件 {resolved_path} 的根对象必须为 JSON object。")
        manifest = parse_plugin_manifest(payload)
        return DiscoveredPluginManifest(manifest=manifest, path=resolved_path)

    def register_into_registry(
        self,
        registry: RuntimeRegistry,
        discovered_manifests: tuple[DiscoveredPluginManifest, ...],
    ) -> tuple[PluginManifest, ...]:
        """将发现到的插件 manifest 通过正式注册函数挂到统一 registry。"""

        manifests: list[PluginManifest] = []
        for discovered_manifest in discovered_manifests:
            manifest = discovered_manifest.manifest
            if registry.find_plugin_manifest(manifest.name) is not None:
                raise RegistryError(f"插件 manifest {manifest.name} 已存在，禁止重复注册。")

            manifest.validate_core_version(registry.core_version)
            register_function = self._load_register_function(manifest)
            self._invoke_register_function(register_function, registry=registry, manifest=manifest)
            self._validate_registered_extensions(registry, manifest=manifest)
            registry.register_plugin_manifest(manifest)
            manifests.append(manifest)
        return tuple(manifests)

    def _load_register_function(self, manifest: PluginManifest) -> RegisterPluginFunction:
        """解析并校验插件注册函数。"""

        if manifest.register_entry is None:
            raise RegistryError(f"插件 {manifest.name} 缺少 register_entry，无法执行正式注册。")

        module_name, function_name = manifest.register_entry.split(":", maxsplit=1)
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            raise RegistryError(f"插件 {manifest.name} 的 register_entry={manifest.register_entry} 无法导入。") from error

        try:
            register_function = getattr(module, function_name)
        except AttributeError as error:
            raise RegistryError(f"插件 {manifest.name} 的注册函数 {manifest.register_entry} 不存在。") from error

        if not callable(register_function):
            raise RegistryError(f"插件 {manifest.name} 的注册入口 {manifest.register_entry} 不是可调用对象。")

        self._validate_register_signature(register_function, manifest=manifest)
        return register_function

    def _validate_register_signature(self, register_function: RegisterPluginFunction, *, manifest: PluginManifest) -> None:
        """校验插件注册函数签名。"""

        from pyfem.compiler import RuntimeRegistry

        signature = inspect.signature(register_function)
        parameters = tuple(signature.parameters.values())
        if len(parameters) != 1:
            raise RegistryError(f"插件 {manifest.name} 的注册函数必须只接收一个 RuntimeRegistry 参数。")

        parameter = parameters[0]
        if parameter.kind not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            raise RegistryError(f"插件 {manifest.name} 的注册函数参数必须是普通位置参数。")
        if parameter.default is not inspect.Signature.empty:
            raise RegistryError(f"插件 {manifest.name} 的注册函数参数不能带默认值。")
        if parameter.annotation is inspect.Signature.empty:
            raise RegistryError(f"插件 {manifest.name} 的注册函数参数必须标注 RuntimeRegistry 类型。")
        if parameter.annotation is not RuntimeRegistry:
            annotation_name = (
                parameter.annotation.rsplit(".", maxsplit=1)[-1]
                if isinstance(parameter.annotation, str)
                else getattr(parameter.annotation, "__name__", str(parameter.annotation))
            )
            if annotation_name != "RuntimeRegistry":
                raise RegistryError(f"插件 {manifest.name} 的注册函数参数必须标注 RuntimeRegistry 类型。")

    def _invoke_register_function(
        self,
        register_function: RegisterPluginFunction,
        *,
        registry: RuntimeRegistry,
        manifest: PluginManifest,
    ) -> None:
        """调用插件正式注册函数。"""

        try:
            register_function(registry)
        except RegistryError:
            raise
        except Exception as error:
            raise RegistryError(f"插件 {manifest.name} 的注册函数执行失败。") from error

    def _validate_registered_extensions(self, registry: RuntimeRegistry, *, manifest: PluginManifest) -> None:
        """校验注册函数是否通过正式 registry 注册了 manifest 声明的扩展点。"""

        for extension in manifest.extensions:
            resolved_extension = self._find_registered_extension(registry, extension.extension_type, extension.key)
            if resolved_extension is None:
                raise RegistryError(
                    f"插件 {manifest.name} 的注册函数未通过 RuntimeRegistry 注册扩展点 "
                    f"{extension.extension_type}:{extension.key}。"
                )

    def _find_registered_extension(self, registry: RuntimeRegistry, extension_type: str, key: str):
        """通过统一 registry 查找指定扩展点。"""

        finders = {
            "constraint": registry.find_constraint_provider,
            "element": registry.find_element_provider,
            "exporter": registry.find_exporter_factory,
            "importer": registry.find_importer_factory,
            "interaction": registry.find_interaction_provider,
            "material": registry.find_material_provider,
            "procedure": registry.find_procedure_provider,
            "results_reader": registry.find_results_reader_factory,
            "results_writer": registry.find_results_writer_factory,
            "section": registry.find_section_provider,
        }
        return finders[extension_type](key)
