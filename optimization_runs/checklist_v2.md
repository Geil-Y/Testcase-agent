---
name: checklist-v2
description: BMS HIL 测试用例质量 checklist v2 — 基于 v1 + 5 轮优化报告 + 汽车行业标准复审
status: updated
created: 2026-05-19
updated: 2026-05-20
---

# BMS HIL 测试用例质量 Checklist v2

> **来源标注**：[CodeX] = 规则来自 BMS_HIL_Agent_CodeX 项目 prompt 模块；无标注 = 当前项目 prompts 或通用规则。
> **v2.1 变更**：逐条审查后删除 4 条、修改 5 条、重分硬门禁/软警告；LLM 覆盖标注。

---

## 1. 结构完整性 (Structural Integrity)

### 1.1 必填字段非空
- [ ] 1.1.1 `title` 不为空、不是 placeholder（如 "Draft Test Case"、"Test Case"）
- [ ] 1.1.2 `objective` 不为空，明确描述了验证目标
- [ ] 1.1.3 `precondition` 不为空，描述了测试前系统状态
- [ ] 1.1.4 `postcondition` 不为空，描述了测试后系统状态
- [ ] 1.1.5 至少包含 1 个 `step`，每个 step 有 `action`，且至少一个 step 有非空的 `expected`
- [ ] 1.1.6 `related_requirement` 字段存在且非空

---

## 2. 领域正确性 (Domain Correctness)

### 2.1 信号名与标识符
- [ ] 2.1.1 已知信号名在 case 中被引用，拼写与需求原文一致（匹配时忽略标点符号）；不自行缩写或变体，不凭空发明不存在的信号名
- [ ] 2.1.2 不凭空发明当前需求或 explicitly accepted test basis 未提供的标识符（CAN ID、诊断 ID、memory location、calibration name 等）[CodeX]

### 2.2 参数与值
- [ ] 2.2.1 不凭空发明数值阈值（如 "3.7V"、"50°C"）；已知阈值必须来自当前需求或 explicitly accepted test basis [CodeX]
- [ ] 2.2.2 符号化参数名（如 r_CellOV_Threshold、t_CellOV_Debounce）视为有效具体值，可直接用于 action 的 Set 或 Wait 步骤

---

## 3. [NEEDS REVIEW] 使用规范 [HARD GATE]

漏标 [NEEDS REVIEW] 或凭空编造缺失语义直接判定为**不可接受（hard fail）**。

### 3.1 五类缺失语义
[NEEDS REVIEW] 仅覆盖以下五类需求语义缺口：
- **signal** — BMS 信号名缺失
- **threshold** — 阈值参数缺失
- **timing** — 时序/去抖参数缺失
- **state** — BMS 状态/模式名缺失
- **observation** — 可观测检查点（DTC、CAN 帧、故障记录等）缺失

不用于 HIL 通道名、工具命令、bench 配置或其他执行环境细节。

### 3.2 Hard fail 条件
- [ ] 3.2.1 [HARD] 若 action 或 expected 需使用 signal/threshold/timing/state/observation 但当前需求或 explicitly accepted test basis 未提供且 case 未标注 [NEEDS REVIEW] → **hard fail**
- [ ] 3.2.2 [HARD] 若 action 或 expected 凭空编造了当前需求或 explicitly accepted test basis 未提供的 signal/threshold/timing/state/observation → **hard fail**
- [ ] 3.2.3 [HARD] 若需求语义完整但 case 添加了不必要的 [NEEDS REVIEW] → **hard fail**；除非该 [NEEDS REVIEW] 阻塞了可执行性

### 3.3 位置与格式
- [ ] 3.3.1 [NEEDS REVIEW] 放在实际需要该值的位置（action 或 expected），不放在 title/objective/precondition/postcondition 等无关字段 [CodeX]
- [ ] 3.3.2 时序参数缺失时，占位符需要单独一条 Wait step：`Wait [NEEDS REVIEW]`
- [ ] 3.3.3 [WARNING] [NEEDS REVIEW] 应使用裸格式，不推荐带 category 后缀（如 `[NEEDS REVIEW: timing]`）

---

## 4. 步骤质量 (Step Quality)

### 4.1 步骤结构
- [ ] 4.1.1 时序等待与执行动作分为独立的两步（如 step 1: Set voltage to threshold, step 2: Wait t_CellOV_Debounce）
- [ ] 4.1.4 action 不包含意图叙述（无 "such that"、"in order to"、"to verify" 等连接词）；action 不能含 check、verify、observe、monitor、capture 等属于 expected result 的观察动词；action 应只描述具体操作

### 4.2 Expected Result 可观测性与清晰度
- [ ] 4.2.2 不包含模糊的 expected result（如 "system works correctly"、"behaves as expected"、"works normally"）
- [ ] 4.2.3 不包含只描述 "read/check/verify/observe/monitor/capture" 但不说明具体期望值的预期结果；如果期望值用 `[NEEDS REVIEW]` 占位，不在此列

---

## 5. 覆盖维度 (Coverage Dimension)

### 5.1 维度匹配
- [ ] 5.1.1 `normal_behavior` 的 case 描述正常功能路径的触发和响应
- [ ] 5.1.2 `boundary_or_threshold` 的 case 测试阈值边界的触发/不触发行为
- [ ] 5.1.3 `fault_or_protection` 的 case 测试故障场景和保护响应
- [ ] 5.1.4 `state_transition` 的 case 测试状态变更（置位→复位、复位→置位）
- [ ] 5.1.5 `observability` 的 case 验证信号/数据可观测性和日志记录

### 5.2 等价类划分与边界值分析
- [ ] 5.2.1 对于每个阈值判定逻辑，至少覆盖「触发」和「不触发」两个等价类
- [ ] 5.2.2 阈值边界处覆盖「恰好触发」和「恰好不触发」的边界值 case
- [ ] 5.2.3 若参数阈值和时序阈值同时存在，二者为独立的正交维度，分别拆分等价类与边界值 case [CodeX]

> 5.2.1~5.2.3 为跨 case 判断（看一个 requirement 下整组 cases 的互补性），由 LLM evaluator（DeepSeek `coverage_value` 维度）覆盖，不进代码层 hard-rule 检查。

---

## 6. 测试工程深度 (Test Engineering Depth)

### 6.1 Precondition / Postcondition 一致性
- [ ] 6.1.1 所有 case（跨需求）使用统一的 precondition（测试环境回归到同一初始状态）
- [ ] 6.1.2 所有 case（跨需求）使用统一的 postcondition（测试结束后回归到同一状态）

> 6.1.1~6.1.2 为跨需求判断，由 LLM evaluator 覆盖，不进代码层 hard-rule 检查。

- [ ] 6.1.3 所有 setup 动作放在 action 中，不在 precondition 里做具体的模拟/配置操作

### 6.2 Title 描述性
- [ ] 6.2.1 Title 陈述了测试条件和预期的 BMS 行为（非泛化标题）[CodeX]

### 6.3 用例聚焦
- [ ] 6.3.1 每个 case 仅验证一个需求的一个行为 [CodeX]
- [ ] 6.3.2 一个 case 不合并多个不同阈值场景 [CodeX]

---

**总计：** 34 个检查项（含 3 个 [HARD] gate、1 个 [WARNING]），分为 6 大类。
**CodeX 来源项数：** 标注 [CodeX] 的项

**v2.1 相对 v2 变更：**
- 删除：1.2.1~1.2.3（输出格式检查）、4.1.5（action ≤15 词）、4.2.1（与 1.1.5 重复）、4.2.4（expected ≤15 词）
- 修改：1.1.5（增加至少一个 expected 非空）、1.1.6（改为 related_requirement 字段存在）、2.1.2/2.2.1/3.2.1/3.2.2（改为当前需求或 explicitly accepted test basis 授权）、2.2.2（增加 Set 步骤）、3.2.3（改为 [HARD] fail）、3.3.2（占位符需单独 Wait step）、3.3.3（降为 [WARNING]）、4.1.4（增加禁止观察动词）、4.2.2/4.2.3（增加 NEEDS REVIEW 例外）
- 活跃化：5.1.1~5.1.5（去掉划线和 [WARNING]）
- LLM 覆盖标注：5.2.1~5.2.3、6.1.1~6.1.2（不进代码 evaluator）
