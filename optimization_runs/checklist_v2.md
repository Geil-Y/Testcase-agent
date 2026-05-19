---
name: checklist-v2
description: BMS HIL 测试用例质量 checklist v2 — 基于 v1 + 5 轮优化报告 + 汽车行业标准复审
status: draft
created: 2026-05-19
---

# BMS HIL 测试用例质量 Checklist v2

> **来源标注**：[CodeX] = 规则来自 BMS_HIL_Agent_CodeX 项目 prompt 模块；无标注 = 当前项目 prompts 或通用规则。
> **v2 变更**：合并重叠项、删除归属错误的检查项、新增 traceability、重写覆盖方法论、5.1 降为 WARNING。

---

## 1. 结构完整性 (Structural Integrity)

### 1.1 必填字段非空
- [ ] 1.1.1 `title` 不为空、不是 placeholder（如 "Draft Test Case"、"Test Case"）
- [ ] 1.1.2 `objective` 不为空，明确描述了验证目标
- [ ] 1.1.3 `precondition` 不为空，描述了测试前系统状态
- [ ] 1.1.4 `postcondition` 不为空，描述了测试后系统状态
- [ ] 1.1.5 至少包含 1 个 `step`，每个 step 有 `action`
- [ ] 1.1.6 `objective` 中关联需求 ID（requirement_key），case 内容确实验证该需求描述的行为

### 1.2 输出格式正确
- [ ] 1.2.1 LLM#1 输出包含 `<analysis>` 和 `<coverage_plan>` 两个 section
- [ ] 1.2.2 LLM#2 输出包含完整的 `<testcase>` HTML 结构
- [ ] 1.2.3 所有 section 都能被 HTML parser 成功解析（无 parse error）

---

## 2. 领域正确性 (Domain Correctness)

### 2.1 信号名与标识符
- [ ] 2.1.1 已知信号名在 case 中被引用，拼写与需求原文一致（不自行缩写或变体，不凭空发明不存在的信号名）
- [ ] 2.1.2 不凭空发明需求原文未提供的标识符（CAN ID、诊断 ID、memory location、calibration name 等）[CodeX]

### 2.2 参数与值
- [ ] 2.2.1 不凭空发明数值阈值（如 "3.7V"、"50°C"）；已知阈值从需求原文引用 [CodeX]
- [ ] 2.2.2 符号化参数名（如 t_CellOV_Debounce）视为有效具体值，可直接用于 action 的 Wait 步骤

---

## 3. [NEEDS REVIEW] 使用规范 [HARD GATE]

漏标 [NEEDS REVIEW] 或凭空编造缺失语义直接判定为 **不可接受（hard fail）**。

### 3.1 五类缺失语义
[NEEDS REVIEW] 仅覆盖以下五类需求语义缺口：
- **signal** — BMS 信号名缺失
- **threshold** — 阈值参数缺失
- **timing** — 时序/去抖参数缺失
- **state** — BMS 状态/模式名缺失
- **observation** — 可观测检查点（DTC、CAN 帧、故障记录等）缺失

不用于 HIL 通道名、工具命令、bench 配置或其他执行环境细节。

### 3.2 Hard fail 条件
- [ ] 3.2.1 [HARD] 若 action 或 expected 需使用 signal/threshold/timing/state/observation 但需求未提供且 case 未标注 [NEEDS REVIEW] → **hard fail**
- [ ] 3.2.2 [HARD] 若 action 或 expected 凭空编造了需求未提供的 signal/threshold/timing/state/observation → **hard fail**
- [ ] 3.2.3 [WARNING] 若需求语义完整但 case 添加了不必要的 [NEEDS REVIEW] → 扣分但不自动 severe，除非阻塞可执行性

### 3.3 位置精确
- [ ] 3.3.1 [NEEDS REVIEW] 放在实际需要该值的位置（action 或 expected），不放在 title/objective/precondition/postcondition 等无关字段 [CodeX]
- [ ] 3.3.2 时序参数缺失时，占位符放在 action 的 Wait 步骤（不假设瞬时响应）
- [ ] 3.3.3 [NEEDS REVIEW] 使用裸格式，禁止带 category 后缀（禁止 `[NEEDS REVIEW: timing]`）

---

## 4. 步骤质量 (Step Quality)

### 4.1 步骤结构
- [ ] 4.1.1 时序等待与执行动作分为独立的两步（如 step 1: Set volt = 4.2V, step 2: Wait t_CellOV_Debounce）
- [ ] 4.1.4 action 不包含意图叙述（无 "such that"、"in order to"、"to verify" 等连接词）；action 应只描述具体操作
- [ ] 4.1.5 每条 action 不超过 15 词，避免意图叙述式长句

### 4.2 Expected Result 可观测性
- [ ] 4.2.1 至少一个 expected result 是具体且可观测的（当足够信息存在时）[CodeX]
- [ ] 4.2.2 不包含模糊的 expected result（如 "system works correctly"、"behaves as expected"）[CodeX]
- [ ] 4.2.3 不包含只描述 "read/check/verify/observe/monitor/capture" 但不说明具体期望值的预期结果 [CodeX]
- [ ] 4.2.4 每条 expected result 不超过 15 词，避免段落式叙述

---

## 5. 覆盖维度 (Coverage Dimension)

### 5.1 维度匹配 [WARNING]
以下 5 项为 warning 级别——用于指导 case 设计方向，不参与硬性 pass/fail 判定：
- [ ] ~~5.1.1 `normal_behavior` 的 case 描述正常功能路径的触发和响应~~ [WARNING]
- [ ] ~~5.1.2 `boundary_or_threshold` 的 case 测试阈值边界的触发/不触发行为~~ [WARNING]
- [ ] ~~5.1.3 `fault_or_protection` 的 case 测试故障场景和保护响应~~ [WARNING]
- [ ] ~~5.1.4 `state_transition` 的 case 测试状态变更（置位→复位、复位→置位）~~ [WARNING]
- [ ] ~~5.1.5 `observability` 的 case 验证信号/数据可观测性和日志记录~~ [WARNING]

### 5.2 等价类划分与边界值分析
- [ ] 5.2.1 对于每个阈值判定逻辑，至少覆盖「触发」和「不触发」两个等价类
- [ ] 5.2.2 阈值边界处覆盖「恰好触发」和「恰好不触发」的边界值 case
- [ ] 5.2.3 若参数阈值和时序阈值同时存在，二者为独立的正交维度，分别拆分等价类与边界值 case [CodeX]

---

## 6. 测试工程深度 (Test Engineering Depth)

### 6.1 Precondition / Postcondition 一致性
- [ ] 6.1.1 所有 case（跨需求）使用统一的 precondition（测试环境回归到同一初始状态）
- [ ] 6.1.2 所有 case（跨需求）使用统一的 postcondition（测试结束后回归到同一状态）
- [ ] 6.1.3 所有 setup 动作放在 action 中，不在 precondition 里做具体的模拟/配置操作

### 6.2 Title 描述性
- [ ] 6.2.1 Title 陈述了测试条件和预期的 BMS 行为（非泛化标题）[CodeX]

### 6.3 用例聚焦
- [ ] 6.3.1 每个 case 仅验证一个需求的一个行为 [CodeX]
- [ ] 6.3.2 一个 case 不合并多个不同阈值场景 [CodeX]

---

**总计：** 40 个检查项（含 2 个 [HARD] gate、6 个 [WARNING]），分为 6 大类。
**CodeX 来源项数：** 标注 [CodeX] 的项

**v2 相对 v1 变更：**
- 新增：1.1.6（traceability）、3.2.1~3.2.3（hard fail 条件）、3.3.3（裸格式要求）
- 删除：2.2.1（阈值引用错位）、2.3.1（时序引用错位）、4.1.1（action/expected 分离过于绝对）
- 合并：2.1.1+2.1.3、2.1.2+2.4.1+2.4.2、原 3.1.1+3.1.2 → 现在的 3.3.1
- 重写：5.2 整节（等价类+边界值方法论替代原参数/时序分离规则）、3 整节（五类缺失语义 + hard gate）
- 降级：5.1.1~5.1.5 → [WARNING]
- 修正：NEEDS REVIEW 位置从 "仅 expected" 扩展到 "action 或 expected"
