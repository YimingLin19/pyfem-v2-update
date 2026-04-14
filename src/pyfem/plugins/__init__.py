"""插件层公共入口。"""

from pyfem.plugins.discovery import DiscoveredPluginManifest, PluginDiscoveryService
from pyfem.plugins.manifest import (
    PLUGIN_MANIFEST_VERSION,
    SUPPORTED_EXTENSION_TYPES,
    PluginCompatibility,
    PluginExtensionManifest,
    PluginManifest,
    parse_plugin_manifest,
)

__all__ = [
    "DiscoveredPluginManifest",
    "PLUGIN_MANIFEST_VERSION",
    "SUPPORTED_EXTENSION_TYPES",
    "PluginCompatibility",
    "PluginDiscoveryService",
    "PluginExtensionManifest",
    "PluginManifest",
    "parse_plugin_manifest",
]
