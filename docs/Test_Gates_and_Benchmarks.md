# pyFEM v2 测试门禁与基准

## 1. 文档目的
本文档说明当前测试分层、benchmark 落点与推荐门禁入口。

## 2. 当前测试分层
- `tests/unit/`：模块接口、fail-fast、契约边界
- `tests/integration/`：主线串联与执行壳
- `tests/verification/`：patch test 与 benchmark 最小保护集
- `tests/regression/`：架构回归、Phase 1 baseline、结果合同、实例作用域、多步路径

当前 `pytest` 还通过根目录 `conftest.py` 自动补充一部分 marker，避免门禁只依赖手工标注：

- `tests/unit/` 与 `tests/regression/` 自动补 `gate_fast`
- 所有测试自动补 `gate_full`
- 名称包含 `scope / instance_scope / compilation_scopes` 的测试自动补 `instance_scope`
- 名称包含 `multistep` 的测试自动补 `multistep`
- 名称包含 `results_`、`query_probe`、`vtk_exporter` 的测试自动补 `results_contract`

## 3. 当前 benchmark / verification 覆盖
当前已存在的最小保护集包括：

- `C3D8 / CPS4 / B21` patch tests
- 梁 / 平面 / 实体 benchmark 最小集合
- `static / modal / implicit_dynamic` 基础主线验证
- rotated instance 的 solver 级回归

这些测试的目标不是堆数量，而是保护：

- canonical scope / compilation scope
- transformed geometry 数值消费边界
- multi-step 结果路径
- results contract
- reader-only 消费边界
- result key / scope / load / output 语义

## 4. 当前推荐门禁
### 快速门禁
```powershell
python -m pytest -m gate_fast
```

适合：

- 本地高频回归
- 架构边界与 Phase 1 baseline 快速确认

### 较全门禁
```powershell
python -m pytest -m gate_full
```

适合：

- 合并前检查
- 全层级回归

### 兼容入口
```powershell
python -m unittest discover -s tests
```

用于兼容既有测试习惯与补充校验。

## 5. 当前推荐使用方式
1. 本地改动先跑 `gate_fast`
2. 提交前跑 `gate_full`
3. 需要兼容旧入口时再跑 `unittest discover`

## 6. 结果解读原则
- `verification` 关注数值合理性
- `regression` 关注架构边界和已完成主线零回归
- 不要把 verification 与 regression 混成一类
- 不要为了过测试恢复 JSON dict 或 solver 旁路
