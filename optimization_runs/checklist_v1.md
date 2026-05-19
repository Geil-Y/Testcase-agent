---
name: checklist-v1
description: BMS HIL 测试用例质量 checklist — 综合当前项目 prompts 和 CodeX case_generation 模块
status: draft
created: 2026-05-18
---

# BMS HIL 测试用例质量 Checklist v1

> **来源标注**：[CodeX] = 规则来自 BMS_HIL_Agent_CodeX 项目 prompt 模块；无标注 = 来自当前项目 prompts 或通用规则。

---

## 1. 结构完整性 (Structural Integrity)

### 1.1 必填字段非空
- [ ] 1.1.1 `title` 不为空、不是 placeholder（如 "Draft Test Case"、"Test Case"）
- [ ] 1.1.2 `objective` 不为空，明确描述了验证目标
- [ ] 1.1.3 `precondition` 不为空，描述了测试前系统状态
- [ ] 1.1.4 `postcondition` 不为空，描述了测试后系统状态
- [ ] 1.1.5 至少包含 1 个 `step`，每个 step 有 `action`

### 1.2 输出格式正确
- [ ] 1.2.1 LLM#1 输出包含 `<analysis>` 和 `<coverage_plan>` 两个 section
- [ ] 1.2.2 LLM#2 输出包含完整的 `<testcase>` HTML 结构
- [ ] 1.2.3 所有 section 都能被 HTML parser 成功解析（无 parse error）

---

## 2. 领域正确性 (Domain Correctness)

### 2.1 信号名使用
- [ ] 2.1.1 已知信号名（`Known BMS signals`）在 expected result 中被直接引用
- [ ] 2.1.2 不凭空发明不存在的信号名 [CodeX]
- [ ] 2.1.3 信号名使用与原文一致（不自行缩写或变体）

### 2.2 阈值参数使用
- [ ] 2.2.1 已知阈值参数（`Known thresholds`）在 expected result 中被直接引用
- [ ] 2.2.2 不凭空发明数值阈值（如 "3.7V"、"50°C"）[CodeX]

### 2.3 时序参数使用
- [ ] 2.3.1 已知时序参数（`Known timing parameters`）在 expected result 中被直接引用
- [ ] 2.3.2 符号化参数名（如 t_CellOV_Debounce）被视为有效具体值，直接使用

### 2.4 诊断/通信信息
- [ ] 2.4.1 不凭空发明 CAN ID、诊断 ID、memory location [CodeX]
- [ ] 2.4.2 不凭空发明 calibration name [CodeX]

---

## 3. [NEEDS REVIEW] 使用规范

### 3.1 使用场景正确
- [ ] 3.1.1 [NEEDS REVIEW] 仅用于 LLM#1 明确标记为 "Critical missing information" 的值
- [ ] 3.1.2 有具体值时不加 [NEEDS REVIEW]（已知信息的标记不转移到无关字段）

### 3.2 位置精确
- [ ] 3.2.1 [NEEDS REVIEW] 放在 expected result 中实际需要该值的位置，而非无关字段 [CodeX]
- [ ] 3.2.2 对于 BMS detection/set/assert 需求，如果时序缺失，expected result 中必须有 [NEEDS REVIEW] 占位符（不假设瞬时响应）

---

## 4. 步骤质量 (Step Quality)

### 4.1 Action-Expected 分离
- [ ] 4.1.1 每个 step 有独立的 `action`（测试者做了什么）和 `expected`（BMS 可观测响应）

### 4.2 步骤结构
- [ ] 4.2.1 时序等待与执行动作分为独立的两步（如 step 1: set volt = 4.2V, step 2: Wait t_CellOV_Debounce）
- [ ] 4.2.2 无重复的 stimulus/wait 步骤（描述相同 duration 或 trigger condition 时）[CodeX]

### 4.3 Expected Result 可观测性
- [ ] 4.3.1 至少一个 expected result 是具体且可观测的（当足够信息存在时）[CodeX]
- [ ] 4.3.2 不包含模糊的 expected result（如 "system works correctly"、"behaves as expected"）[CodeX]
- [ ] 4.3.3 不包含只描述 "read/check/verify/observe/monitor/capture" 但不说明具体期望值的预期结果 [CodeX]

---

## 5. 覆盖维度匹配 (Coverage Dimension Match)

### 5.1 Case 内容与 Coverage 一致
- [ ] 5.1.1 `normal_behavior` 的 case 描述正常功能路径的触发和响应
- [ ] 5.1.2 `boundary_or_threshold` 的 case 测试阈值边界的触发/不触发行为
- [ ] 5.1.3 `fault_or_protection` 的 case 测试故障场景和保护响应
- [ ] 5.1.4 `state_transition` 的 case 测试状态变更（置位→复位、复位→置位）
- [ ] 5.1.5 `observability` 的 case 验证信号/数据可观测性和日志记录

### 5.2 边界场景分离 [CodeX]
- [ ] 5.2.1 参数未触发边界（parameter 低于阈值、时序满足）和时序未触发边界（duration 不足、参数满足）为独立 case [CodeX]
- [ ] 5.2.2 参数阈值和时序阈值为独立概念，对应不同的 case [CodeX]

---

## 6. 测试工程深度 (Test Engineering Depth)

### 6.1 Precondition / Postcondition 一致性
- [ ] 6.1.1 所有 case（跨需求）使用统一的 precondition（测试环境回归到同一初始状态）
- [ ] 6.1.2 所有 case（跨需求）使用统一的 postcondition（测试结束后回归到同一状态）
- [ ] 6.1.3 所有 setup 动作放在 action 中，不在 precondition 里做具体的模拟/配置操作

### 6.2 Title 描述性
- [ ] 6.2.1 Title 陈述了测试条件和预期的 BMS 行为（非泛化标题）[CodeX]

### 6.3 用例聚焦
- [ ] 6.3.1 每个 case 聚焦于一个需求或一个覆盖意图 [CodeX]
- [ ] 6.3.2 一个 case 不合并多个不同阈值场景 [CodeX]

---

**总计：** 35 个检查项，分为 6 大类。
**CodeX 来源项数：** 标注 [CodeX] 的项
