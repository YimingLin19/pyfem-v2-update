"""内置扩展注册总入口。"""

from __future__ import annotations


def register_builtin_extensions(registry) -> None:
    """集中注册 Phase 1 / Phase 2 当前内置扩展。"""

    from pyfem.compiler.builtin_procedure_providers import register_builtin_procedure_providers
    from pyfem.compiler.builtin_providers import register_builtin_runtime_providers
    from pyfem.io.builtin_extensions import register_builtin_io_extensions

    register_builtin_runtime_providers(registry)
    register_builtin_procedure_providers(registry)
    register_builtin_io_extensions(registry)
