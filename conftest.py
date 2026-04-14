"""pytest 全局门禁配置。"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """按目录与主题为测试自动补充标准门禁标记。"""

    del config
    for item in items:
        relative_path = Path(str(item.fspath)).resolve().relative_to(ROOT).as_posix()
        item.add_marker(pytest.mark.gate_full)

        if relative_path.startswith("tests/unit/"):
            item.add_marker(pytest.mark.unit)
            item.add_marker(pytest.mark.gate_fast)
        elif relative_path.startswith("tests/integration/"):
            item.add_marker(pytest.mark.integration)
        elif relative_path.startswith("tests/verification/"):
            item.add_marker(pytest.mark.verification)
        elif relative_path.startswith("tests/regression/"):
            item.add_marker(pytest.mark.regression)
            item.add_marker(pytest.mark.gate_fast)

        if "phase1_baseline" in relative_path:
            item.add_marker(pytest.mark.phase1_baseline)
        if any(token in relative_path for token in ("scope", "instance_scope", "compilation_scopes")):
            item.add_marker(pytest.mark.instance_scope)
        if "multistep" in relative_path:
            item.add_marker(pytest.mark.multistep)
        if "results_" in relative_path or "query_probe" in relative_path or "vtk_exporter" in relative_path:
            item.add_marker(pytest.mark.results_contract)
