"""插件 manifest 第一版测试。"""

import unittest

from pyfem.foundation.errors import RegistryError
from pyfem.plugins import (
    PLUGIN_MANIFEST_VERSION,
    PluginExtensionManifest,
    PluginManifest,
    parse_plugin_manifest,
)


class PluginManifestTests(unittest.TestCase):
    """验证插件 manifest 的最小解析与校验。"""

    def test_manifest_can_roundtrip_from_dict_and_keep_register_entry(self) -> None:
        manifest = parse_plugin_manifest(
            {
                "name": "demo-plugin",
                "version": "0.1.0",
                "manifest_version": PLUGIN_MANIFEST_VERSION,
                "compatibility": {"min_core_version": "0.1.0", "max_core_version": "0.x"},
                "register_entry": "tests.plugin_fixtures.runtime_registry_plugin:register_demo_importer",
                "extensions": [
                    {
                        "extension_type": "importer",
                        "key": "demo_fixture_inp",
                        "entry_point": "tests.plugin_fixtures.runtime_registry_plugin:DemoImporter",
                        "register_function": "register_demo_importer",
                        "metadata": {"description": "demo importer"},
                    }
                ],
            }
        )

        payload = manifest.to_dict()

        self.assertEqual(manifest.name, "demo-plugin")
        self.assertEqual(manifest.version, "0.1.0")
        self.assertEqual(manifest.register_entry, "tests.plugin_fixtures.runtime_registry_plugin:register_demo_importer")
        self.assertTrue(manifest.compatibility.is_compatible_with_core("0.1.0"))
        self.assertEqual(payload["register_entry"], manifest.register_entry)
        self.assertEqual(PluginManifest.from_dict(payload), manifest)

    def test_manifest_rejects_unsupported_extension_type_and_invalid_register_entry(self) -> None:
        with self.assertRaisesRegex(RegistryError, "不受支持"):
            PluginExtensionManifest(
                extension_type="solver_backend",
                key="demo_backend",
                entry_point="demo_plugin.backend:Backend",
            )

        with self.assertRaisesRegex(RegistryError, "module:function"):
            parse_plugin_manifest(
                {
                    "name": "demo-plugin",
                    "version": "0.1.0",
                    "compatibility": {"min_core_version": "0.1.0"},
                    "register_entry": "tests.plugin_fixtures.runtime_registry_plugin.register_demo_importer",
                    "extensions": [],
                }
            )

    def test_manifest_rejects_invalid_structure_duplicate_key_and_incompatible_version(self) -> None:
        with self.assertRaisesRegex(RegistryError, "compatibility 必须为对象"):
            parse_plugin_manifest(
                {
                    "name": "demo-plugin",
                    "version": "0.1.0",
                    "compatibility": [],
                    "extensions": [],
                }
            )

        with self.assertRaisesRegex(RegistryError, "存在重复 key"):
            parse_plugin_manifest(
                {
                    "name": "demo-plugin",
                    "version": "0.1.0",
                    "compatibility": {"min_core_version": "0.1.0"},
                    "extensions": [
                        {
                            "extension_type": "importer",
                            "key": "demo_inp",
                            "entry_point": "demo_plugin.io:DemoImporter",
                        },
                        {
                            "extension_type": "importer",
                            "key": "demo_inp",
                            "entry_point": "demo_plugin.io:DemoImporterV2",
                        },
                    ],
                }
            )

        manifest = parse_plugin_manifest(
            {
                "name": "demo-plugin",
                "version": "0.1.0",
                "compatibility": {"min_core_version": "9.0.0"},
                "extensions": [],
            }
        )

        with self.assertRaisesRegex(RegistryError, "当前版本"):
            manifest.validate_core_version("0.1.0")


if __name__ == "__main__":
    unittest.main()
