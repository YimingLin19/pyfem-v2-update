# pyFEM v2 Architecture Overview

## 1. 文档目的
本文档描述 pyFEM v2 在 `Phase 6A` 时点的当前架构、正式主线、产品层外壳边界与后续扩展位置。

本文档只描述当前仓库已经存在的正式能力，不描述尚未落地的未来能力。

## 2. 当前阶段定位
当前仓库处于：

`Phase 6A：基础产品化与生态雏形`

本阶段的重点不是扩充新的大型物理能力，而是把已有平台主线向产品壳层收口：

- 文档与项目外壳
- Job / execution shell
- API / session facade
- Results 消费入口
- 最小 GUI 壳
- 插件发现 / 注册雏形

## 3. 正式主数据流
当前正式数据流为：

`Importer / API / GUI Shell -> ModelDB -> Compiler -> CompiledModel -> ProcedureRuntime -> Solver -> ResultsWriter / ResultsDB -> ResultsReader -> Query / Probe / Export / GUI`

这个数据流体现以下非协商原则：

1. `ModelDB` 是问题定义唯一来源。
2. `Compiler` 是 ModelDB 与 Runtime 之间的强制中间层。
3. `ResultsWriter / ResultsReader / ResultsDB` 是正式结果合同。
4. 产品层只能消费平台接口，不能反向决定内核结构。

## 4. 核心分层
### 4.1 平台核心
- `modeldb/`：问题定义、实例/作用域、步骤、作业、输出请求
- `compiler/`：校验、scope 解析、provider 绑定、runtime 构建、DOF 编号
- `kernel/`：单元、材料、截面、约束、相互作用 runtime
- `procedures/`：`static / modal / implicit_dynamic`
- `solver/`：装配、backend、状态推进

### 4.2 IO 与结果
- `io/`：INP importer、JSON results writer/reader、VTK exporter
- `post/`：reader-only 的 query / probe / facade

### 4.3 产品壳层
- `job/`：统一执行外壳与 monitor 输出
- `api/`：脚本友好的 session facade
- `gui/`：最小 GUI 控制壳
- `plugins/`：manifest 与发现/注册雏形

## 5. 当前正式扩展面
### 5.1 RuntimeRegistry
`RuntimeRegistry` 是当前唯一正式扩展面，统一管理：

- element registry
- material registry
- section registry
- procedure registry
- constraint registry
- interaction registry
- importer registry
- exporter registry
- results reader / writer registry
- plugin manifest 注册

不允许再新增第二套注册面。

### 5.2 Plugin Manifest
`plugins/manifest.py` 当前只承担 metadata 角色，可以描述：

- 插件名称
- 插件版本
- 兼容版本
- 扩展点类型
- entry point
- register function

当前 manifest 不直接参与 solver/runtime 构造。

## 6. Job / API / GUI 壳层边界
### 6.1 Job
`JobManager` 负责把以下执行步骤标准化：

1. 加载模型
2. compile
3. 运行 step
4. 写 results
5. 可选 export

它不负责新的 solver 逻辑，也不建立第二套执行主线。

### 6.2 API
`PyFEMSession` 负责为脚本与外部调用提供正式入口，避免外部直接拼装底层对象。

API 只暴露：

- 模型加载
- job 执行
- 结果打开
- 插件发现 / manifest 注册

API 不暴露 `problem / backend / assembler` 等内部对象。

### 6.3 GUI
当前 GUI 只提供薄控制壳，反映正确数据流：

`打开模型 -> 提交 job -> 读取结果 -> 显示基础结果入口`

GUI 不直接 new solver / backend / exporter / 具体 element。

## 7. Results 消费边界
Results 消费侧当前分三层：

1. `ResultsReader`：正式读取接口
2. `ResultsQueryService / ResultsProbeService`：reader-only 服务
3. `ResultsFacade`：产品层友好的最小消费外壳

其中 `vtk / query / probe / facade / gui` 都必须保持 reader-only 边界，不允许回到 solver 内部数组或 JSON dict 旁路。

## 8. 当前能力范围
当前正式支持：

- `C3D8 / CPS4 / B21`
- `static / modal / implicit_dynamic`
- 实例 / 作用域 / transform 第一版
- multi-step 结果路径第一版
- JSON reference results backend
- VTK exporter
- Reader-only post 主线

当前明确未支持：

- 几何非线性
- 材料非线性
- 接触真实算法
- 工程级 ResultsDB 后端
- 成熟 GUI 建模与浏览
- 完整插件 SDK / 市场 / 热加载

## 9. 当前阶段结论
Phase 6A 的意义是让 pyFEM v2 从“内核主线已成立”推进到“具备最小产品接入壳层”，但仍保持平台边界清晰。

下一阶段应继续沿正式接口增强，而不是为了产品表象把执行、结果、插件逻辑重新散落到外层。
