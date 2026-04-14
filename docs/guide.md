# pyFEM v2 接手文档（精简强化版）

> 适用对象：从零开始接手 pyFEM v2、语法和架构理解都还不稳的新成员。  
> 目标：在 **14 天** 内，不是“看过一遍”，而是做到：  
> 1. 能讲清主架构；  
> 2. 能沿一条正式主线从输入追到结果；  
> 3. 能做小改动并判断影响范围；  
> 4. 能初步判断别人有没有把架构边界改坏。
>
> 本文档服务于接手与 onboarding，不作为当前架构现状的唯一真源。
> 当前阶段判断与正式边界，请优先以 `README.md`、`docs/Architecture_Overview.md`、`docs/Roadmap_v1.2.md` 为准。

---

## 1. 架构

### 1.1 主脊柱

pyFEM v2 当前最重要的不是“已经支持多少物理能力”，而是主脊柱已经明确：

```text
输入 / 脚本 / GUI
    -> ModelDB
    -> Compiler
    -> CompiledModel
    -> ProcedureRuntime
    -> ResultsWriter / ResultsReader
    -> Query / Probe / Facade / GUI
```

理解项目时，必须始终按这条主线看，而不是把 importer、GUI、单元实现、结果浏览器混在一起看。

### 1.2 各层职责

#### 输入层
负责把“外部世界”送进系统主线。

典型入口：
- `run_case.py`
- `PyFEMSession`
- GUI 壳层

这一层的职责不是计算，而是：
- 接收输入路径或现成模型
- 选择 importer / results backend / exporter
- 调度作业执行
- 打开结果进行后处理消费

#### ModelDB 层
负责表达“问题定义”。

这里保存的是：
- mesh / node / element / part / assembly
- material / section
- boundary / nodal load / distributed load / interaction
- output request
- step / job

这一层只描述“要解什么问题”，不负责数值求解。

#### Compiler 层
负责把定义世界编译成运行时世界。

这一层做的事是：
- 读取 `ModelDB`
- 通过 `registry + provider` 找到各类运行时构造逻辑
- 构造 material / section / element / constraint / interaction / procedure runtime
- 生成 `CompiledModel`

这一层不是 solver，但它决定了：
- 哪些类型当前正式支持
- 各类对象之间怎样连接
- 运行时对象图是不是完整

#### CompiledModel 层
负责持有编译后的正式运行时对象图。

它收口的是：
- `dof_manager`
- `material_runtimes`
- `section_runtimes`
- `element_runtimes`
- `constraint_runtimes`
- `interaction_runtimes`
- `step_runtimes`

也就是说：
**ModelDB 是“问题定义仓库”，CompiledModel 是“可运行对象仓库”。**

#### ProcedureRuntime 层
负责真正执行一个 step。

比如静力、模态、隐式动力学这些 procedure，都会在这一层实现自己的：
- 组装
- 施加约束
- 求解
- 写出结果

这层才是真正把编译后的运行时对象用起来的地方。

#### Results 层
负责正式结果的生产与消费。

生产端：
- `ResultsWriter`

消费端：
- `ResultsReader`
- `ResultsQueryService`
- `ResultsProbeService`
- `ResultsFacade`

这一层的重要原则是：
**后处理不应该直接扒求解器内部变量，而应该通过正式结果合同消费。**

#### GUI / API / 壳层
负责把正式主线包装成可调用产品入口。

这一层当前已经能：
- 载入模型
- 提交作业
- 打开结果
- 导出 VTK

但它目前仍是“最小可用壳层”，不是成熟商用前处理器。

### 1.3 当前必须牢记的架构判断

1. `ModelDB` 不是 solver 输入字典，而是正式定义层。  
2. `StepDef` 不是 `ProcedureRuntime` 本体，二者之间必须经过编译。  
3. `GUI` 不应该直接 new 求解对象。  
4. importer 不应该跳过 `ModelDB/Compiler` 直接驱动 solver。  
5. 结果层必须通过 writer/reader/query/probe/facade 正式流动。  
6. 当前项目的真正强项是“架构主线正确”，不是“物理能力已经很广”。

---

## 2. 当前正式支持范围

下面这部分只写“当前代码里能明确确认的正式支持范围”，不写想象中的未来能力。

### 2.1 当前正式支持的分析类型

已正式注册并接入主线：
- `static`
- `static_linear`
- `modal`
- `implicit_dynamic`
- `dynamic`

其中：
- 你应该把 `static_linear` 当作第一学习主线；
- `modal` 和 `implicit_dynamic` 目前是已接通的正式 procedure；
- 但“接通”不等于“已经是工程级成熟能力”。

### 2.2 当前正式支持的材料模型

已正式支持：
- `linear_elastic`
- `elastic_isotropic`

也就是说，当前正式主线是：
- 小变形
- 各向同性线弹性

### 2.3 当前正式支持的截面类型

已正式支持：
- `solid`
- `plane_stress`
- `plane_strain`
- `beam`

### 2.4 当前正式支持的单元类型

已正式支持：
- `C3D8`
- `CPS4`
- `B21`

理解上可以先对应成：
- `C3D8`：小变形八节点实体单元
- `CPS4`：小变形四节点平面单元
- `B21`：二维梁单元

### 2.5 当前正式支持的约束与载荷主线

当前明确正式接通的主线：
- 位移边界条件（`displacement`）
- 节点集中载荷
- 一部分分布载荷 / 表面压力主线

这里必须注意：
- 这不等于“所有边界/载荷都成熟支持”；
- 当前更接近“基础主线已通”，不是“全量工程载荷系统”。

### 2.6 当前正式支持的输入 / 输出主线

当前正式接通：
- `inp` importer
- `json` results writer / reader
- `vtk` exporter

也就是说，当前最稳的产品路径是：

```text
INP -> ModelDB -> Compiler -> Procedure -> JSON Results -> Query/Probe/Facade -> VTK
```

### 2.7 当前明确不应当算作“正式已支持”的能力

下面这些，当前不要当成“已经能正式拿来用”的能力：

- 材料非线性
- 几何非线性 / 大变形
- 真实接触
- 壳单元
- 高阶单元
- 丰富约束系统（如成熟 MPC / multiplier 正式主线）
- 完整工程阻尼体系
- 完整图形化前处理 GUI
- 完整 Abaqus 兼容

### 2.8 一句话总结

当前项目最适合做的是：
- 基础线弹性
- 小规模静力 / 模态 / 最小隐式动力学验证
- importer / compiler / results 主线验证
- 平台架构与结果合同验证

当前项目最不适合做的是：
- 非线性
- 接触
- 壳 / 高阶复杂单元问题
- 完整商用 GUI 前处理演示
- 工程级复杂动力学分析

---

## 3. 阅读顺序

### 3.1 总原则

阅读顺序一定要遵守下面这条原则：

**先主线，后细节；先定义，后实现；先静力，后扩展；先 results，后 GUI。**

绝对不要：
- 一上来逐行审全部源码；
- 一上来先啃 GUI；
- 一上来先啃 importer；
- 一上来先钻单元公式细节。

### 3.2 正确顺序

#### 第 1 批：产品主入口
先看：
- `run_case.py`
- `src/pyfem/api/session.py`

目标：搞清“项目怎么跑起来”。

#### 第 2 批：最小模型构造
再看：
- 手工构模测试
- `tests/support/model_builders.py`
- 各类最小静力/模态/动态模型搭建测试

目标：搞清“ModelDB 眼里的问题定义到底长什么样”。

#### 第 3 批：注册面
再看：
- `builtin_providers.py`
- `builtin_procedure_providers.py`
- 相关 registry 暴露位置

目标：搞清“当前正式支持什么”。

#### 第 4 批：编译主线
再看：
- `compiler.py`
- `compiled_model.py`

目标：搞清“为什么要编译，编译前后分别是什么”。

#### 第 5 批：静力主线
再看：
- `procedures/base.py`
- `procedures/static_linear.py`

目标：搞清“一个正式 step 到底怎么执行”。

#### 第 6 批：结果消费主线
再看：
- `ResultsReader`
- `ResultsQueryService`
- `ResultsProbeService`
- `ResultsFacade`
- 相关测试

目标：搞清“结果怎么被正式消费”。

#### 第 7 批：横向扩展
再看：
- `modal`
- `implicit_dynamic`
- 多步执行测试

目标：搞清“同一套主骨架是如何支撑不同 procedure 的”。

#### 第 8 批：最后再看 importer / GUI
只有当前面都顺了，才开始看：
- importer 翻译细节
- GUI 壳层
- 线程 / dock / viewport / results browser

### 3.3 你现在最不该先读的东西

1. GUI 线程与界面细节  
2. importer 关键字翻译细节  
3. 全部单元公式  
4. 所有测试一次性通读  
5. placeholder 和各种 fallback 细枝末节

这些不是不重要，而是现在不该作为第一入口。

---

## 4. 14 天接手计划（强化详细版）

> 目标：14 天后，你应该能独立完成：  
> - 讲清主架构；  
> - 跟踪静力主线；  
> - 做小改动；  
> - 判断一个改动有没有越过架构边界。  
>
> 每天建议投入：2.5~4 小时。  
> 每天都必须留下输出物，不允许“只看不写”。

### 第 1 天：建立最外层主线地图

#### 今天看什么
- `run_case.py`
- `src/pyfem/api/session.py`

#### 今天必须搞懂什么
1. `run_case.py` 是如何拿输入路径、创建 `JobManager`、调用 `run_input_file()` 的。  
2. `PyFEMSession` 为什么是正式平台入口。  
3. `load_model_from_file / run_input_file / run_model / open_results / export_results` 这 5 条接口分别干什么。  
4. “求解入口”和“结果入口”为什么被分成不同方法。

#### 今天必须产出的笔记
写一张“外层主线图”：

```text
input_path
 -> importer/load
 -> ModelDB
 -> compile
 -> run step
 -> write results
 -> open results
 -> export
```

#### 今天必须动手做的事
- 不改代码，只做函数调用链追踪。  
- 把 `run_case.py` 每个函数调用的职责写成中文一句话。

#### 今天的验收标准
- 不看源码，你能口头讲清“一次最小求解是怎么从输入走到结果的”。

---

### 第 2 天：吃透最小模型定义

#### 今天看什么
- 最小梁模型相关测试
- 手工构模工具函数
- `ModelDB` 相关定义对象出现的位置

#### 今天必须搞懂什么
1. 一个最小模型最少需要哪些定义对象。  
2. `Mesh / Part / MaterialDef / SectionDef / BoundaryDef / OutputRequest / StepDef / JobDef` 的职责。  
3. `StepDef` 和 `JobDef` 的区别。  
4. 为什么当前项目强调“先定义问题，再求解问题”。

#### 今天必须产出的笔记
写一份“最小模型词典”，至少包含：
- 每个 Def 对象是什么
- 它属于哪一层
- 它和谁有依赖

#### 今天必须动手做的事
- 手抄一个最小梁模型的对象清单；  
- 不要求运行，但必须能把模型结构完整写出来。

#### 今天的验收标准
- 你能自己写出一个“最小线弹性梁模型”需要哪些定义对象。

---

### 第 3 天：分清定义世界与运行时世界

#### 今天看什么
- `compiled_model.py`
- provider 注册面
- 任何 `Compiler().compile(model)` 被调用的位置

#### 今天必须搞懂什么
1. `ModelDB` 和 `CompiledModel` 的根本区别。  
2. 为什么不能直接 `solve(ModelDB)`。  
3. `Def -> Runtime` 的转换是项目最核心的一步。  
4. 当前系统里哪些对象属于定义层，哪些属于运行时层。

#### 今天必须产出的笔记
写一张两列表：

| 定义层 | 运行时层 |
|---|---|
| MaterialDef | MaterialRuntime |
| SectionDef | SectionRuntime |
| StepDef | ProcedureRuntime |
| ModelDB | CompiledModel |

尽量继续补全 element / constraint / interaction。

#### 今天必须动手做的事
- 自己写 10 句中文，解释“为什么这个项目必须要有 Compiler”。

#### 今天的验收标准
- 你能解释清楚 Def 和 Runtime 分开的工程价值。

---

### 第 4 天：梳理当前正式支持范围

#### 今天看什么
- `builtin_providers.py`
- `builtin_procedure_providers.py`
- IO 注册相关入口

#### 今天必须搞懂什么
1. 当前正式支持哪些 procedure。  
2. 当前正式支持哪些材料、截面、单元。  
3. 当前哪些能力只是扩展坑位，不是完成能力。  
4. 为什么“注册面”是判断支持范围的第一依据。

#### 今天必须产出的笔记
写一张“当前正式支持矩阵”：
- procedure
- material
- section
- element
- constraint
- interaction
- importer/exporter/results backend

#### 今天必须动手做的事
- 手写一份“当前不要误判为已支持的能力清单”。

#### 今天的验收标准
- 别人问你“现在到底能算什么”，你能不含糊地回答。

---

### 第 5 天：正式吃透静力主线（第一遍）

#### 今天看什么
- `procedures/base.py`
- `procedures/static_linear.py`

#### 今天必须搞懂什么
1. `ProcedureRuntime.run(...)` 在接口层是什么意思。  
2. 静力步真正执行时的大顺序。  
3. `U`、`RF`、summary、history 是在哪个阶段被写出的。  
4. 为什么 static 是你最应该先吃透的 procedure。

#### 今天必须产出的笔记
把静力步压成“8 步流程卡”：
1. 开 session / frame
2. 进入试算态
3. 组装切线
4. 组装外载
5. 施加约束
6. 解线性方程
7. 写 frame 结果
8. 写 summary/history

#### 今天必须动手做的事
- 画静力 step 的时序图。  
- 每一步标出“输入是什么，输出是什么”。

#### 今天的验收标准
- 你能不用代码，把一个静力 step 跑完的顺序讲给别人听。

---

### 第 6 天：静力主线（第二遍）——把脚本入口和 procedure 对上

#### 今天看什么
- `run_case.py`
- 对应的集成测试
- 与静力结果检查相关的测试

#### 今天必须搞懂什么
1. `run_case.py` 和静力 procedure 之间是怎么接上的。  
2. 为什么 `run_case.py` 不是“直接调用 solver”，而是走 `JobManager` 壳层。  
3. 结果文件、VTK、report 为什么都属于正式产物。  
4. 测试为什么要核对位移值，而不是只看程序不崩。

#### 今天必须产出的笔记
写一页“脚本入口 -> 作业执行 -> 结果产物”对应表。

#### 今天必须动手做的事
- 找一个最小算例，手工列出：输入文件、step 名、结果文件、导出文件、关键输出值。

#### 今天的验收标准
- 你能说清脚本运行路径为什么是产品化入口，而不是临时 demo。

---

### 第 7 天：结果层第一遍——只学结果怎么被消费

#### 今天看什么
- 结果 query / probe 相关测试
- `open_results()` 相关调用
- Facade 暴露接口

#### 今天必须搞懂什么
1. 为什么 `open_results()` 返回的是 facade。  
2. query 和 probe 在角色上有什么区别。  
3. 为什么结果消费必须走 reader-only 路径。  
4. step / frame / field / history / summary 分别是什么。

#### 今天必须产出的笔记
写一份“结果对象词典”：
- step
- frame
- field
- history
- summary
- query
- probe
- facade

#### 今天必须动手做的事
- 自己写一段伪代码：跑完静力后，如何打开结果、列 step、查位移分量、读 history。

#### 今天的验收标准
- 你能说清后处理为什么不该直接读求解器内部变量。

---

### 第 8 天：做第一次安全改动

#### 今天看什么
- 最小梁模型构造测试
- 静力 benchmark 测试
- 输出请求相关构造位置

#### 今天必须搞懂什么
1. 哪些改动是“定义层安全改动”。  
2. 哪些改动会穿透到编译、procedure、结果。  
3. 为什么新手只能先改参数，不能先改架构。

#### 今天必须产出的笔记
写一张“安全改动清单”：
- 可改：材料参数、载荷大小、输出请求
- 暂不改：编译主线、provider 接口、results 合同、GUI 线程逻辑

#### 今天必须动手做的事
三选一，只做一个：
- 调整 `young_modulus`
- 调整节点载荷
- 多加一个输出请求

并写出：
- 改动前预期
- 改动后实际
- 不一致时先查哪一层

#### 今天的验收标准
- 你能明确说出“我改的是定义层，不是运行时骨架”。

---

### 第 9 天：进入 provider 体系

#### 今天看什么
- `builtin_providers.py`
- `builtin_procedure_providers.py`
- registry 相关暴露与创建入口

#### 今天必须搞懂什么
1. provider 到底在 build 什么。  
2. request 对象为什么存在。  
3. 新增 element/material/procedure 为什么应该通过 provider 接入。  
4. 为什么 provider 是项目扩展秩序的关键。

#### 今天必须产出的笔记
写一张 “type key -> provider -> runtime” 映射表。

#### 今天必须动手做的事
- 任选一个 provider，写 10 句中文解释它的 build 过程。  
- 说明它依赖的上游对象和下游对象是什么。

#### 今天的验收标准
- 你能回答“如果以后加一个新单元，应该插在哪一层”。

---

### 第 10 天：正式读编译主线

#### 今天看什么
- `compiler.py`
- `compiled_model.py`
- 与 compile 调用相关的测试

#### 今天必须搞懂什么
1. 编译顺序为什么不能乱。  
2. section 为什么依赖 material。  
3. element 为什么依赖 section/material/dof。  
4. step runtime 是如何建立并挂进 `CompiledModel` 的。  
5. placeholder / fallback 出现的位置意味着什么。

#### 今天必须产出的笔记
画一张“编译时序图”，至少包含：
- validate
- build material
- build section
- build element
- build constraint
- build interaction
- build procedure
- assemble `CompiledModel`

#### 今天必须动手做的事
- 选一条 element build 路径，自己讲一遍“它是怎么从 element record 变成 element runtime 的”。

#### 今天的验收标准
- 你能说清“为什么 Compiler 不是可有可无的中间层”。

---

### 第 11 天：理解运行时状态与正式 procedure 的关系

#### 今天看什么
- state / problem / 相关测试
- procedure 与 state 交汇的位置

#### 今天必须搞懂什么
1. 为什么项目不满足于“一次线性求解就结束”。  
2. 为什么需要 runtime state。  
3. `trial / commit / rollback` 是为未来什么能力准备的。  
4. 为什么状态层存在即使当前主要能力还是基础主线。

#### 今天必须产出的笔记
写一页“状态层存在的理由”，重点写：
- 对静力的意义
- 对动力学的意义
- 对未来非线性的意义

#### 今天必须动手做的事
- 把“定义层 -> 编译层 -> procedure 层 -> state 层 -> results 层”用一句话串起来。

#### 今天的验收标准
- 你能回答“为什么这个项目提前有状态层，而不是以后再说”。

---

### 第 12 天：横向比较 static / modal / dynamic

#### 今天看什么
- `static_linear`
- `modal`
- `implicit_dynamic`
- 多步测试 / 动态结果测试

#### 今天必须搞懂什么
1. 三种 procedure 的共同骨架是什么。  
2. 三种 procedure 的输入参数差异。  
3. 三种 procedure 的输出结果差异。  
4. 为什么 StepDef 不能直接等于某个具体 Procedure 类。

#### 今天必须产出的笔记
写一张三列表：

| procedure | 关键输入 | 关键输出 |
|---|---|---|
| static_linear | ... | ... |
| modal | ... | ... |
| implicit_dynamic | ... | ... |

#### 今天必须动手做的事
- 自己写一段 15 句以内的总结，解释“同一个项目如何支撑多种分析步而不把接口拆烂”。

#### 今天的验收标准
- 你能解释 static、modal、dynamic 的共性和边界。

---

### 第 13 天：第一次做结构审计

#### 今天看什么
只挑一条完整主线，不再铺新文件：
- 推荐：`run_case.py -> session/job -> compile -> static -> results -> query/probe`

#### 今天必须搞懂什么
1. 这条主线每一层入口在哪里。  
2. 最容易被误改的边界在哪里。  
3. 哪些改动会造成“表面上能跑，实则把骨架搞坏”。

#### 今天必须产出的笔记
写一页“主线风险点”，至少列出 5 条：
- 不要绕过 ModelDB
- 不要绕过 Compiler
- 不要把 GUI 直接绑到 solver
- 不要让 results 消费直接扒内部变量
- 不要让 provider 注册面和实际支持范围失真

#### 今天必须动手做的事
- 选一个你认为“最不能乱改”的接口，写出原因。

#### 今天的验收标准
- 你已经开始从“读代码的人”转成“能审结构的人”。

---

### 第 14 天：做正式接手总结

#### 今天看什么
回看前 13 天的所有产出，不新增大量新内容。

#### 今天必须产出的正式文档
你要自己再写一份“接手总结”，至少包含：

1. 项目主架构图  
2. 当前正式支持范围  
3. 最稳的主线是什么  
4. 当前最适合作为学习入口的文件  
5. 你已经掌握的内容  
6. 你还没掌握但已定位的问题  
7. 接下来两周应该继续啃哪些模块

#### 今天必须动手做的事
- 把前 14 天所有笔记整理成你自己的 `docs/接手总结.md`。  
- 不要求完美，但必须让别的新人也能拿来用。

#### 今天的验收标准
达到下面 4 条，就算这 14 天真正有效：
- 能讲清主架构  
- 能讲清静力主线  
- 能做小改动  
- 能指出关键架构边界不能怎么乱改

---

## 5. 安全改动规则

这一部分非常重要。新接手阶段，**允许你改的东西很少**。

### 5.1 先改什么

接手初期，优先只做这几类改动：

1. 材料参数改动  
2. 截面参数改动  
3. 载荷大小改动  
4. 边界条件参数改动  
5. 输出请求改动  
6. 测试里的最小模型参数改动

这些改动的特点是：
- 它们主要发生在定义层；
- 不会立刻打穿主骨架；
- 出问题时更容易定位。

### 5.2 暂时不要改什么

接手初期，先不要动：

1. `Compiler` 主顺序  
2. provider 接口形状  
3. `CompiledModel` 主结构  
4. ProcedureRuntime 公共接口  
5. ResultsReader / ResultsWriter / Query / Probe 合同  
6. GUI 线程和 worker 主线  
7. importer 主翻译骨架

这些地方一旦乱动，很容易造成：
- 主线还勉强能跑，但架构已经歪了；
- 某些测试过了，但长期扩展能力被破坏；
- 你自己很难判断后果到底波及多少层。

### 5.3 每次改动前必须先回答的 4 个问题

每次动手前，先写下这 4 个问题的答案：

1. 我改的是哪一层？  
2. 这层的上游是谁？  
3. 这层的下游是谁？  
4. 这个改动会不会破坏正式合同？

如果这 4 个问题答不出来，就先别改。

### 5.4 每次改动后必须检查的 5 件事

1. 最小主线测试有没有受影响  
2. 结果字段/结果文件有没有变化  
3. 现有 procedure 行为有没有被误伤  
4. 是否引入了“绕过架构边界”的捷径  
5. 你的改动是不是只解决了眼前问题，但埋了长期坑

### 5.5 新人阶段的铁律

**宁可先多写一点测试和笔记，也不要为了“快点跑通”去跨层硬连。**

对于这个项目来说，最危险的不是“能力还不够多”，而是：
**在补能力的时候把主骨架补歪。**

---

## 6. 接手标准

下面这部分不是“理想状态”，而是你是否真正开始接住项目的判断标准。

### 6.1 第一层标准：会跑

满足以下条件：
- 你知道项目的正式入口在哪里；
- 你知道怎么从输入跑到结果；
- 你知道结果怎么再被打开与消费。

如果只达到这一层，你只是“会用项目”，还不算真正接手。

### 6.2 第二层标准：会解释

满足以下条件：
- 你能解释 `ModelDB` 是什么；
- 你能解释为什么要有 `Compiler`；
- 你能解释 `Def` 和 `Runtime` 的区别；
- 你能解释 static、modal、dynamic 为什么共用一套骨架但不能混成一类对象；
- 你能解释结果为什么必须走正式合同。

达到这一层，才算开始真正理解项目。

### 6.3 第三层标准：会改

满足以下条件：
- 你能做安全参数改动；
- 你能预测改动会影响哪一层；
- 你能在改坏时知道优先查哪里；
- 你不会一上来就跨层乱连。

达到这一层，才算开始具备维护能力。

### 6.4 第四层标准：会审

满足以下条件：
- 别人提交一个改动时，你能判断它是在“补能力”还是在“破坏边界”；
- 你能指出哪些接口不能乱改；
- 你能区分“代码啰嗦”和“架构必须有中间层”；
- 你能发现“表面上跑通了，但主线已经被绕开”的危险改动。

达到这一层，才算开始真正能接手项目。

### 6.5 14 天后的最低合格线

14 天后，如果你能做到下面这 6 条，就算这轮接手训练是合格的：

1. 能画出项目主架构图  
2. 能口述静力主线  
3. 能列出当前正式支持范围  
4. 能解释 Def / Runtime / Compiler 的关系  
5. 能做一个小改动并判断影响范围  
6. 能指出至少 5 条“不能乱改的边界”

如果还达不到这 6 条，不要急着去改 GUI、改 importer、加单元、加 procedure，先继续补主线理解。

---

## 最后一句

这 14 天的目标，不是把 pyFEM v2 “全部学完”。  
而是把你从“看到代码就乱”拉到“脑子里有地图，知道先看哪、改哪、不能碰哪”。

对这个项目来说，真正的接手不是会背多少类名，  
而是你能不能守住这条主线：

```text
定义层 -> 编译层 -> 运行层 -> 结果层 -> 壳层
```

只要这条主线在你脑子里稳了，后面的语法、细节、GUI、单元公式，都能慢慢补。
