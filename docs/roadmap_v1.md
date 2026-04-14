# pyFEM v2 路线图（历史版本草案）

> 本文档是较早阶段形成的详细路线图草案，保留用于追溯阶段设计思路。
> 当前生效的阶段判断与路线收口，请以 `docs/Roadmap_v1.2.md` 为准；本文不再作为当前状态真源。

## 1. 文档目的
本文档用于定义 pyFEM v2 的整体开发路线图，明确：

- 当前阶段目标
- 各阶段核心任务
- 阶段之间的依赖关系
- 团队开发优先级
- 何时进入下一阶段的判断标准

本文档基于“商业级结构有限元平台”目标制定，适用于团队长期开发。

---

## 2. 项目定位
pyFEM v2 的目标是构建一个**商业级结构有限元平台内核与产品基础**。

项目必须从第一天起为以下能力预留正式架构位置：

- 更多单元族
- 更多材料模型
- 几何非线性
- 材料非线性
- 接触
- 动力学与振动
- 结果数据库
- 重启动
- 插件与脚本扩展
- GUI 与后处理工作流

---

## 3. 总体开发原则

### 3.1 先平台，后功能
优先搭建稳定平台骨架，再逐步填充能力。

### 3.2 先接口，后实现
公共接口与模块边界必须先建立主形态，再逐步实现具体内容。

### 3.3 先主线闭环，后高级能力
优先打通：
`ModelDB -> Compiler -> CompiledModel -> Procedure -> Solver -> ResultsDB`

### 3.4 先验证，后扩展
任何新能力都必须配套验证算例与回归测试。

### 3.5 产品层可以提前，但不能反向绑死内核
GUI、API、Job、ResultsReader 等产品能力可以提前建设，但只能消费平台接口，不能反向决定内核结构。

### 3.6 未来能力先保留正式落点，不抢跑实现
对于几何非线性、材料非线性、接触、MPC / multiplier、复杂装配、工程级 ResultsDB 与高性能求解等未来能力，当前阶段优先保证：

- 在正式主线上有明确落点
- 接口与状态生命周期可扩展
- 当前不支持时明确 fail-fast
- 不用临时实现绑死未来架构

### 3.7 先做结构收口，再做功能外扩
当平台主线已经可运行但关键扩展点、状态生命周期、结果合同仍未收口时，应优先进行结构修复与边界澄清，而不是继续横向铺开更多功能。

---

## 4. 新版阶段划分
本项目建议划分为 7 个阶段：

- Phase 1：平台骨架与基础闭环
- Phase 2：平台增强与工程化基础
- Phase 6A：基础产品化与生态雏形
- Phase 3：静力非线性与几何非线性
- Phase 4：动力学与振动增强
- Phase 5：接触、壳、高阶单元与更广覆盖
- Phase 6B：完整产品化与生态建设

---

# Phase 1：平台骨架与基础闭环

## 1. 阶段目标
建立 pyFEM v2 的正式主骨架，并完成第一批基础能力闭环。

核心目标不是单纯“把几个功能做出来”，而是让主架构真正成立，并支撑团队后续扩展。

当前阶段必须同时完成：

- 主线可运行
- 核心抽象落位
- 第一批基础能力闭环
- 第一轮关键结构收口

---

## 2. 核心交付

### 2.1 架构骨架
建立正式目录与分层，包括：

- foundation
- modeldb
- mesh
- compiler
- kernel
- procedures
- solver
- io
- post
- job
- plugins
- api
- gui
- tests

### 2.2 核心抽象
必须形成正式接口：

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

### 2.3 第一批分析能力
实现：

- 小变形
- 各向同性线弹性
- C3D8
- CPS4
- B21
- Static Linear
- Modal
- 基础 Implicit Dynamic

### 2.4 第一批结果能力
实现：

- ResultsWriter / ResultsReader 基础闭环
- U / RF / S / E / MODE_SHAPE 等输出
- VTK exporter
- 基础 field / history 输出

### 2.5 第一批测试与验证
建立：

- unit tests
- integration tests
- verification tests
- regression baseline 雏形

### 2.6 第一轮架构收口
必须完成以下关键结构收口任务：

- constraint provider 正式接入 Compiler
- interaction provider 正式接入 Compiler
- RuntimeState 生命周期第一版落地
- OutputRequest 执行语义第一版落地
- extra DOF 正式 owner 语义第一版落地
- regression baseline 初版建立

---

## 3. 阶段边界

### 3.1 本阶段应该完成的事
- 把 v2 主脊柱真正跑通
- 让 C3D8 / CPS4 / B21 通过新架构正式接入
- 让 Static Linear / Modal / basic Implicit Dynamic 形成最小闭环
- 让 ResultsWriter / ResultsReader 成为正式输出路径
- 让关键扩展点与状态生命周期开始进入正式主线

### 3.2 本阶段不应做成完整版的事
以下能力在 Phase 1 **不要求做成正式可用功能**，但必须预留正式落点与能力边界：

- 几何非线性
- 材料非线性
- 接触
- MPC / multiplier
- 复杂装配实例
- 工程级 ResultsDB
- 高性能求解 backend

### 3.3 本阶段明确不建议的做法
- 用临时 if/elif 旁路替代 registry / provider 主线
- 让 importer 越过 ModelDB / Compiler 直接驱动求解
- 让 GUI 直接依赖具体 solver / element 实现
- 把 extra DOF 长期伪装成节点 DOF
- 在 Results 合同尚未收口时继续堆更多输出选项
- 在 RuntimeState 未落地前抢跑非线性实现
- 在 JSON ResultsDB 上持续堆长期工程职责

---

## 4. 阶段完成标准
满足以下条件，才可判定 Phase 1 完成：

1. 目录骨架已稳定
2. 核心接口主轮廓已稳定，并完成第一轮结构收口
3. `ModelDB -> Compiler -> CompiledModel -> Procedure -> Solver -> ResultsDB` 主线可跑通
4. C3D8 / CPS4 / B21 已通过新架构正式接入
5. Static Linear / Modal / basic Implicit Dynamic 已形成最小闭环
6. ResultsWriter 可输出正式结果，ResultsReader 可读回基础结果
7. constraint / interaction provider 已进入 Compiler 主路径
8. RuntimeState 已具备第一版 `allocate -> trial -> commit -> rollback` 生命周期
9. OutputRequest 的基础 target / position / frequency 语义已进入正式执行路径
10. 至少存在一批基础 benchmark 和 regression 测试
11. 代码库已明显具备后续团队扩展能力

---

# Phase 2：平台增强与工程化基础

## 1. 阶段目标
把 v2 从“基础闭环”升级为“可持续扩展的平台内核”。

---

## 2. 核心任务

### 2.1 输入与建模增强
- 完善 INP importer
- 完善 region / set / surface / orientation 支持
- 完善 material / section / step 绑定逻辑
- 建立更清晰的模型校验体系
- PartInstance transform 语义第一版
- instance-level scope / set / surface 展开规则第一版

### 2.2 结果与后处理增强
- 补齐 OutputRequest 到 ResultsWriter 的正式合同
- 稳定 ResultsDB schema
- 完善节点平均应力与积分点结果恢复
- 统一模态、静力、动力学结果读取接口
- 提供 probe / history / field 查询能力

### 2.3 测试与验证体系增强
- 补充 patch tests
- 完善梁、平面、实体 benchmark
- 建立模态和动力学 regression baseline
- 建立自动回归流程

### 2.4 注册表与插件机制
- 完善 element registry
- 完善 material registry
- 完善 procedure registry
- importer / exporter registry 雏形
- constraint / interaction registry 完整化
- 插件 manifest 机制雏形

### 2.5 工程基础设施
- 日志体系
- 配置体系
- 错误处理体系
- schema version 管理
- CI 基础流程

### 2.6 结果与存储边界澄清
- 明确 JSON ResultsDB 的参考实现定位
- 为 append / partial read / multi-step / restart metadata 预留正式边界
- 明确 ResultsDatabase 与具体存储实现的职责分层

---

## 3. 阶段完成标准
满足以下条件，才可判定 Phase 2 完成：

1. 输入、编译、求解、结果主线稳定
2. 结果查询和读取能力明确
3. 注册表机制已形成
4. regression 测试开始真正起作用
5. 实例语义与基础装配边界已明确
6. 平台已从“能跑”升级为“能持续开发”

---

# Phase 6A：基础产品化与生态雏形

## 1. 阶段目标
在不绑死内核的前提下，提前建设基础产品层和生态外壳，方便团队协作、演示、测试和后续扩展。

这一阶段不是做完整商业 GUI，而是做“产品化基础设施”。

---

## 2. 核心任务

### 2.1 文档与项目外壳
- README
- 架构总览文档
- 路线图文档
- 开发规范文档
- benchmark 说明文档

### 2.2 Job 与执行外壳
- JobManager 雏形
- execution shell
- 基础 monitor / log 输出
- 标准化运行入口

### 2.3 API / Session 雏形
- session API 外壳
- 脚本调用主线
- 为后续参数化建模保留位置

### 2.4 Results 消费侧能力
- ResultsReader 第一版
- probe / query 接口雏形
- 基础 post API

### 2.5 最小 GUI 壳
只做最小能力：

- 打开模型
- 提交 job
- 读取结果
- 显示基础位移 / 应力结果入口

注意：

- 不做复杂建模界面
- 不做成熟商业级结果浏览器
- 不允许 GUI 反向控制内核实现细节

### 2.6 插件生态雏形
- registry 完善
- plugin manifest
- 插件发现机制第一版

---

## 3. 阶段边界
本阶段不应做：

- 复杂 GUI 建模工作流
- 接触专用可视化
- 壳 section point 高级后处理
- 振动 / 频响高级结果浏览器
- 完整用户插件 SDK 冻结

---

## 4. 阶段完成标准
满足以下条件，才可判定 Phase 6A 完成：

1. 项目已具备基础产品层外壳
2. Job / API / Reader / GUI 壳已形成
3. 文档体系基本成型
4. 插件生态已有雏形
5. 产品层仍然保持对内核的低耦合

---

# Phase 3：静力非线性与几何非线性

## 1. 阶段目标
为平台引入正式的非线性求解能力，并接入几何非线性框架。

---

## 2. 核心任务

### 2.1 静力非线性程序
- StaticNonlinearProcedure
- Newton-Raphson
- Modified Newton（可选）
- line search 基础支持
- cutback / increment control 基础支持
- commit / rollback 机制正式落地

### 2.2 材料非线性
建议从最典型模型开始：

- J2 plasticity
- 简单硬化
- 一致切线接口
- 状态变量管理

### 2.3 几何非线性
建议逐步引入：

- corotational beam
- TL / UL solid
- 初始应力刚度 / 几何刚度
- follower load 预留

### 2.4 非线性验证
- 大挠度梁
- 塑性 benchmark
- 几何非线性实体 benchmark
- 收敛性与鲁棒性回归

---

## 3. 阶段完成标准
满足以下条件，才可判定 Phase 3 完成：

1. 平台正式具备静力非线性程序框架
2. 材料状态变量机制经受实际模型验证
3. 几何非线性接口已真正接入主架构
4. 非线性 benchmark 形成稳定回归集合

---

# Phase 4：动力学与振动增强

## 1. 阶段目标
把已有基础动力学 / 模态能力升级为更完整的结构动力学与振动分析平台。

---

## 2. 核心任务

### 2.1 隐式动力学增强
- 完善 Newmark / generalized-alpha
- Rayleigh damping
- 时程控制与 history 输出
- 能量输出
- 更完善的约束处理

### 2.2 模态与振动增强
- 模态提取增强
- 模态后处理完善
- 频响 / 谐响应
- 模态叠加法
- 阻尼模型扩展

### 2.3 显式动力学（建议后置）
- central difference
- 集总质量
- 稳定时间步估计
- 显式结果输出接口
- 与接触能力的接口预留

### 2.4 动力学验证
- 振动 benchmark
- 瞬态动力学 benchmark
- 模态验证
- 阻尼模型验证

---

## 3. 阶段完成标准
满足以下条件，才可判定 Phase 4 完成：

1. 隐式动力学稳定可用
2. 模态 / 振动能力明显增强
3. 动力学输出和后处理接口成熟
4. 显式动力学至少具备清晰架构位置

---

# Phase 5：接触、壳、高阶单元与更广覆盖

## 1. 阶段目标
把平台从“核心内核”扩展到更广泛工程场景。

---

## 2. 核心任务

### 2.1 壳单元
建议优先：

- S4 / S4R 路线
- thickness integration
- section point outputs
- shell 后处理

### 2.2 接触
建议顺序：

- tie
- frictionless contact
- penalty formulation
- surface-to-surface
- 后续再扩展摩擦、拉格朗日乘子等

### 2.3 更多单元族
- C3D20
- C3D8R
- CPS8
- B31
- 连接器 / 弹簧 / 阻尼元

### 2.4 约束与刚体增强
- rigid body
- coupling
- MPC
- connector interactions

### 2.5 广覆盖验证
- 壳 benchmark
- 接触 benchmark
- 高阶单元 benchmark
- 复杂工程组合测试

---

## 3. 阶段完成标准
满足以下条件，才可判定 Phase 5 完成：

1. 平台覆盖更多工程常见单元族
2. 基础接触能力成型
3. 壳单元正式进入可用状态
4. 工程建模覆盖面明显扩大

---

# Phase 6B：完整产品化与生态建设

## 1. 阶段目标
在前面各类物理能力较成熟后，完成真正完整的产品层建设。

---

## 2. 核心任务

### 2.1 完整 GUI 工作流
- 模型树
- 结果浏览
- history / probe / contour view
- 更成熟的可视化与交互

### 2.2 高级结果消费层
- 动力学与振动专用结果浏览
- 接触状态可视化
- 壳 section point 结果浏览
- 更高级的 plot / filter / cut / compare

### 2.3 Job 系统增强
- 本地 job 管理增强
- restart / resume
- 批处理与并行作业支持
- 更成熟的监控与日志系统

### 2.4 API 与脚本生态增强
- 更成熟的 session API
- 参数化建模接口
- 自动化流程编排

### 2.5 插件生态正式化
- 插件 SDK
- 用户材料 / 用户单元扩展边界
- 插件版本兼容与文档

### 2.6 文档与发布
- 开发者文档
- 用户文档
- benchmark 报告
- 发布流程
- 版本管理与 changelog

---

## 3. 阶段完成标准
满足以下条件，才可判定 Phase 6B 完成：

1. GUI、Job、API、ResultsDB 已形成完整产品闭环
2. 高级结果浏览能力成熟
3. 插件系统具备正式扩展能力
4. 文档体系和发布体系形成
5. 项目具备“产品级”基础

---

# 5. 推荐实施顺序（总结版）

## 建议主顺序
1. Phase 1
2. Phase 2
3. Phase 6A
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6B

---

## 为什么这样排
- Phase 1 / 2 先把平台骨架、关键扩展点与工程基础打牢
- 6A 提前建设基础产品层，让团队协作、演示、测试更高效
- 再进入非线性、动力学、接触、壳与高阶
- 最后做完整产品化，避免 GUI 和产品层因物理能力演进反复重构

---

## 不建议的做法
- 在 Phase 1 尚未稳定前同时大规模铺开接触、壳、显式动力学、完整 GUI
- 在 DofManager、Compiler、RuntimeState、Results 合同未稳前就追求复杂产品层
- 让 GUI 过早绑定当前有限能力，导致后面动力学 / 接触 / 壳接入时大量返工
- 在 JSON ResultsDB、dense backend、伪节点 extra dof 等临时方案上过早固化长期标准

---

# 6. 里程碑建议

## M1
v2 骨架 + 核心接口主形态 + Compiler 主线

## M2
C3D8 / CPS4 / B21 + Static Linear

## M3
Modal + basic Implicit Dynamic + ResultsWriter / ResultsReader / VTK

## M3.5
Compiler 扩展点收口 + RuntimeState 第一版 + OutputRequest 合同第一版 + regression baseline 初版

## M4
Verification / regression / registry / engineering infrastructure

## M5
基础产品层外壳（6A）

## M6
Static Nonlinear + material nonlinearity basics

## M7
Geometric nonlinearity

## M8
动力学与振动增强

## M9
壳 / 接触 / 高阶单元

## M10
完整产品化与生态建设（6B）

---

# 7. 最终说明
本路线图的核心思想不是“堆功能”，而是：

> **先让 pyFEM v2 成为一个真正的平台，再让功能和产品层以受控方式生长。**

其中，基础产品化可以提前，但完整产品化必须建立在较成熟的内核、状态管理与结果体系之上。

Phase 1 的成功标准不只是“已经能跑出几个算例”，而是：

> **主线可运行，关键结构已收口，未来能力已有正式落点，后续扩展不需要推翻主架构。**
