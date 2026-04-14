# pyFEM v2 Project Prompt（历史立项草案）

> 本文档记录的是 `Phase 1` 立项时期的目标与约束，主要用于保留早期设计意图。
> 当前仓库的现行阶段、能力范围与路线判断，以 `README.md`、`docs/Architecture_Overview.md`、`docs/Roadmap_v1.2.md` 为准。

## 项目目标
构建一个**商业级结构有限元平台内核**，使用 Python 作为第一阶段实现语言。
该项目面向团队长期开发，不是一次性原型，不是教学 demo，也不是只围绕当前几个单元的临时求解器。

---

## 总体设计目标
本项目必须满足以下目标：

1. 具有清晰、稳定、可演进的架构分层
2. 支持团队并行开发
3. 当前先实现小变形结构分析
4. 架构从第一天开始为以下能力保留扩展点：
   - 几何非线性
   - 材料非线性
   - 接触
   - 更多单元族
   - 更多分析程序
   - ResultsDB / restart
   - 插件机制
   - GUI / API / 脚本接入

---

## 立项时阶段：Phase 1
本文以下内容描述的是立项时对 `Phase 1` 的目标设定，不等同于当前仓库现状。

第一阶段只要求实现一个“商业级骨架 + 第一批能力闭环”。

### Phase 1 必须实现
- v2 目录骨架
- ModelDB 定义对象
- Mesh / ElementRecord / Part / Assembly
- DofManager
- Compiler 与 CompiledModel
- Runtime 抽象接口
- 第一批 element runtimes：
  - C3D8
  - CPS4
  - B21
- 第一批 material runtime：
  - isotropic linear elastic
- 第一批 section runtimes：
  - solid
  - plane stress
  - plane strain
  - beam
- 第一批 procedures：
  - static linear
  - modal
  - basic implicit dynamic
- Assembler
- 线代 backend 抽象
- ResultsWriter / 轻量 ResultsDB 基础闭环
- tests：unit + verification + benchmark baseline

### Phase 1 非目标
以下能力第一阶段可以不实现，但不得阻碍未来扩展：

- 接触算法
- 塑性
- 损伤
- 完整几何非线性实现
- shell family
- 显式动力学生产版
- GUI 精细化
- 高级后处理界面

---

## 绝对约束
以下约束必须严格遵守：

1. **不得把 importer 直接接到 solver。**
2. **不得让 GUI 直接实例化求解内核对象。**
3. **不得让单元通过 node id 算术推导全局 DOF。**
4. **不得使用 `num_nodes * 固定自由度数` 作为平台正式自由度策略。**
5. **不得把多个层次糊进少量大文件。**
6. **不得为了当前 phase 1 牺牲未来几何非线性和动力学扩展能力。**
7. **不得把线性与未来非线性做成两套完全割裂的接口。**
8. **不得把结果输出降级为“直接读求解器内部数组”。**
9. **不得采用只适合单人短期维护的代码组织。**
10. **必须保持模块边界清晰。**

---

## 正式架构主线
项目必须遵循以下主线：

`Importer -> ModelDB -> Compiler -> CompiledModel -> Procedure -> Solver/Assembler -> ResultsWriter/ResultsDB -> Post/GUI/API`

这条主线不可破坏。

---

## 必须存在的正式抽象
以下抽象必须作为正式接口保留：

- ModelDB
- ElementRecord
- DofManager
- CompiledModel
- ElementRuntime
- MaterialRuntime
- SectionRuntime
- ConstraintRuntime
- InteractionRuntime
- ProcedureRuntime
- ResultsWriter

任何实现都必须围绕这些抽象组织，而不是绕开它们写捷径。

---

## 推荐目录结构
项目应按下述方向组织：

- foundation
- modeldb
- mesh
- compiler
- kernel
  - elements
  - materials
  - sections
  - constraints
  - interactions
- procedures
- solver
- io
- post
- job
- plugins
- api
- gui
- tests

可以根据实现细节微调，但不能破坏分层逻辑。

---

## 语言与注释规范
必须严格遵守：

- 所有代码标识符使用英文
- 所有注释使用中文
- 所有 docstring 使用中文
- 所有架构说明、实现总结、测试总结、建议说明使用中文
- 测试函数名可以使用英文，但测试内部注释和说明必须使用中文

---

## 接口设计要求
### Model Layer
- 只表达问题定义
- 不包含求解状态
- 可版本化
- 可校验
- 可序列化

### Compiler Layer
- 负责校验和运行时构建
- 负责 DOF 编号
- 负责 section/material/region 绑定
- 不得耦合 GUI

### Runtime Kernel Layer
- 单元、材料、截面、约束、相互作用全部走统一 runtime 接口
- 单元至少要支持：
  - tangent/residual
  - mass
  - damping 接口保留
  - output
  - state allocation

### Procedure Layer
- 必须 step-driven
- Static / Modal / Dynamic 应通过统一 procedure 抽象组织
- 不得写成彼此独立且难以维护的散乱脚本

### Results Layer
- 必须通过 ResultsWriter / ResultsDB 输出
- 必须支持 field / history / frame 概念
- 要为 restart 和后续扩展预留位置

---

## 数值能力要求
### Phase 1 必须覆盖
- 3D solid：C3D8
- 2D plane：CPS4
- beam：B21
- linear elastic
- static linear
- modal
- basic implicit dynamic

### 后续必须可接入
- geometric nonlinearity
- plasticity
- contact
- more element families
- buckling
- explicit dynamic

---

## 测试与验证要求
必须同步建设：

### unit tests
验证模块本身接口和逻辑

### integration tests
验证 importer/compiler/runtime/procedure 之间能正确协作

### verification tests
至少包含：
- 单元 sanity check
- patch test
- 梁算例
- 模态 benchmark
- 动力学 benchmark

### regression tests
一旦形成 benchmark 基线，后续修改不能破坏旧结果。

---

## Codex 工作方式要求
在执行复杂任务时，Codex 必须遵循以下流程：

1. 先阅读当前仓库结构与已有文件
2. 先给出简短计划
3. 说明将创建/修改哪些文件
4. 分批实现，不要一次性失控扩散
5. 保持模块边界清晰
6. 实现后运行相关测试
7. 最后用中文汇报：
   - 做了什么
   - 哪些文件被创建或修改
   - 当前测试情况
   - 当前局限
   - 下一步建议

---

## Codex 实现偏好
Codex 在实现时应优先做到：

- 先搭骨架，再填功能
- 先稳定接口，再扩展实现
- 使用 dataclass 表达记录/定义/结果对象
- 对公共接口写清晰中文 docstring
- 模块小而清晰
- 依赖方向明确
- 不偷懒写“先这样凑合”的结构

---

## 完成标准
只有满足以下条件，才算 Phase 1 达到“可接受”：

1. 仓库已形成清晰的 v2 架构骨架
2. 核心接口已实现且职责明确
3. ModelDB → Compiler → CompiledModel → Procedure 的主线可运行
4. C3D8 / CPS4 / B21 已通过新架构接入
5. Static Linear / Modal / basic Implicit Dynamic 至少形成基础闭环
6. ResultsWriter 可写出正式结果
7. 测试存在且通过
8. 代码库明显适合后续团队扩展

---

## 最终提醒
本项目的核心不是“尽快写出很多功能”，而是：

> **先建立一个正确的商业级平台骨架，再让功能自然生长。**

所有实现都必须服务于这个目标。
