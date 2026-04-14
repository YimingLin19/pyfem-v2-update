"""插件 discovery/register 测试夹具。"""

from pyfem.compiler import RuntimeRegistry
from pyfem.io import InpImporter


def register_demo_importer(registry: RuntimeRegistry) -> None:
    """注册测试 importer。"""

    registry.register_importer("demo_fixture_inp", InpImporter)


def register_mismatched_importer(registry: RuntimeRegistry) -> None:
    """故意注册与 manifest 不一致的 importer key。"""

    registry.register_importer("mismatched_fixture_inp", InpImporter)


def register_duplicate_importer(registry: RuntimeRegistry) -> None:
    """故意覆盖 builtin importer key。"""

    registry.register_importer("inp", InpImporter)


def invalid_signature(registry: RuntimeRegistry, extra_argument: object) -> None:
    """提供非法签名测试夹具。"""

    del registry
    del extra_argument


def invalid_annotation(registry: object) -> None:
    """提供错误类型标注的测试夹具。"""

    del registry
