# Task 99 - 全仓架构审查与 Phase 1 完成度审查

请严格读取并遵守仓库根目录中的 `AGENTS.md` 和 `Prompt.md`。

## 本轮任务目标
对当前 pyFEM v2 仓库进行一次系统性的架构审查、实现审查和 Phase 1 完成度审查。

目标不是新增很多功能，而是判断当前仓库是否真正符合 v2 的商业级结构平台路线，而不是“表面上有目录、实质上仍然存在旧式耦合”。

---

## 审查重点

### 1. 架构边界审查
请重点检查：
- importer 是否仍越权影响 solver internals
- GUI / app 层是否越权决定具体数值对象
- compiler 是否真正存在并发挥作用
- ModelDB 是否真正成为问题定义中心
- ResultsWriter / ResultsDB 是否真正独立

### 2. DOF 体系审查
请重点检查：
- 是否仍存在 `num_nodes * 常量自由度` 假设
- 是否仍存在 element 内部根据 node id 算 global dof 的逻辑
- 是否存在隐式固定 3 自由度思路
- 梁 / 平面 / 三维的 DOF layout 是否真正独立

### 3. Runtime 接口审查
检查：
- ElementRuntime 是否统一
- MaterialRuntime 是否状态化
- ProcedureRuntime 是否统一
- static / modal / dynamic 是否被合理组织
- 是否已经为未来几何非线性保留稳定扩展点

### 4. 代码质量审查
检查：
- 是否存在超大文件
- 是否存在职责污染
- 是否存在明显循环依赖
- 中文注释和中文 docstring 规范是否被遵守
- 是否有模块命名混乱问题

### 5. 测试体系审查
检查：
- unit tests 覆盖情况
- verification tests 覆盖情况
- regression baseline 是否已初步建立
- 当前 benchmark 是否足以支撑 Phase 1 质量门禁

### 6. Phase 1 完成度审查
判断以下内容是否完成、部分完成或未完成：
- 目录骨架
- ModelDB
- DofManager
- Compiler
- C3D8 / CPS4 / B21
- Elastic material
- Sections
- Static Linear
- Modal
- Basic Implicit Dynamic
- ResultsWriter / ResultsReader
- Importer / Exporter
- End-to-end path
- tests / verification

---

## 输出要求
请输出一份中文审查报告，至少包含：

1. **总体评价**
2. **当前架构优点**
3. **当前架构风险**
4. **问题清单**
   - 高优先级
   - 中优先级
   - 低优先级
5. **Phase 1 完成度表**
6. **建议立即修改的事项**
7. **建议的下一轮开发任务**

如果发现严重架构问题，请指出具体文件与问题类型。

---

## 严格要求
1. 所有说明必须使用中文。
2. 审查必须具体，不要泛泛而谈。
3. 要尽量给出文件级、模块级建议。
4. 不要只夸优点，要明确指出结构风险。
5. 如果某些地方只是“能跑但不够商业级”，要明确说出来。

---

## 交付标准
本轮结束后，应形成一份可供团队评审和下一阶段排期使用的正式架构审查报告。