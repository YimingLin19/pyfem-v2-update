# pyFEM v2 开发指南

## 1. 适用范围
本文档适用于当前 `Phase 6A` 仓库开发。

## 2. 开发基本原则
1. `ModelDB` 是问题定义唯一来源。
2. `Compiler` 是 ModelDB 与 Runtime 的强制中间层。
3. `DofManager` 负责全局 DOF 编号。
4. 正式结果必须走 `ResultsWriter / ResultsReader / ResultsDB`。
5. `RuntimeRegistry` 是唯一正式扩展面。

术语约定：

- `ResultsDB` 表示结果后端与结果数据库这一层概念。
- 当前代码中的逻辑结果对象类型名为 `ResultsDatabase`。
- 文档引用两者时，应明确“概念层”和“代码类型名”的区别。

## 3. 产品层约束
- importer 不得直接驱动 solver
- GUI 不得直接实例化 solver / backend / element
- API 不得暴露 assembler / problem / backend 内部对象
- Job 不得形成第二套执行主线
- Results 消费层不得绕过 `ResultsReader`

## 4. 代码规范
- 标识符使用英文
- 注释与 docstring 使用中文
- 公共接口保留类型标注
- 记录型对象优先 `dataclass`
- 模块应保持单一职责

## 5. 测试纪律
新增能力必须同步补测试，并放入正确层级：

- `tests/unit/`
- `tests/integration/`
- `tests/verification/`
- `tests/regression/`

当前推荐门禁：

```powershell
python -m pytest -m gate_fast
python -m pytest -m gate_full
python -m unittest discover -s tests
```

## 6. 文档纪律
- 文档必须与当前代码状态一致
- 不写仓库中不存在的能力
- 历史设计与当前状态不一致时，要明确标成历史草案或评审记录

## 7. 扩展纪律
- 新扩展点优先挂到 `RuntimeRegistry`
- plugin manifest 只做 metadata 与发现/注册壳
- 不允许为了“看起来插件化”而新建平行机制

## 8. 修改前检查清单
在开始非平凡改动前，至少先确认以下问题：

1. 是否绕开了 `ModelDB -> Compiler -> Procedure -> Results` 正式主线。
2. 是否让 `GUI / API / Job / Post` 反向依赖 `solver / assembler / backend` 内部细节。
3. 是否新增了 `RuntimeRegistry` 之外的第二套注册、发现或执行机制。
4. 是否需要同步更新测试、文档与阶段说明，避免把历史草案当成当前现状。

## 9. 当前推荐工作流
1. 明确边界与目标
2. 审计相关代码与测试
3. 先补正式入口，再补包装壳
4. 写定向测试
5. 跑 `gate_fast / gate_full / unittest`
6. 最后更新文档
