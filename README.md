# pyFEM v2

## 简介
`pyFEM v2` 是一个面向结构力学的有限元平台内核项目。

这个仓库当前关注的重点，是把平台主线、模块边界、结果流转和测试门禁先整理清楚，再在这个基础上继续扩展更多单元、材料、分析程序、GUI 和插件能力。它不是一次性的算例脚本，也不是只为了少量单元快速拼起来的教学 demo，而是希望把后续长期演进需要的基础骨架先搭稳。

目前仓库已经形成的正式数据流为：

`Importer / API / GUI Shell -> ModelDB -> Compiler -> CompiledModel -> Procedure -> Solver -> ResultsWriter / ResultsReader / ResultsDB -> Post / Export`

这条主线的意义在于：模型定义、运行时对象、求解执行、结果写出和结果消费彼此分层，不靠旁路脚本临时串起来。后续无论扩展更多分析能力，还是接入 GUI、脚本接口、插件，都应该沿着这条正式链路走，而不是绕开它。

---

## 当前阶段
当前仓库处于 `Phase 6A：基础产品化与生态雏形`。

这里说的“Phase 6A”，强调的是架构和平台形态已经进入“向外收口”的阶段：不仅要能算，还要逐步把已有能力整理成稳定、清晰、可复用、可测试、可接入的标准入口。它并不表示项目已经具备成熟商业软件的完整功能，而是表示核心主线、产品壳层和扩展面正在成型。

当前阶段主要在做这些事情：

- 统一标准化作业执行入口
- 提供更适合脚本调用的 API Session
- 建立只读结果消费入口
- 形成最小但可用的 GUI 工作台壳
- 落地插件发现与注册第一版
- 用测试门禁保护架构边界不被回退

---

## 当前已经具备的能力

### 1. 求解主线
目前仓库已经具备一条完整的正式求解主线：

- `ModelDB -> Compiler -> Procedure -> Results`

这意味着当前代码不再是 importer 直接喂 solver、solver 直接吐裸数组、外层再手工拼接后处理的模式，而是已经有明确的分层入口和结果流转合同。

### 2. 当前已有的分析程序
目前已接入的分析程序包括：

- `static_linear`
- `modal`
- `implicit_dynamic`

这些 procedure 由正式 provider 构建，并通过统一 registry 注册，而不是在外层脚本里硬编码分支。

### 3. 当前已有的单元类型
目前仓库内已经接入的单元类型包括：

- `C3D8`
- `CPS4`
- `B21`

它们通过正式 element runtime provider 挂到统一注册表中，由编译阶段负责从定义对象绑定到运行时对象。

### 4. 模型与编译侧
当前模型与编译链路已经具备以下基础能力：

- `ModelDB` 作为问题定义唯一来源
- `Compiler` 负责从定义世界进入 runtime 世界
- `DofManager` 统一负责全局自由度编号
- 实例、作用域、transform 已有第一版
- `RuntimeRegistry` 已建立为统一扩展入口

### 5. 结果侧
当前结果侧已经有第一版正式合同和消费接口，包括：

- 多步结果路径第一版
- `ResultsSession -> ResultStep -> ResultFrame / ResultField + ResultHistorySeries + ResultSummary`
- 标准 `ResultsWriter / ResultsReader`
- `VTK` 导出路径
- 只读结果消费入口 `ResultsFacade`
- `ResultsQueryService`
- `ResultsProbeService`

结果消费侧强调 reader-only 边界，也就是说，后处理和 GUI 尽量通过正式 reader 接口读结果，而不是反向依赖 solver 运行期内部数组，或直接手工读某个 JSON 结构。

### 6. 产品壳层
当前仓库已经有一套最小产品壳层，主要包括：

- 标准作业执行入口：`JobManager`
- 脚本入口：`PyFEMSession`
- 结果消费入口：`ResultsFacade`
- GUI 壳入口：`GuiShell`
- 插件发现入口：`PluginDiscoveryService`

这些壳层的作用，是把核心内核能力整理成更稳定的外部接入面，避免 GUI、脚本和其他调用方直接深入到 solver、element 或 backend 内部。

### 7. GUI 现状
当前 GUI 还不是完整建模器，也不是商业级结果浏览器，但已经不只是一个“空壳”。

仓库里已经有：

- 主窗口工作台
- 导航树快照消费对象
- 结果浏览与视图共享上下文
- 中央视图区
- 探针、图例、结果导出等基础后处理交互能力
- `run_gui.py` 启动入口
- `pyfem-gui` 命令行入口

因此更准确的说法是：当前 GUI 已经是一套最小可用的工作台壳，可以承担主线演示、结果查看和基础后处理交互，但还不是成熟建模环境。

---

## 当前明确还不包含的内容
下面这些方向当前还没有正式落地，或者还处于很早期阶段：

- 几何非线性真实算法
- 材料非线性真实算法
- 接触真实算法
- 工程级 `ResultsDB` 后端
- 成熟的 GUI 建模器
- 商业级结果浏览器
- 完整插件 SDK
- 插件市场和动态安装体系
- 作业调度平台
- 分布式执行与并行作业系统

写清楚这一点很重要。这样能避免初次进入仓库的人把“架构已经有扩展位”和“这些能力已经工程化完成”混为一谈。

---

## 后续扩展方向
虽然很多能力还没完全落地，但当前架构已经为这些方向预留了正式接入口：

- 更多单元 runtime
- 更多材料 runtime
- 更多截面 runtime
- 更多约束与相互作用 runtime
- 更多 procedure 类型
- 更完整的 `ResultsDB / restart` 能力
- 更成熟的 GUI 与脚本接口
- 插件化扩展与产品壳层接入
- 与外部工具、业务系统或作业平台的集成

所以当前阶段的重点不是把功能列表尽量拉长，而是保证之后继续扩的时候，不会破坏已有主线和边界。

---

## 核心架构主线
可以把当前 pyFEM v2 的正式主线理解成下面这条链路：

### Importer / API / GUI Shell
这一层是输入入口和外部壳层。

- `Importer` 负责把输入文件转成正式模型定义
- `API` 提供脚本友好的外部调用入口
- `GUI Shell` 提供工作台式交互壳层

它们的共同特点是：都不应该直接决定 solver 内部结构，也不应该跳过正式编译链路。

### ModelDB
`ModelDB` 是问题定义唯一来源。

它表达的是“要解什么问题”，而不是“如何计算”。材料、截面、边界、载荷、步骤、输出请求等，都属于定义世界，应该在这里被组织起来。

### Compiler
`Compiler` 是定义世界进入 runtime 世界的正式入口。

它负责：

- 校验模型定义
- 绑定 provider
- 构建运行时对象
- 组织 DOF 编号
- 生成 `CompiledModel`

这层非常关键，因为它把“问题定义”和“数值执行”明确隔开了。

### CompiledModel
`CompiledModel` 是编译后的运行时对象集合。

它持有已经绑定好的 element runtime、material runtime、section runtime、constraint runtime、interaction runtime、procedure runtime，以及与当前模型对应的 `DofManager`。

### Procedure
`Procedure` 负责组织分析流程。

它表达的是“这一类分析如何执行”，例如静力、模态、隐式动力学。它不应该直接依赖具体单元类名，也不应该把自己写成某种特殊单元专用逻辑。

### Solver
`Solver` 负责离散问题、装配、backend 和状态推进等求解执行内容。

在当前仓库里，procedure 会通过正式 solver 主线推进计算，而不是自己直接把所有矩阵和状态管理逻辑写死。

### ResultsWriter / ResultsReader / ResultsDB
结果侧通过正式结果合同流转：

- `ResultsWriter` 负责把结果写出
- `ResultsReader` 负责正式读取
- `ResultsDB` 表示结果后端抽象

这样做的目的是让结果不再只是“solver 里的一堆临时数组”，而是可以被正式消费、导出、查询和后续产品层使用。

### Post / Export
后处理与导出层消费的是正式 reader 接口，而不是直接依赖求解器内部状态。

这使得：

- `ResultsFacade`
- `ResultsQueryService`
- `ResultsProbeService`
- `VTK` 导出器

都能沿着同一条正式结果链路工作。

---

## 核心设计约束
下面这些约束，是当前仓库最重要的开发边界。后续继续扩展功能时，建议始终沿这些边界接入。

### 1. `ModelDB` 是问题定义唯一来源
所有模型定义信息都应以 `ModelDB` 为准。不要让 GUI、脚本壳、importer 或其他外层逻辑各自偷偷维护一份“自己的模型状态”。

### 2. `Compiler` 是定义世界与 runtime 世界之间的正式中间层
不能为了图省事，直接从定义对象去实例化某个运行时单元或某个 solver 结构。定义对象和运行时对象之间必须经过编译阶段。

### 3. `DofManager` 负责全局 DOF 编号
全局自由度编号必须统一管理。单元不能自己按节点编号做算术拼凑全局 DOF。

### 4. `Procedure` 不依赖具体单元类名
分析程序组织层不应该被具体单元实现反向绑死，否则后续扩展 procedure 或单元都会越来越难维护。

### 5. 结果必须走正式结果链路
正式结果应该通过：

`ResultsWriter / ResultsReader / ResultsDB`

这条链路流转，而不是 solver 直接返回某个 ad-hoc 结构后让外层硬读。

### 6. `Importer` 只负责导入
`Importer` 的职责是把输入翻译成正式模型定义，而不是直接驱动求解。

### 7. `GUI / API / Job` 只消费正式平台接口
GUI、API 和作业壳层只能调用正式入口，不能直接侵入 solver / backend / element 内部结构，更不能反向决定内核架构。

### 8. `RuntimeRegistry` 是当前唯一正式扩展面
当前仓库已经明确把 registry 作为统一扩展入口。新增扩展时，应优先挂到 `RuntimeRegistry`，不要再额外发明第二套旁路注册机制。

这些约束的目的，不是把开发变复杂，而是避免项目以后因为临时补丁太多而变成难以继续演进的系统。

---

## 仓库结构
当前仓库按平台分层组织，大致如下：

### `src/pyfem/foundation/`
基础设施层。

负责公共常量、错误类型、版本信息和底层支撑能力。它不表达具体有限元模型，也不应该依赖更高层业务模块。

### `src/pyfem/modeldb/`
问题定义层。

负责模型、步骤、材料、截面、边界、载荷、输出请求等定义对象，是“要解什么”的唯一来源。

### `src/pyfem/mesh/`
网格与几何拓扑抽象层。

这里放的是节点、单元记录以及相关的基础网格结构，例如 `ElementRecord`。

### `src/pyfem/compiler/`
编译层。

负责校验定义对象、绑定 provider、构建 runtime、组织 DOF 编号，并生成 `CompiledModel`。

### `src/pyfem/kernel/`
物理 runtime 层。

当前包括：

- `elements`
- `materials`
- `sections`
- `constraints`
- `interactions`

### `src/pyfem/procedures/`
分析程序组织层。

当前已包括：

- `static_linear`
- `modal`
- `implicit_dynamic`

### `src/pyfem/solver/`
求解执行层。

负责装配、backend、离散问题对象和状态推进。

### `src/pyfem/io/`
输入输出层。

包括 importer、results writer / reader 和 `VTK` exporter。

### `src/pyfem/post/`
结果消费层。

包括：

- `ResultsFacade`
- `ResultsQueryService`
- `ResultsProbeService`
- 其他结果恢复、派生、概览相关服务

### `src/pyfem/job/`
标准作业执行壳层。

这里主要承接标准作业执行流程、monitor 报告和默认路径生成等工作。

### `src/pyfem/api/`
面向脚本和外部调用的入口层。

当前核心入口是 `PyFEMSession`。

### `src/pyfem/gui/`
最小 GUI 工作台壳。

它负责调用正式接口、组织视图和结果消费，不直接侵入 solver / backend / element。

### `src/pyfem/plugins/`
插件层。

当前已经有 manifest、发现、校验与注册第一版。

### `tests/`
测试目录。

按 `unit / integration / verification / regression` 分层组织。

### `docs/`
文档目录。

包括架构说明、模块职责、开发规范、路线图和测试门禁文档。

### `tasks/`
任务拆解与阶段评审记录。

---

## 环境准备

## 基本要求
- Python `>= 3.11`
- 建议使用虚拟环境

## 运行依赖
从当前代码导入和入口使用情况看，求解与测试至少需要本地安装：

- `numpy`
- `scipy`

如果要使用 GUI，还需要：

- `PySide6`
- `pyvista`
- `pyvistaqt`

## 推荐安装方式

仅使用求解主线：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e . numpy scipy
```

如果还需要 GUI：

```powershell
python -m pip install -e ".[gui]" numpy scipy
```

## 关于安装说明
当前 `pyproject.toml` 已经声明了 GUI 可选依赖和 `pyfem-gui` 脚本入口，但核心数值依赖还没有完全写进项目依赖列表。因此在本地开发时，建议显式安装 `numpy` 和 `scipy`。

## 关于脚本运行
根目录下的 `run_case.py` 和 `run_gui.py` 会自动把 `src/` 加入 `sys.path`。这意味着在本地快速试跑时，即使没有先做 editable install，通常也能直接运行脚本。

不过如果要长期开发，仍然建议先执行：

```powershell
python -m pip install -e .
```

---

## 快速开始

### 1. 运行现有 INP 算例
直接运行：

```powershell
python run_case.py
```

默认会读取根目录下的 `Job-1.inp`，并沿正式主线完成：

1. importer 导入模型
2. `Compiler` 编译得到 `CompiledModel`
3. `Procedure` 调用 solver 主线
4. `ResultsWriter` 写出结果
5. 可选导出 `VTK`

这条路径不会绕开 `Compiler`、`Procedure` 或 `ResultsWriter`。

### 2. 使用环境变量覆盖 `run_case.py`
`run_case.py` 支持通过环境变量覆盖默认配置，方便在不改脚本的情况下切换算例。

当前支持：

- `PYFEM_INP_PATH`：输入文件路径
- `PYFEM_MODEL_NAME`：覆盖模型名
- `PYFEM_STEP_NAME`：指定执行步骤名
- `PYFEM_RESULTS_PATH`：结果输出路径
- `PYFEM_WRITE_VTK`：是否导出 VTK，支持 `0 / false / no / off` 关闭
- `PYFEM_VTK_PATH`：VTK 输出路径
- `PYFEM_REPORT_PATH`：作业报告 JSON 输出路径

示例：

```powershell
$env:PYFEM_INP_PATH = "Job-1.inp"
$env:PYFEM_RESULTS_PATH = "Job-1.results.json"
$env:PYFEM_VTK_PATH = "Job-1.vtk"
python run_case.py
```

### 3. 使用 API Session
脚本层推荐优先使用 `PyFEMSession`，而不是自己在外部手工拼 importer、compiler 和 solver。

示例：

```python
from pathlib import Path

from pyfem.api import PyFEMSession

session = PyFEMSession()

report = session.run_input_file(
    Path("Job-1.inp"),
    results_path=Path("Job-1.results.json"),
    export_format="vtk",
    export_path=Path("Job-1.vtk"),
)

results = session.open_results(Path("Job-1.results.json"))
print(report.frame_count, results.list_steps())
```

`PyFEMSession` 当前提供的能力包括：

- `load_model_from_file`
- `run_input_file`
- `run_model`
- `open_results`
- `export_results`
- `discover_plugin_manifests`
- `register_discovered_plugins`

它适合：

- 自动化脚本
- 轻量二次封装
- 与其他 Python 工具集成
- 外层工作流控制

### 4. 启动 GUI
如果已经安装 GUI 依赖，可以通过以下任一方式启动：

```powershell
python run_gui.py
```

或者：

```powershell
pyfem-gui
```

当前 GUI 更适合做以下事情：

- 主线演示
- 结果查看
- 基础后处理交互
- 导航和结果浏览联动

它现在还不是完整建模环境，因此不建议把它理解成“已经具备完整商业 CAE 前端”。

### 5. 查看结果
结果消费侧推荐通过下面这些正式入口使用：

- `ResultsFacade`
- `ResultsQueryService`
- `ResultsProbeService`

尽量不要直接依赖 solver 运行时内部数组，也不要在外层硬编码读取某个 JSON 字段结构。对于长期演进的项目来说，正式 reader 接口比直接读裸结构更稳定。

---

## 当前推荐入口
如果只是想沿正式主线熟悉仓库，建议优先从下面这些对象开始：

- 求解执行入口：`pyfem.job.JobManager`
- 脚本入口：`pyfem.api.PyFEMSession`
- 结果消费入口：`pyfem.post.ResultsFacade`
- GUI 壳入口：`pyfem.gui.GuiShell`
- 编译入口：`pyfem.Compiler`
- 扩展注册入口：`pyfem.RuntimeRegistry`

如果只是想先把主线跑通，最简单的入口通常是：

- `python run_case.py`
- `PyFEMSession`

---

## 插件系统说明
当前仓库已经有插件系统第一版，不只是简单地预留了一个 `plugins/` 目录。

当前已经具备的内容包括：

- 插件 manifest
- 插件 manifest 解析
- 插件发现
- 插件 manifest 加载
- 核心版本兼容检查
- 注册函数签名检查
- 扩展点声明校验
- 通过 `RuntimeRegistry` 的统一注册

这意味着当前插件接入是有正式约束的：

1. 先发现 manifest  
2. 再校验 manifest 内容和兼容性  
3. 再通过正式注册函数接入统一 registry  

而不是随便 import 一段代码就算接入成功。

从当前入口设计看，外层更推荐通过：

- `PluginDiscoveryService`
- `PyFEMSession.discover_plugin_manifests`
- `PyFEMSession.register_discovered_plugins`

来管理插件发现与注册。

---

## 测试与质量门禁
这个仓库不建议靠“手工跑一个算例没报错”来判断改动是否安全。当前测试门禁已经开始承担保护架构边界的作用。

## 测试目录分层
当前测试目录按下面四类组织：

- `tests/unit/`  
  模块级单元测试、接口约束、fail-fast 语义

- `tests/integration/`  
  多模块串联、产品壳层接入、执行主线联调

- `tests/verification/`  
  数值验证、patch test、最小 benchmark 保护集

- `tests/regression/`  
  架构回归、结果合同回归、实例/作用域语义回归、多步路径回归

## pytest 标记
当前 `pytest` 配置里已经声明了这些关键标记：

- `unit`
- `integration`
- `verification`
- `regression`
- `gate_fast`
- `gate_full`
- `instance_scope`
- `results_contract`
- `multistep`
- `phase1_baseline`

## 自动补标逻辑
除了手写 marker 以外，`conftest.py` 还会按目录和主题自动补充测试标记。例如：

- `tests/unit/` 自动带 `unit` 和 `gate_fast`
- `tests/regression/` 自动带 `regression` 和 `gate_fast`
- 所有测试都会补 `gate_full`
- 名称包含 `scope / instance_scope / compilation_scopes` 的测试会补 `instance_scope`
- 名称包含 `multistep` 的测试会补 `multistep`
- 与结果合同、query/probe、vtk exporter 相关的测试会补 `results_contract`

这套自动补标逻辑的意义，是让测试门禁不只停留在“靠人记得打标签”，而是尽量由目录和主题约定来维持一致性。

## 推荐命令
本地高频回归：

```powershell
python -m pytest -m gate_fast
```

较完整门禁：

```powershell
python -m pytest -m gate_full
```

兼容入口：

```powershell
python -m unittest discover -s tests
```

## 当前门禁重点保护的内容
从现有组织方式看，当前测试重点保护的是这些方面：

- `C3D8 / CPS4 / B21` 的 patch test 和基础 benchmark
- `static_linear / modal / implicit_dynamic` 主线
- `ModelDB -> Compiler -> Procedure -> Results` 管线完整性
- `DofManager`、作用域与 transform 语义
- 正式结果合同与多步结果路径
- reader-only 结果消费边界
- 产品壳层和插件发现不反向侵入内核

---

## 开发时的建议
为了让仓库继续沿平台化方向演进，开发时建议始终遵守下面这些习惯。

### 新能力优先接入正式主线
不要为了局部方便再额外开一条旁路求解通道。能挂到正式链路上的，优先走正式链路。

### `Importer` 只负责导入
importer 负责把输入翻译成正式模型定义，不负责直接驱动 solver。

### `GUI / API / Job` 只调用正式接口
这些壳层不应该去直接实例化底层 element、backend 或 solver 内部对象，更不应该反向定义内核结构。

### `Procedure` 负责组织分析流程
procedure 的职责是组织某类分析怎么执行，而不是绑定某个具体单元实现。

### 结果输出走 `ResultsWriter`
不要在 solver 或某个临时脚本里直接写 ad-hoc 结果结构。

### 结果消费尽量沿 `ResultsReader` 边界
后处理、导出和 GUI 应尽量基于正式 reader 接口工作，而不是直接依赖求解器内部状态或 JSON 细节。

### 新扩展优先挂到 `RuntimeRegistry`
当前 registry 已经是统一扩展面。新增 element、material、section、procedure、约束、相互作用或其他正式扩展时，优先通过 registry 接入。

### 保持文档和测试同步
新增功能最好同时补三样东西：

- 最小可用实现
- 对应测试
- 对应文档说明

这样项目不会出现“代码已经改了，但README和测试还是旧状态”的断层。

### 文本风格约定
当前项目约定：

- 标识符使用英文
- 注释、docstring、架构说明、开发说明使用中文

继续沿用这套风格，会更利于长期维护。

---

## 文档索引
如果想进一步了解当前仓库边界和开发思路，可以优先阅读下面这些文档：

- `docs/Architecture_Overview.md`  
  整体架构与正式主线说明

- `docs/Module_Responsibilities.md`  
  顶层模块职责与协作边界

- `docs/Development_Guide.md`  
  开发规范、扩展纪律与推荐工作流

- `docs/Test_Gates_and_Benchmarks.md`  
  测试分层、benchmark 落点与门禁建议

- `docs/Roadmap_v1.2.md`  
  路线图与阶段演进方向

- `tasks/01_bootstrap.md` ~ `tasks/05_results_io.md`  
  v2 重构任务拆解

- `tasks/99_arch_review.md`  
  架构评审与阶段性结论

---

## 当前状态总结
可以把当前 pyFEM v2 理解成下面这个状态：

- 主线已经搭起来了
- 关键边界已经收住了
- 脚本、作业、结果消费、GUI、插件这些外层入口已经有了第一版
- 测试门禁已经开始承担“防止架构回退”的作用
- 后面还需要继续补算法深度、结果后端、GUI 完整度和插件生态

如果你的目标是继续开发 pyFEM v2，最稳妥的方式，还是沿着现有正式主线继续扩，而不是为了局部方便去绕开它。