# pyFEM v2 当前路线图（v1.2）

> 本文档是当前生效的路线图与阶段口径。
> 如与 `tasks/Prompt.md`、`docs/roadmap_v1.md` 等历史草案冲突，以本文为准。

## 1. 当前阶段
当前仓库处于：

`Phase 6A：基础产品化与生态雏形`

当前阶段的目标不是扩张新物理能力，而是把已有平台主线收口成最小产品外壳。

当前阶段文档收口原则：

1. 现状描述优先集中到 `README.md`、`docs/Architecture_Overview.md` 与本文。
2. 历史设计文档必须明确标识为“历史草案”或“归档记录”。

## 2. 已完成的阶段基线
### Phase 1
- `C3D8 / CPS4 / B21`
- `static / modal / implicit_dynamic`
- `ModelDB -> Compiler -> Procedure -> Results` 主线成立

### Phase 2
- 实例 / 作用域 / transform 第一版
- `ResultsSession -> ResultStep -> ResultFrame/Field + ResultHistorySeries + ResultSummary`
- reader-only 的 `vtk / query / probe`
- patch / benchmark / regression / integration 分层
- `gate_fast / gate_full / unittest discover`
- `RuntimeRegistry` 统一扩展面
- builtin importer / exporter / results IO 正式注册
- plugin manifest 第一版 metadata-only

## 3. 当前 Phase 6A 的范围
本阶段继续收口以下能力：

1. README、架构、路线图、开发规范、测试门禁文档
2. `JobManager` 与统一 execution shell
3. `PyFEMSession` 脚本入口
4. `ResultsFacade` reader-only 消费入口
5. `GuiShell` 最小 GUI 控制壳
6. `PluginDiscoveryService` 插件发现/注册雏形

## 4. 当前明确不做
- 几何非线性、材料非线性、接触真实算法
- 工程级 ResultsDB 后端
- 成熟 GUI 建模器与结果浏览器
- 完整 Session 自动编排
- Job 调度平台、分布式执行、并行作业管理
- 完整插件 SDK、插件市场、动态安装

## 5. Phase 6A 完成判据
1. 产品层存在正式入口，但不新增旁路主线。
2. GUI / API / Job 都只消费平台接口。
3. Results 消费侧保持 reader-only。
4. 插件 discovery / registration 有正式落点，但不侵入 solver。
5. `pytest -m gate_fast`
6. `pytest -m gate_full`
7. `python -m unittest discover -s tests`

## 6. 后续优先方向
### 6B
- 更清晰的 results browsing 入口
- 更成熟的 API/session 组织
- GUI 结果浏览壳增强
- 插件注册策略细化

### 7A
- backend / job policy 工程化
- 更完善的结果后端抽象
- 更稳定的 benchmark baseline 报告

### 后续物理能力
- 非线性主线
- 接触
- 更多单元族
- 更强的材料模型

## 7. 路线原则
后续每一步都应优先沿正式边界增强：

- 不用产品壳反向决定内核结构
- 不用测试或 GUI 逼出旁路
- 不再新增第二套注册与执行逻辑
