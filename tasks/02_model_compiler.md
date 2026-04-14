# Task 02 - ModelDB + Compiler + DOF 闭环

请严格读取并遵守仓库根目录中的 `AGENTS.md` 和 `Prompt.md`。

## 本轮任务目标
实现 v2 的“模型层 + 编译层 + 自由度层”最小闭环。

---

## 必须完成的内容

### 1. 完善 ModelDB 相关定义对象
至少完善以下定义：
- Metadata
- ModelDB
- Part
- Assembly
- NodeRecord
- ElementRecord
- Mesh
- MaterialDef
- SectionDef
- BoundaryDef
- NodalLoadDef
- DistributedLoadDef
- StepDef
- OutputRequest
- JobDef

### 2. 完善 ElementRecord / Mesh
要求：
- `ElementRecord` 必须显式包含 `type_key`
- `Mesh` 必须支持 nodes / elements / node_sets / element_sets / surfaces / orientations

### 3. 实现正式 DofManager
必须支持：
- `register_node_dofs`
- `register_extra_dofs`
- `finalize`
- `get_global_id`
- `get_node_dof_ids`
- `num_dofs`

### 4. 设计并实现 DOF layout 机制
至少覆盖：
- C3D8: UX UY UZ
- CPS4: UX UY
- B21: UX UY RZ

要求：
- DOF 名必须是显式字符串，不允许隐式约定
- 为未来 `RX RY RZ`、拉格朗日乘子等预留空间

### 5. 实现 CompiledModel
至少包含：
- model
- dof_manager
- element_runtimes
- material_runtimes
- section_runtimes
- constraint_runtimes
- interaction_runtimes
- step_runtimes

### 6. 实现最小可工作的 Compiler
至少完成：
- 基本模型校验
- section / material / region 绑定
- 节点 DOF 注册
- runtime 占位对象创建
- 输出 CompiledModel

### 7. 加入测试
至少增加：
- ModelDB 构造测试
- DofManager 编号测试
- Compiler 输出 CompiledModel 测试

---

## 严格要求
1. 所有代码标识符使用英文。
2. 所有注释和 docstring 使用中文。
3. Compiler 不能依赖 GUI。
4. Importer 不能直接负责编译之外的求解逻辑。
5. 不允许出现 `num_nodes * 常量自由度数` 的设计。
6. 不允许把 DOF 编号逻辑写回 element 类。

---

## 工作方式要求
1. 先检查 task 01 已有结构。
2. 输出本轮计划。
3. 按“模型定义 -> DOF -> 编译层 -> 测试”顺序实施。
4. 最后汇报：
   - 改了哪些文件
   - 做了哪些设计决定
   - 测试结果
   - 还有什么没做
   - 下一步建议

---

## 交付标准
本轮结束后，应具备：
- 一个清晰的模型定义层
- 一个正式的 DofManager
- 一个最小可工作的 Compiler
- 从 ModelDB 到 CompiledModel 的基本闭环