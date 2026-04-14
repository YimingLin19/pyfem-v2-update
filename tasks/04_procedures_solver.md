# Task 04 - Procedure + Solver + Assembler 闭环

请严格读取并遵守仓库根目录中的 `AGENTS.md` 和 `Prompt.md`。

## 本轮任务目标
实现第一批分析程序与求解核心闭环，包括：
- Static Linear
- Modal
- 基础 Implicit Dynamic

并形成从 `CompiledModel -> Procedure -> Solver -> ResultsWriter` 的主线。

---

## 必须完成的内容

### 1. 实现 Assembler
Assembler 至少应支持：
- 收集 element contributions
- 组装全局 tangent
- 组装全局 residual
- 组装全局 mass
- 预留 damping 组装接口
- 处理基本约束贡献（当前至少 SPC）

要求：
- Assembler 不得依赖具体单元类型名
- Assembler 只负责装配，不负责定义模型

### 2. 实现 DiscreteProblem
至少要有结构问题的最小实现，支持：
- `assemble_tangent`
- `assemble_residual`
- `assemble_mass`
- `assemble_damping`
- `commit`
- `rollback`

### 3. 实现线性代数 backend 抽象
至少实现：
- `LinearAlgebraBackend` 抽象
- `SciPyBackend` 实现

要求：
- 线性求解和特征值求解都要有入口
- 不要把 SciPy 细节散落在 procedure 中

### 4. 实现 ProcedureRuntime 第一批
至少实现：
- `StaticLinearProcedure`
- `ModalProcedure`
- `ImplicitDynamicProcedure`

### 5. 隐式动力学
可先采用：
- Newmark
或
- generalized-alpha

但接口必须可扩展，不得写成只适合当前一个算法的死结构。

### 6. Step 驱动
Procedure 必须基于 step runtime 组织，而不是直接写成几个散乱函数。

### 7. ResultsWriter 接入
Procedure 执行过程中，结果必须通过 `ResultsWriter` 输出：
- frame
- field outputs
- history outputs（当前至少支持基础形式）

### 8. 测试 / 验证
至少增加：
- static linear benchmark
- modal benchmark
- simple implicit dynamic benchmark

---

## 严格要求
1. 所有代码标识符使用英文。
2. 所有注释和 docstring 使用中文。
3. 不要把 static / modal / dynamic 粘在一个大文件里。
4. 不要让 procedure 依赖具体单元类名。
5. 不要跳回 GUI 路径。
6. 结果输出必须走 ResultsWriter，不允许直接返回临时数组作为正式接口。

---

## 工作方式要求
1. 先检查当前 assembler/problem/procedure 接口。
2. 输出简洁计划。
3. 按“assembler -> backend -> problem -> procedures -> tests”顺序推进。
4. 最后汇报：
   - 新建/修改文件
   - 程序设计说明
   - 采用的动力学积分策略
   - 测试结果
   - 当前局限
   - 下一步建议

---

## 交付标准
本轮结束后，应具备：
- static linear 闭环
- modal 闭环
- basic implicit dynamic 闭环
- ResultsWriter 已接入 procedure 主线