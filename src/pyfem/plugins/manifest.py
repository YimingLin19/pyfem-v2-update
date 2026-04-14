"""插件 manifest 第一版定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from pyfem.foundation.errors import RegistryError

PLUGIN_MANIFEST_VERSION = "1"
SUPPORTED_EXTENSION_TYPES = frozenset(
    {
        "constraint",
        "element",
        "exporter",
        "importer",
        "interaction",
        "material",
        "procedure",
        "results_reader",
        "results_writer",
        "section",
    }
)


@dataclass(slots=True, frozen=True)
class PluginCompatibility:
    """描述插件与内核版本的最小兼容信息。"""

    min_core_version: str
    max_core_version: str | None = None

    def __post_init__(self) -> None:
        if not self.min_core_version:
            raise RegistryError("插件 manifest 缺少 min_core_version。")
        _parse_version_tokens(self.min_core_version, allow_wildcard=False)
        if self.max_core_version is not None:
            _parse_version_tokens(self.max_core_version, allow_wildcard=True)

    def is_compatible_with_core(self, core_version: str) -> bool:
        """判断当前插件是否兼容指定核心版本。"""

        core_tokens = _parse_version_tokens(core_version, allow_wildcard=False)
        min_tokens = _parse_version_tokens(self.min_core_version, allow_wildcard=False)
        if _compare_version_tokens(core_tokens, min_tokens) < 0:
            return False
        if self.max_core_version is None:
            return True
        max_tokens = _parse_version_tokens(self.max_core_version, allow_wildcard=True)
        return _satisfies_upper_bound(core_tokens, max_tokens)

    def validate_core_version(self, core_version: str, *, plugin_name: str) -> None:
        """在核心版本不兼容时显式 fail-fast。"""

        if self.is_compatible_with_core(core_version):
            return
        if self.max_core_version is None:
            raise RegistryError(
                f"插件 {plugin_name} 要求核心版本 >= {self.min_core_version}，当前版本为 {core_version}。"
            )
        raise RegistryError(
            f"插件 {plugin_name} 仅兼容核心版本 [{self.min_core_version}, {self.max_core_version}]，当前版本为 {core_version}。"
        )

    def to_dict(self) -> dict[str, str]:
        """将兼容性信息转换为字典。"""

        payload = {"min_core_version": self.min_core_version}
        if self.max_core_version is not None:
            payload["max_core_version"] = self.max_core_version
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PluginCompatibility":
        """从字典读取兼容性信息。"""

        min_core_version = str(payload.get("min_core_version", "")).strip()
        max_core_version = payload.get("max_core_version")
        resolved_max_version = None if max_core_version in {None, ""} else str(max_core_version).strip()
        return cls(min_core_version=min_core_version, max_core_version=resolved_max_version)


@dataclass(slots=True, frozen=True)
class PluginExtensionManifest:
    """描述插件声明的单个扩展点。"""

    extension_type: str
    key: str
    entry_point: str
    register_function: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.extension_type not in SUPPORTED_EXTENSION_TYPES:
            raise RegistryError(f"插件 manifest 扩展点类型 {self.extension_type} 不受支持。")
        if not self.key:
            raise RegistryError("插件 manifest 扩展点缺少 key。")
        if not self.entry_point:
            raise RegistryError(f"插件扩展点 {self.extension_type}:{self.key} 缺少 entry_point。")

    def to_dict(self) -> dict[str, Any]:
        """将扩展点定义转换为字典。"""

        payload: dict[str, Any] = {
            "extension_type": self.extension_type,
            "key": self.key,
            "entry_point": self.entry_point,
        }
        if self.register_function is not None:
            payload["register_function"] = self.register_function
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PluginExtensionManifest":
        """从字典读取扩展点定义。"""

        metadata = payload.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, Mapping):
            raise RegistryError("插件 manifest 扩展点 metadata 必须为对象。")
        register_function = payload.get("register_function")
        resolved_register_function = None if register_function in {None, ""} else str(register_function).strip()
        return cls(
            extension_type=str(payload.get("extension_type", "")).strip(),
            key=str(payload.get("key", "")).strip(),
            entry_point=str(payload.get("entry_point", "")).strip(),
            register_function=resolved_register_function,
            metadata={str(key): str(value) for key, value in metadata.items()},
        )


@dataclass(slots=True, frozen=True)
class PluginManifest:
    """定义插件 manifest 第一版正式结构。"""

    name: str
    version: str
    manifest_version: str = PLUGIN_MANIFEST_VERSION
    compatibility: PluginCompatibility = field(default_factory=lambda: PluginCompatibility(min_core_version="0.0.0"))
    extensions: tuple[PluginExtensionManifest, ...] = ()
    register_entry: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise RegistryError("插件 manifest 缺少 name。")
        if not self.version:
            raise RegistryError(f"插件 {self.name} 的 manifest 缺少 version。")
        if self.manifest_version != PLUGIN_MANIFEST_VERSION:
            raise RegistryError(
                f"插件 {self.name} 的 manifest_version={self.manifest_version} 不受支持，当前仅支持 {PLUGIN_MANIFEST_VERSION}。"
            )
        if self.register_entry is not None:
            _validate_register_entry(self.register_entry)
        keys = [(extension.extension_type, extension.key) for extension in self.extensions]
        if len(keys) != len(set(keys)):
            raise RegistryError(f"插件 {self.name} 的扩展点声明存在重复 key。")

    def validate_core_version(self, core_version: str) -> None:
        """校验当前插件与指定核心版本的兼容性。"""

        self.compatibility.validate_core_version(core_version, plugin_name=self.name)

    def to_dict(self) -> dict[str, Any]:
        """将 manifest 转换为可序列化字典。"""

        payload: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "manifest_version": self.manifest_version,
            "compatibility": self.compatibility.to_dict(),
            "extensions": [extension.to_dict() for extension in self.extensions],
        }
        if self.register_entry is not None:
            payload["register_entry"] = self.register_entry
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PluginManifest":
        """从字典解析 manifest。"""

        compatibility_payload = payload.get("compatibility", {})
        if not isinstance(compatibility_payload, Mapping):
            raise RegistryError("插件 manifest compatibility 必须为对象。")

        extensions_payload = payload.get("extensions", ())
        if not isinstance(extensions_payload, (list, tuple)):
            raise RegistryError("插件 manifest extensions 必须为数组。")

        register_entry = payload.get("register_entry")
        resolved_register_entry = None if register_entry in {None, ""} else str(register_entry).strip()

        return cls(
            name=str(payload.get("name", "")).strip(),
            version=str(payload.get("version", "")).strip(),
            manifest_version=str(payload.get("manifest_version", PLUGIN_MANIFEST_VERSION)).strip()
            or PLUGIN_MANIFEST_VERSION,
            compatibility=PluginCompatibility.from_dict(compatibility_payload),
            extensions=tuple(PluginExtensionManifest.from_dict(item) for item in extensions_payload),
            register_entry=resolved_register_entry,
        )


def parse_plugin_manifest(payload: Mapping[str, Any]) -> PluginManifest:
    """解析插件 manifest 字典。"""

    return PluginManifest.from_dict(payload)


def _validate_register_entry(register_entry: str) -> None:
    """校验 register_entry 的模块与函数路径格式。"""

    if ":" not in register_entry:
        raise RegistryError("插件 manifest 的 register_entry 必须使用 module:function 形式。")
    module_name, function_name = register_entry.split(":", maxsplit=1)
    if not module_name.strip() or not function_name.strip():
        raise RegistryError("插件 manifest 的 register_entry 必须同时包含模块名与函数名。")


def _parse_version_tokens(version_text: str, *, allow_wildcard: bool) -> tuple[int | str, ...]:
    """解析简单版本号文本。"""

    normalized_text = str(version_text).strip()
    if not normalized_text:
        raise RegistryError("插件版本号不能为空。")

    tokens: list[int | str] = []
    for part in normalized_text.split("."):
        normalized_part = part.strip().lower()
        if not normalized_part:
            raise RegistryError(f"非法插件版本号 {version_text}。")
        if normalized_part == "x":
            if not allow_wildcard:
                raise RegistryError(f"版本约束 {version_text} 不允许使用通配符 x。")
            tokens.append("x")
            continue
        if not normalized_part.isdigit():
            raise RegistryError(f"当前仅支持数字或 x 形式的版本约束，收到 {version_text}。")
        tokens.append(int(normalized_part))
    return tuple(tokens)


def _compare_version_tokens(left_tokens: tuple[int | str, ...], right_tokens: tuple[int | str, ...]) -> int:
    """比较两个纯数字版本号序列。"""

    max_length = max(len(left_tokens), len(right_tokens))
    for index in range(max_length):
        left_value = 0 if index >= len(left_tokens) else left_tokens[index]
        right_value = 0 if index >= len(right_tokens) else right_tokens[index]
        if isinstance(left_value, str) or isinstance(right_value, str):
            raise RegistryError("版本比较阶段不允许包含通配符。")
        if left_value < right_value:
            return -1
        if left_value > right_value:
            return 1
    return 0


def _satisfies_upper_bound(core_tokens: tuple[int | str, ...], max_tokens: tuple[int | str, ...]) -> bool:
    """判断核心版本是否满足上界约束。"""

    if "x" in max_tokens:
        wildcard_index = max_tokens.index("x")
        required_prefix = max_tokens[:wildcard_index]
        return tuple(core_tokens[:wildcard_index]) == required_prefix

    return _compare_version_tokens(core_tokens, max_tokens) <= 0
