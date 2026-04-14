# pyFEM v2 Module Responsibilities

## 1. 文档目的
本文档说明当前各顶层模块的职责边界、协作约束与开发纪律。

当前对应阶段为 `Phase 6A`。

## 2. 顶层目录职责
| 目录 | 主要职责 | 不应承担的职责 |
| --- | --- | --- |
| `foundation/` | 错误、类型、基础设施 | 物理算法与产品逻辑 |
| `modeldb/` | 问题定义唯一来源 | 求解状态与 GUI 细节 |
| `mesh/` | 网格、集合、surface、orientation | 单元积分与 backend |
| `compiler/` | compile、registry、runtime 构建、DOF 编号 | GUI / Job / API 调度 |
| `kernel/` | element / material / section / constraint / interaction runtime | 产品层 orchestration |
| `procedures/` | static / modal / implicit_dynamic 求解流程 | 具体单元类名分派 |
| `solver/` | 装配、backend、状态推进 | importer / GUI 交互 |
| `io/` | importer、results reader/writer、VTK exporter | 直接驱动 solver |
| `post/` | reader-only 结果消费接口 | 反向操控求解主线 |
| `job/` | 标准化运行入口与 monitor 输出 | 新的 solver 主线 |
| `api/` | 脚本友好 facade | 暴露 solver 内部对象 |
| `gui/` | 最小图形控制壳 | 直接 new backend / solver / element |
| `plugins/` | manifest 与发现/注册壳 | 侵入 kernel / procedure / solver |
| `tests/` | 门禁、验证、回归 | 正式业务实现 |

## 3. 模块协作约束
### 3.1 模型与编译
- `ModelDB` 是问题定义唯一来源。
- `Compiler` 必须是模型世界与运行时世界之间的强制中间层。
- `DofManager` 是全局 DOF 编号唯一责任方。

### 3.2 求解与结果
- `Procedure` 不得依赖具体单元类名。
- 正式结果必须通过 `ResultsWriter / ResultsReader / ResultsDB`。
- `vtk / query / probe / facade / gui` 必须保持 reader-only。

### 3.3 产品层
- `Job / API / GUI` 只能消费平台正式接口。
- importer 不得直接驱动 solver。
- GUI 不得直接实例化 solver / backend / exporter / element。

### 3.4 插件与注册
- `RuntimeRegistry` 是当前唯一正式扩展面。
- 不允许新增第二套半正式注册逻辑。
- plugin manifest 只描述扩展，不直接参与 runtime 构造。

## 4. 当前推荐入口
- 求解执行：`pyfem.job.JobManager`
- 脚本入口：`pyfem.api.PyFEMSession`
- 结果消费：`pyfem.post.ResultsFacade`
- GUI 壳：`pyfem.gui.GuiShell`
- 插件发现：`pyfem.plugins.PluginDiscoveryService`

## 5. 当前开发纪律
1. 标识符使用英文。
2. 注释、docstring、文档说明使用中文。
3. 新能力优先接入 `ModelDB -> Compiler -> Procedure -> Results` 正式主线。
4. 不支持的组合要 fail-fast，不允许静默忽略。
5. 不允许为了产品层便捷而破坏 Phase 3 / 4 / 6A 之后的扩展边界。

## 6. 当前阶段结论
模块边界的重点已经从“内核主线成立”推进到“产品壳层成立但不反向侵入内核”。后续新增功能仍应先看边界，再看实现速度。
