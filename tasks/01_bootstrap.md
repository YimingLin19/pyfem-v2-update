# Task 01 - Bootstrap v2 架构骨架

请严格读取并遵守仓库根目录中的 `AGENTS.md` 和 `Prompt.md`。

## 本轮任务目标
搭建 pyFEM v2 的正式项目骨架与核心接口雏形。

本轮只做“架构落地第一步”，不要追求一次性实现所有数值功能。

---

## 必须完成的内容

### 1. 创建 v2 的目录结构
至少创建以下目录骨架（可根据实现需要增加，但不要破坏分层）：

- foundation
- modeldb
- mesh
- compiler
- kernel/common
- kernel/elements
- kernel/materials
- kernel/sections
- kernel/constraints
- kernel/interactions
- procedures
- solver
- io/importers
- io/exporters
- io/resultsdb
- post
- job
- plugins
- api
- gui
- tests/unit
- tests/integration
- tests/verification
- tests/regression

### 2. 创建核心模块文件骨架
至少创建以下核心文件（如需拆分可增加）：

- `modeldb/model.py`
- `mesh/node.py`
- `mesh/mesh.py`
- `mesh/element_record.py`
- `mesh/dof_manager.py`
- `compiler/compiled_model.py`
- `compiler/compiler.py`
- `kernel/common/context.py`
- `kernel/common/state.py`
- `kernel/common/contribution.py`
- `kernel/elements/base.py`
- `kernel/materials/base.py`
- `kernel/sections/base.py`
- `kernel/constraints/base.py`
- `kernel/interactions/base.py`
- `procedures/base.py`
- `solver/problem.py`
- `io/resultsdb/writer.py`

### 3. 实现核心抽象接口雏形
至少要有以下抽象或正式定义：
- ModelDB
- ElementRecord
- DofManager
- CompiledModel
- Compiler
- ElementRuntime
- MaterialRuntime
- SectionRuntime
- ConstraintRuntime
- InteractionRuntime
- ProcedureRuntime
- ResultsWriter

### 4. 所有公共接口必须具备
- Python 类型标注
- 中文 docstring
- 清晰职责说明

---

## 严格要求
1. 所有代码标识符使用英文。
2. 所有注释使用中文。
3. 所有 docstring 使用中文。
4. 不要实现 TL/UL，不要实现接触算法，不要实现 GUI 功能。
5. 不要把多个层次糊进一个文件。
6. 不要为了省事把未来扩展点删掉。
7. 不允许出现 `num_nodes * 固定自由度` 的正式实现逻辑。
8. 不允许在单元内部通过 node id 算术推导全局 DOF。

---

## 工作方式要求
1. 先输出一个简洁计划。
2. 再分批创建文件。
3. 检查模块依赖是否清晰。
4. 最后运行最基本的导入/静态检查（如果适用）。
5. 输出总结时用中文说明：
   - 创建了哪些文件
   - 每个文件做什么
   - 当前有哪些未实现部分
   - 下一步推荐做什么

---

## 交付标准
本轮结束后，仓库中应该已经出现一个清晰的 v2 主骨架，并且核心接口雏形完整存在。