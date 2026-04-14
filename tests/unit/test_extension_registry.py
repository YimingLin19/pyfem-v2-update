"""统一扩展注册表测试。"""

from pathlib import Path
import unittest
from uuid import uuid4

from pyfem.compiler import RuntimeRegistry
from pyfem.foundation.errors import RegistryError
from pyfem.io import InMemoryResultsWriter, InpImporter, JsonResultsReader, JsonResultsWriter, VtkExporter
from pyfem.plugins import PluginCompatibility, PluginExtensionManifest, PluginManifest


class ExtensionRegistryTests(unittest.TestCase):
    """验证 importer/exporter/results IO 与 manifest 的正式注册面。"""

    def test_builtin_io_extensions_are_available_from_single_registry_surface(self) -> None:
        registry = RuntimeRegistry()
        target_path = Path("tests") / f"_tmp_registry_results_{uuid4().hex}.json"
        try:
            importer = registry.create_importer("inp")
            writer = registry.create_results_writer("json", target_path)
            memory_writer = registry.create_results_writer("memory")
            reader = registry.create_results_reader("json", target_path)
            exporter = registry.create_exporter("vtk")

            self.assertIsInstance(importer, InpImporter)
            self.assertIsInstance(writer, JsonResultsWriter)
            self.assertIsInstance(memory_writer, InMemoryResultsWriter)
            self.assertIsInstance(reader, JsonResultsReader)
            self.assertIsInstance(exporter, VtkExporter)
        finally:
            target_path.unlink(missing_ok=True)

    def test_missing_io_extensions_fail_fast_with_clear_error(self) -> None:
        registry = RuntimeRegistry()

        with self.assertRaisesRegex(RegistryError, "未注册模型导入器 custom_inp"):
            registry.create_importer("custom_inp")
        with self.assertRaisesRegex(RegistryError, "未注册结果 writer binary"):
            registry.create_results_writer("binary")
        with self.assertRaisesRegex(RegistryError, "未注册结果 reader binary"):
            registry.create_results_reader("binary")
        with self.assertRaisesRegex(RegistryError, "未注册结果 exporter custom_vtk"):
            registry.create_exporter("custom_vtk")

    def test_plugin_manifest_registers_through_runtime_registry(self) -> None:
        registry = RuntimeRegistry()
        manifest = PluginManifest(
            name="demo-plugin",
            version="0.1.0",
            compatibility=PluginCompatibility(min_core_version="0.1.0"),
            register_entry="tests.plugin_fixtures.runtime_registry_plugin:register_demo_importer",
            extensions=(
                PluginExtensionManifest(
                    extension_type="importer",
                    key="demo_inp",
                    entry_point="demo_plugin.io:DemoImporter",
                    register_function="register_plugin",
                ),
            ),
        )

        registry.register_plugin_manifest(manifest)

        self.assertIs(registry.get_plugin_manifest("demo-plugin"), manifest)
        self.assertEqual(registry.find_plugin_manifest("demo-plugin"), manifest)

        with self.assertRaisesRegex(RegistryError, "已存在"):
            registry.register_plugin_manifest(manifest)
        with self.assertRaisesRegex(RegistryError, "未注册插件 manifest missing-plugin"):
            registry.get_plugin_manifest("missing-plugin")


if __name__ == "__main__":
    unittest.main()
