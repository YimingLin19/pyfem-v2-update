# Task 05 - ResultsDB / Importer / Exporter / 端到端闭环

请严格读取并遵守仓库根目录中的 `AGENTS.md` 和 `Prompt.md`。

## 本轮任务目标
实现结果层和 IO 层基础闭环，并打通端到端流程：

`INP -> ModelDB -> Compiler -> Procedure -> ResultsWriter -> Export`

---

## 必须完成的内容

### 1. 实现轻量 ResultsWriter / ResultsReader
至少支持写出：
- job metadata
- step metadata
- frames
- field outputs
- history outputs

### 2. 第一批 field keys
至少支持：
- U
- RF
- S
- E
- MODE_SHAPE
- FREQUENCY
- TIME

### 3. 结果位置
至少支持：
- NODE
- ELEMENT_CENTROID
- INTEGRATION_POINT（若当前已有）
- GLOBAL_HISTORY

### 4. 实现基础 ResultsReader
要求：
- 能读取写出的结果
- 为后续 post / GUI 预留清晰接口

### 5. 实现基础 VTK exporter
至少能导出：
- 节点位移
- 单元/节点应力中的一部分（当前实现到什么程度要明确说明）

### 6. 实现 INP importer + translator
要求：
- importer 只负责读取输入并构建 ModelDB
- translator 可分层组织
- 严禁 importer 直接驱动 solver internals

### 7. 端到端算例
至少完成一个小算例的完整流程：
- INP
- ModelDB
- Compiler
- Procedure
- ResultsWriter
- VTK export / result readback

### 8. 测试
至少增加：
- importer basic test
- results writer / reader test
- exporter basic test
- end-to-end pipeline test

---

## 严格要求
1. 所有代码标识符使用英文。
2. 所有注释和 docstring 使用中文。
3. importer 不得 new solver internals。
4. 结果层必须独立，不得让 GUI 直接读取 solver 内部变量作为正式结果接口。
5. 不要把 IO、结果、后处理混成一个大文件。

---

## 工作方式要求
1. 先检查当前结果层与 io 层接口。
2. 输出本轮计划。
3. 按“results writer -> results reader -> importer -> exporter -> e2e tests”顺序推进。
4. 最后汇报：
   - 支持了哪些输入输出能力
   - 端到端链路是否打通
   - 测试结果
   - 当前限制
   - 下一步建议

---

## 交付标准
本轮结束后，应具备：
- 轻量 ResultsDB 闭环
- importer 基础能力
- VTK exporter 基础能力
- 端到端最小工作链路