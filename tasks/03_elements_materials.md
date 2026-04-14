# Task 03 - 第一批 Element / Material / Section Runtime

请严格读取并遵守仓库根目录中的 `AGENTS.md` 和 `Prompt.md`。

## 本轮任务目标
实现 Phase 1 的第一批运行时对象：
- MaterialRuntime
- SectionRuntime
- ElementRuntime

并接入：
- C3D8
- CPS4
- B21
- 各向同性线弹性材料

---

## 必须完成的内容

### 1. 实现 MaterialRuntime 第一版
至少实现：
- `ElasticIsotropicRuntime`

要求：
- 使用统一的 `MaterialRuntime` 接口
- 即使当前是线弹性，也必须走 `allocate_state + update` 路径
- 保留未来状态变量材料的扩展点

### 2. 实现 SectionRuntime 第一版
至少实现：
- `SolidSectionRuntime`
- `PlaneStressSectionRuntime`
- `PlaneStrainSectionRuntime`
- `BeamSectionRuntime`

要求：
- Beam section 至少支持面积、惯性矩等基本参数入口
- Section 与 material 必须解耦，不能把 section 参数硬塞到 material 类中

### 3. 实现 ElementRuntime 第一版
至少实现：
- `C3D8Runtime`
- `CPS4Runtime`
- `B21Runtime`

所有单元都必须实现统一接口：
- `type_key`
- `dof_layout`
- `allocate_state`
- `tangent_residual`
- `mass`
- `damping`
- `output`

### 4. 单元实现范围
当前先做：
- 小变形
- 线弹性
- 静力/模态/基础动力学所需局部贡献

### 5. 质量矩阵
必须保留质量矩阵接口。
如果当前只实现一致质量或集总质量，请明确说明采用了哪一种，并在注释和总结中写清楚。

### 6. 输出接口
至少支持：
- 位移相关输出
- 应力
- 应变
- 梁单元基本截面输出（若当前实现有限，请说明）

### 7. 测试
至少增加：
- C3D8 基本刚度或 sanity check
- CPS4 基本 patch / sanity check
- B21 悬臂梁或基础梁刚度 sanity check
- 材料弹性矩阵合理性测试
- Section 参数传递测试

---

## 严格要求
1. 所有代码标识符使用英文。
2. 所有注释和 docstring 使用中文。
3. 不允许在单元内部通过 node id 生成全局 DOF。
4. 不允许在单元内部访问全局矩阵。
5. 不允许把单元和 assembler、solver 直接耦合。
6. 不允许为了当前阶段简化而破坏未来几何非线性和动力学扩展接口。

---

## 工作方式要求
1. 先检查当前 runtime 抽象是否足够。
2. 如果需要微调接口，先说明理由再修改。
3. 按“材料 -> 截面 -> 单元 -> 测试”顺序推进。
4. 最后输出：
   - 实现了哪些 runtime
   - 每个 runtime 的职责
   - 目前支持范围
   - 质量矩阵策略
   - 测试结果
   - 当前限制
   - 下一步建议

---

## 交付标准
本轮结束后，应具备：
- 三类正式单元 runtime
- 一类正式材料 runtime
- 四类 section runtime
- 对应测试与基本验证