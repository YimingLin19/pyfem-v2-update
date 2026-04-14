"""插件发现与注册测试。"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from pyfem.compiler import RuntimeRegistry
from pyfem.foundation.errors import RegistryError
from pyfem.io import InpImporter
from pyfem.plugins import PluginDiscoveryService


class PluginDiscoveryTests(unittest.TestCase):
    """验证插件 manifest 的发现、约束与注册调用。"""

    def test_plugin_discovery_calls_register_function_through_runtime_registry(self) -> None:
        plugin_root = Path("tests") / f"_plugin_discovery_{uuid4().hex}"
        plugin_root.mkdir(parents=True, exist_ok=True)
        manifest_path = plugin_root / "plugin.json"
        try:
            manifest_path.write_text(
                json.dumps(
                    {
                        "name": "demo-plugin",
                        "version": "0.1.0",
                        "compatibility": {"min_core_version": "0.1.0", "max_core_version": "0.x"},
                        "register_entry": "tests.plugin_fixtures.runtime_registry_plugin:register_demo_importer",
                        "extensions": [
                            {
                                "extension_type": "importer",
                                "key": "demo_fixture_inp",
                                "entry_point": "tests.plugin_fixtures.runtime_registry_plugin:DemoImporter",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            service = PluginDiscoveryService()
            discovered = service.discover(plugin_root)
            registry = RuntimeRegistry()
            registered = service.register_into_registry(registry, discovered)

            self.assertEqual(discovered[0].path, manifest_path)
            self.assertEqual(registered[0].name, "demo-plugin")
            self.assertIsInstance(registry.create_importer("demo_fixture_inp"), InpImporter)
            self.assertEqual(registry.get_plugin_manifest("demo-plugin").version, "0.1.0")
        finally:
            shutil.rmtree(plugin_root, ignore_errors=True)

    def test_plugin_discovery_rejects_missing_register_entry_invalid_signature_invalid_annotation_duplicate_key_and_incompatible_version(self) -> None:
        service = PluginDiscoveryService()

        missing_register_manifest = self._write_manifest(
            {
                "name": "missing-register",
                "version": "0.1.0",
                "compatibility": {"min_core_version": "0.1.0"},
                "extensions": [
                    {
                        "extension_type": "importer",
                        "key": "demo_fixture_inp",
                        "entry_point": "tests.plugin_fixtures.runtime_registry_plugin:DemoImporter",
                    }
                ],
            }
        )
        invalid_signature_manifest = self._write_manifest(
            {
                "name": "invalid-signature",
                "version": "0.1.0",
                "compatibility": {"min_core_version": "0.1.0"},
                "register_entry": "tests.plugin_fixtures.runtime_registry_plugin:invalid_signature",
                "extensions": [],
            }
        )
        invalid_annotation_manifest = self._write_manifest(
            {
                "name": "invalid-annotation",
                "version": "0.1.0",
                "compatibility": {"min_core_version": "0.1.0"},
                "register_entry": "tests.plugin_fixtures.runtime_registry_plugin:invalid_annotation",
                "extensions": [],
            }
        )
        duplicate_key_manifest = self._write_manifest(
            {
                "name": "duplicate-importer",
                "version": "0.1.0",
                "compatibility": {"min_core_version": "0.1.0"},
                "register_entry": "tests.plugin_fixtures.runtime_registry_plugin:register_duplicate_importer",
                "extensions": [
                    {
                        "extension_type": "importer",
                        "key": "inp",
                        "entry_point": "pyfem.io.inp:InpImporter",
                    }
                ],
            }
        )
        incompatible_manifest = self._write_manifest(
            {
                "name": "future-plugin",
                "version": "0.1.0",
                "compatibility": {"min_core_version": "9.0.0"},
                "register_entry": "tests.plugin_fixtures.runtime_registry_plugin:register_demo_importer",
                "extensions": [
                    {
                        "extension_type": "importer",
                        "key": "demo_fixture_inp",
                        "entry_point": "tests.plugin_fixtures.runtime_registry_plugin:DemoImporter",
                    }
                ],
            }
        )

        try:
            with self.assertRaisesRegex(RegistryError, "缺少 register_entry"):
                service.register_into_registry(RuntimeRegistry(), service.discover(missing_register_manifest.parent))

            with self.assertRaisesRegex(RegistryError, "只接收一个 RuntimeRegistry 参数"):
                service.register_into_registry(RuntimeRegistry(), (service.load_manifest(invalid_signature_manifest),))

            with self.assertRaisesRegex(RegistryError, "必须标注 RuntimeRegistry 类型"):
                service.register_into_registry(RuntimeRegistry(), (service.load_manifest(invalid_annotation_manifest),))

            with self.assertRaisesRegex(RegistryError, "已存在"):
                service.register_into_registry(RuntimeRegistry(), (service.load_manifest(duplicate_key_manifest),))

            with self.assertRaisesRegex(RegistryError, "当前版本"):
                service.register_into_registry(RuntimeRegistry(), (service.load_manifest(incompatible_manifest),))
        finally:
            shutil.rmtree(missing_register_manifest.parent, ignore_errors=True)
            shutil.rmtree(invalid_signature_manifest.parent, ignore_errors=True)
            shutil.rmtree(invalid_annotation_manifest.parent, ignore_errors=True)
            shutil.rmtree(duplicate_key_manifest.parent, ignore_errors=True)
            shutil.rmtree(incompatible_manifest.parent, ignore_errors=True)

    def test_plugin_discovery_rejects_missing_path_invalid_json_and_unregistered_declared_extension(self) -> None:
        service = PluginDiscoveryService()
        with self.assertRaisesRegex(RegistryError, "不存在"):
            service.discover(Path("tests") / "_missing_plugin_root")

        invalid_json_root = Path("tests") / f"_plugin_discovery_invalid_{uuid4().hex}"
        invalid_json_root.mkdir(parents=True, exist_ok=True)
        invalid_json_manifest = invalid_json_root / "plugin.json"

        mismatched_manifest = self._write_manifest(
            {
                "name": "mismatched-plugin",
                "version": "0.1.0",
                "compatibility": {"min_core_version": "0.1.0"},
                "register_entry": "tests.plugin_fixtures.runtime_registry_plugin:register_mismatched_importer",
                "extensions": [
                    {
                        "extension_type": "importer",
                        "key": "declared_fixture_inp",
                        "entry_point": "tests.plugin_fixtures.runtime_registry_plugin:DemoImporter",
                    }
                ],
            }
        )
        try:
            invalid_json_manifest.write_text("{ invalid json }", encoding="utf-8")
            with self.assertRaisesRegex(RegistryError, "不是合法 JSON"):
                service.load_manifest(invalid_json_manifest)

            with self.assertRaisesRegex(RegistryError, "未通过 RuntimeRegistry 注册扩展点 importer:declared_fixture_inp"):
                service.register_into_registry(RuntimeRegistry(), (service.load_manifest(mismatched_manifest),))
        finally:
            shutil.rmtree(invalid_json_root, ignore_errors=True)
            shutil.rmtree(mismatched_manifest.parent, ignore_errors=True)

    def _write_manifest(self, payload: dict[str, object]) -> Path:
        plugin_root = Path("tests") / f"_plugin_discovery_case_{uuid4().hex}"
        plugin_root.mkdir(parents=True, exist_ok=True)
        manifest_path = plugin_root / "plugin.json"
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path


if __name__ == "__main__":
    unittest.main()
