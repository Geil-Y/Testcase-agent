---
name: scoring-rubrics
description: BMS HIL 测试用例 8 维评分标准 — 供 LLM 评估器使用
status: draft
created: 2026-05-20
score_range: 1-5
passing_baseline: 3
evaluation_target: AI-generated BMS HIL draft test cases
---

# BMS HIL 测试用例 8 维评分标准

本评分标准用于评估 AI 生成的 BMS HIL draft test case 是否适合进入人工工程评审或后续自动化转写。

每个维度 1-5 分。
3 分为及格基线：case 基本可用，但需要人工修改后才能进入正式测试资产。

本 rubric 不处理 hard gates。
格式解析、安全拦截、非法字段、结构缺失、非法 `[NEEDS REVIEW]` 语法或位置等 deterministic validation 应由代码层完成。
LLM evaluator 只负责高级语义评分和工程质量判断。

---

## Evaluation Model — 评价模型

本 rubric 同时包含 requirement-level 和 case-level 评分。

- `coverage_value` 是 requirement-level 维度：评价同一条 requirement 下整组 generated cases 的覆盖价值。
- 其他 7 个维度是 case-level 维度：评价每条 case 自身的工程质量。

LLM evaluator 应按 requirement group 评价：一次查看 requirement、analysis / coverage plan、known signals / thresholds / timing / states / observations、missing information items，以及该 requirement 下的所有 generated cases。

代码层负责聚合分数：

- 对每条 requirement，先计算 7 个 case-level 维度在所有 cases 上的平均分。
- `coverage_value` 使用该 requirement 的 case set 分数。
- 再按权重计算 per-requirement score。
- 最后对所有 requirement 的 per-requirement score 取平均，得到 run-level score。
- 同时保留关键维度最低分，用于风险提示或代码层门禁。

LLM evaluator 不输出最终 `overall_score` 或 `decision`。

---

## Dimensions — 评分维度

| 维度 | 层级 | 名称 | 核心问题 |
|------|------|------|----------|
| requirement_alignment | case-level | 需求一致性 / 可追溯性 | 这条 case 是否测对了当前 requirement？ |
| coverage_value | requirement-level | 覆盖价值 | 这组 cases 对当前 requirement 的覆盖是否有验证价值？ |
| executability | case-level | 可执行性 | HIL 操作员或自动化脚本能否执行这条 case？ |
| observability | case-level | 可观测性 | 是否知道应该观察什么证据？ |
| pass_fail_clarity | case-level | 通过/失败判定清晰度 | 观察到结果后能否判断 pass/fail？ |
| information_integrity | case-level | 信息完整性与不脑补 | 信息是否有依据？缺失时是否诚实标注？ |
| state_and_environment_control | case-level | 状态与测试环境控制 | 初始状态、环境假设和恢复行为是否受控？ |
| automation_readiness | case-level | 自动化转写友好度 | 是否适合转成测试脚本或结构化测试资产？ |

---

## Dimension Ownership — 维度边界

- `requirement_alignment`：评价单条 case 是否测对当前 requirement，是否避免测试目标漂移。
- `coverage_value`：评价同一 requirement 下整组 cases 是否形成有价值的覆盖。
- `executability`：评价单条 case 的步骤是否能被 HIL 操作员或自动化脚本执行。
- `observability`：评价 expected result 是否指向可观察证据。
- `pass_fail_clarity`：评价 expected result 是否包含明确的 pass/fail 判定条件。
- `information_integrity`：评价信息是否来自 requirement、retrieved context 或已知 test basis；缺失时是否用 `[NEEDS REVIEW]` 标注。
- `state_and_environment_control`：评价 precondition、test environment、initial state、state transition、restore/reset 是否受控。
- `automation_readiness`：评价 case 是否结构化、原子化、字段边界清楚，适合后续自动化转写。

---

## General Scoring Scale — 通用评分尺度

| 分值 | 通用含义 |
|------|----------|
| **1** | 几乎不可用。核心语义严重缺失、混乱或误导，需要大幅重写。 |
| **2** | 质量较低。有基本结构，但存在明显工程问题，需要大量人工修改。 |
| **3** | 基本可用。能表达主要测试意图，但需要人工补充、收敛或修正。 |
| **4** | 质量较好。大部分内容清晰、可用，仅有少量细节需要改进。 |
| **5** | 高质量。语义清楚、工程上可信，可直接进入人工 review 或低成本自动化转写。 |

---

# 1. requirement_alignment — 需求一致性 / 可追溯性

评价单条 test case 是否紧扣输入 requirement、test objective 和 case intent，是否避免生成与当前需求无关的 BMS 行为。

该维度关注“测得是不是这条需求”，而不是“整组 cases 覆盖得全不全”。
`coverage_value` 评价整组 cases 的覆盖价值；`requirement_alignment` 评价单条 case 的需求一致性和语义聚焦度。

| 分值 | 描述 |
|------|------|
| **1** | 明显跑题。主要测试目标与输入 requirement 不一致；验证了其他 BMS 功能、其他故障类型或无关系统行为；case 无法追溯回当前 requirement。 |
| **2** | 弱相关。case 大体属于 BMS/HIL 范围，但测试目标与 requirement 只有间接关系；存在明显无关步骤、无关 expected result 或无关 case intent。 |
| **3** | 基本相关。case 覆盖了 requirement 的主要意图，但部分 steps、expected result 或 objective 不够聚焦；需要人工删除、收敛或重写部分内容后才能形成清晰追溯关系。 |
| **4** | 高度一致。objective、steps 和 expected result 基本都能追溯到当前 requirement；仅有少量表达不够精确，或 case intent 与具体步骤之间存在轻微不一致。 |
| **5** | 完全一致且聚焦。case 只验证当前 requirement 的一个明确行为；objective、case intent、steps、expected result 语义一致；无无关 BMS 行为、无额外假设、无测试目标漂移。 |

### Notes

- 不因整组 cases 覆盖不完整而降低 `requirement_alignment`。
- 如果 case 明确聚焦当前 requirement 的一个有效行为，即使只是 positive path，也可以获得较高 `requirement_alignment` 分。
- 字段格式、step 粒度、`[NEEDS REVIEW]` 位置等 deterministic 问题不在本维度扣分。

---

# 2. coverage_value — 覆盖价值

评价同一条 requirement 下整组 generated cases 是否提供有意义的验证价值。

该维度关注“这组 cases 对当前 requirement 覆盖得是否有价值”。
它不是单条 case-level 分数，而是 requirement-level / case-set-level 分数。

| 分值 | 描述 |
|------|------|
| **1** | 覆盖价值很低。case set 没有清晰覆盖任何有效 coverage dimension；多条 cases 重复同一个浅层场景，或混入多个与当前 requirement 无关的行为，无法形成有意义的验证证据。 |
| **2** | 覆盖价值较弱。case set 声明了 coverage dimensions，但实际 cases 与这些 dimensions 匹配较差；关键触发/不触发、边界、时序、状态或恢复场景明显缺失；存在把多个阈值、多个故障或多个状态转换混在一条 case 中的问题。 |
| **3** | 覆盖价值基本可接受。case set 能覆盖 requirement 的一个或多个明确行为，例如触发场景、非触发场景、边界附近场景或时序场景；但覆盖粒度较粗，互补性不足，边界/时序/状态条件未充分拆分。 |
| **4** | 覆盖价值较高。case set 聚焦当前 requirement，cases 之间有明确分工；触发/不触发、边界、时序、恢复或状态依赖场景基本形成互补覆盖，仅有少量正交拆分或边缘场景不足。 |
| **5** | 覆盖价值很高。case set 精准覆盖 requirement 下的重要独立 coverage intents；不混合无关行为，不重复堆叠同质 cases；等价类、边界值、时序条件、恢复行为和状态转换拆分合理，能形成清晰、可追溯的验证证据。 |

### Typical Coverage Dimensions

- `positive_trigger`：条件满足后功能应触发
- `negative_no_trigger`：条件未满足时功能不应触发
- `boundary_trigger`：边界上方或达到触发条件
- `boundary_no_trigger`：边界下方或未达到触发条件
- `timing_trigger`：持续时间满足 debounce / confirmation time 后触发
- `timing_no_trigger`：持续时间不足时不触发
- `recovery`：条件恢复后故障、状态或输出按需求恢复
- `diagnostic_reporting`：诊断状态、DTC、warning 或 fault status 按需求上报
- `state_dependent_behavior`：不同 BMS state / mode 下行为不同
- `robustness`：合理异常输入、边缘状态或干扰条件下行为符合需求

### Notes

- 覆盖价值不等于 case 数量。
- 评价对象是同一 requirement 下的全部 generated cases。
- 单条 case 应聚焦一个 coverage intent；case set 应形成互补覆盖。
- 覆盖必须服务于 requirement evidence，而不是生成看似丰富但无关的测试场景。

---

# 3. executability — 可执行性

评价单条 case 的测试步骤是否能被 HIL 操作员或自动化脚本顺利执行，且无需大量人工解释。

该维度关注 step flow、动作粒度、操作对象、执行顺序和恢复动作是否清晰。
`information_integrity` 评价信息是否有依据；`executability` 评价步骤是否能被执行。

| 分值 | 描述 |
|------|------|
| **1** | 基本不可执行。步骤缺失、顺序混乱，或 action 主要是测试意图 / 需求复述，而不是可执行操作；HIL 操作员无法判断应该 set 什么、wait 什么、check 什么。 |
| **2** | 有基本步骤结构，但执行困难。部分 action 过于抽象，操作对象不清楚，多个动作混在同一步，或缺少关键 set / wait / check 环节；需要大量人工补充才能执行。 |
| **3** | 基本可执行。主要步骤能形成合理的 set -> wait -> check 流程，每步大体只有一个操作；但部分 action 仍带有意图叙述，步骤粒度不稳定，或 restore / reset 行为不够清楚。 |
| **4** | 可执行性较好。步骤顺序清晰，action 以具体操作为主，set / wait / check / restore 基本分离；HIL 操作员只需少量工程判断即可执行。 |
| **5** | 高度可执行。每一步都是清晰、原子化、命令式操作；测试流程完整且顺序自然；set、wait、check、restore 分离明确；无需额外解释即可进入人工 review 或自动化脚本转写。 |

### Notes

- action 应简洁、原子化、命令式；通常不应写成长段解释。
- action 不应使用 “in order to”、 “to verify”、 “to ensure” 等意图叙述替代操作。
- wait step 不应隐藏独立 check action；但如果等待时间本身是时序验证的一部分，可以包含对应 expected result。
- set、wait、check、restore 应尽量拆分为独立步骤。
- 不在本维度评价 signal、threshold、timing、DTC 是否有依据；这些归 `information_integrity`。

---

# 4. observability — 可观测性

评价单条 case 的 expected result 和验证步骤是否指向明确的可观察对象，使 HIL 系统、测试工具或工程师能够采集、记录和检查测试结果。

该维度关注“有没有可观察证据”，而不是“pass/fail 标准是否完整”。
`pass_fail_clarity` 评价判定条件是否明确；`observability` 评价结果是否能通过 signal、state、DTC、diagnostic status、log、trace、measurement 或 report 被观察到。

| 分值 | 描述 |
|------|------|
| **1** | 基本不可观测。expected result 为空，或只包含完全模糊描述，例如 “system works correctly”“behaves as expected”“fault is handled”，没有任何可观察对象。 |
| **2** | 可观测性较弱。只有少量 expected result 指向可观察对象；多数关键验证点缺少 signal、state、DTC、diagnostic status、log、trace 或 measurement；执行者需要自行判断应观察什么。 |
| **3** | 基本可观测。主要验证点有可观察对象或观察方向，但部分 expected result 仍较泛，例如只写 “fault detected”“status changes”“response is correct”，没有明确说明观察对象或证据来源。 |
| **4** | 可观测性较好。关键 expected result 基本都指向明确的观察对象或观察证据类型，例如 signal、flag、state、DTC、diagnostic status、log、trace 或 measurement；当具体对象缺失时，能用 `[NEEDS REVIEW]` 清楚标出需要补充的证据类型。 |
| **5** | 高度可观测。每个关键验证点都有具体且有依据的可观察对象和证据来源；expected result 能直接映射到已知 HIL measurement、ECU signal、diagnostic state、bus trace、log 或 test report metric；无泛泛描述、无主观判断、无无依据的伪具体信号。 |

### Typical Observable Evidence in BMS HIL Cases

- ECU internal or exposed signal
- BMS state / mode
- fault flag / warning flag
- diagnostic event / DTC status
- CAN / LIN / Ethernet bus signal or message status
- contactor command or feedback status, if safely simulated or observable
- voltage / current / temperature measurement in the simulated plant model
- fault memory / diagnostic log
- HIL measurement trace
- test report metric

### Notes

- 如果可观测对象来自 requirement / context，`observability` 可以达到 5。
- 如果可观测对象缺失，但用 `[NEEDS REVIEW]` 清楚标出需要哪类证据，`observability` 可以达到 3-4。
- 如果可观测对象缺失且未标 `[NEEDS REVIEW]`，`observability` 最高不应超过 3。
- 如果 case 编造了未提供的 signal、DTC、CAN message、HIL channel 或工具命令，即使 expected result 看起来具体，`observability` 最高不应超过 3。
- 如果 expected result 只写 “works correctly”“fault handled”“behaves as expected”，`observability` 应为 1-2。

---

# 5. pass_fail_clarity — 通过/失败判定清晰度

评价单条 case 是否提供明确、客观、可复现的通过/失败判定条件。

该维度关注“看到结果后，如何判断 pass/fail”。
`observability` 评价是否知道观察什么；`pass_fail_clarity` 评价是否知道观察到什么算通过或失败。

| 分值 | 描述 |
|------|------|
| **1** | 几乎无法判断 pass/fail。expected result 为空、模糊，或只写 “works correctly”“behaves as expected”“responds normally”等主观描述。 |
| **2** | 有部分检查点，但缺少明确判定值、状态、比较条件、时间窗口或允许范围；执行者需要自行解释通过标准。 |
| **3** | 主要验证点具备基本 pass/fail 判断，例如某状态 active / inactive、某 flag set / not set；但部分条件仍不完整，例如缺少时间条件、前后状态、容差或边界判定。 |
| **4** | 大部分 expected result 都有明确判定条件；执行者基本可以根据记录结果判断 pass/fail，仅有少量边界表达、时间窗口或组合条件需要完善。 |
| **5** | 每个关键验证点都有明确、客观、可复现的 pass/fail criteria；判定条件与 requirement 语义一致，包含必要的值、状态、比较关系、时间窗口或允许范围；无主观词和模糊判断。 |

### Examples

Low clarity:

- Expected: BMS responds correctly.
- Expected: Fault is handled.
- Expected: Status changes.

Higher clarity:

- Expected: Overvoltage detection status becomes active.
- Expected: Fault remains inactive before configured debounce time.
- Expected: Warning flag is set within configured confirmation time.

Best clarity when supported by context:

- Expected: `BMS_CellOV_Flag = 1` within `t_CellOV_Debounce`.
- Expected: `DTC_CellOV` status = active after configured confirmation time.
- Expected: Fault status remains inactive for voltage below threshold.

### Notes

- `pass_fail_clarity` 可以因为缺少 threshold、timing 或 signal 而受限。
- 如果缺失信息被 `[NEEDS REVIEW]` 标出，仍可获得中等分，但通常不应达到 5。
- 5 分要求关键判定条件具体且有依据。
- 不要把 “check a signal” 当作 pass/fail criteria；必须说明期望状态、值、变化或比较关系。

---

# 6. information_integrity — 信息完整性与不脑补

评价单条 case 是否忠实使用输入 requirement、retrieved context 和已知 test basis 中的信息；当关键信息缺失时，是否用 `[NEEDS REVIEW]` 诚实标注，而不是编造 signal、threshold、timing、state、observation、DTC、CAN message、HIL channel 或工具命令。

该维度关注“信息是否有依据”，而不是“步骤是否能执行”或“结果是否能观察”。
Marker syntax and allowed field placement are deterministic validation concerns. This dimension focuses on whether missing semantic information is honestly identified and unsupported facts are avoided.

| 分值 | 描述 |
|------|------|
| **1** | 信息完整性很差。case 把缺失信息直接写成确定事实，例如编造具体 signal name、threshold value、timing value、DTC、CAN message、HIL channel、工具命令或平台能力；关键测试条件缺乏依据且未标注 `[NEEDS REVIEW]`。 |
| **2** | 存在明显不可靠信息。部分关键值或对象没有依据但被写成事实；或遗漏多个必要的 `[NEEDS REVIEW]`，导致执行者可能误以为这些信息已经确认。 |
| **3** | 基本诚实处理缺失信息。主要语义缺口已用 `[NEEDS REVIEW]` 标注，但仍有个别遗漏、过度标注，或对已知信息与未知信息的边界表达不够清楚。 |
| **4** | 信息完整性较好。已知 requirement / context 中的信息被正确使用；缺失的 signal、threshold、timing、state 或 observation 基本都被准确标注；没有明显编造，只存在少量边缘不确定点。 |
| **5** | 信息完整性很高。所有关键测试信息都能追溯到 requirement、retrieved context 或明确 test basis；所有缺失语义都被精确标注为 `[NEEDS REVIEW]`；不多标、不漏标、不伪造；不会使用未提供的 HIL 通道名、工具命令、DTC、CAN message 或平台能力。 |

### Typical Information Gaps

- signal / interface：缺失可设置或可观测的信号、接口、状态变量、诊断状态
- threshold / calibration：缺失阈值、标定参数、边界条件、容差
- timing：缺失 debounce time、confirmation time、timeout、采样或等待时间
- state / mode：缺失 BMS state、operation mode、charging / discharging / rest state、fault state
- observation / evaluation target：缺失 expected result 应检查的 flag、DTC、status、log、trace、metric
- environment / capability assumption：缺失 HIL/SIL/bench/tool capability 时，不得假设某工具命令、HIL channel 或平台能力存在

### Notes

- `information_integrity` 不评价步骤好不好执行；步骤粒度、set/wait/check 是否拆分，归 `executability`。
- `information_integrity` 不评价 expected 是否足够可观测；expected 是否能通过 signal/log/DTC/status 判断，归 `observability`。
- 缺失信息不等于低质量；当 requirement 本身缺少阈值、信号或时序时，正确使用 `[NEEDS REVIEW]` 反而应提高 `information_integrity` 分。
- “写得很具体”不等于“信息完整”；无依据的具体值或具体信号名应被视为信息完整性问题。

---

# 7. state_and_environment_control — 状态与测试环境控制

评价单条 case 是否清楚描述执行前、执行中、执行后的 BMS/HIL 状态控制，包括 preconditions、test environment assumptions、initial state、state transition、restore/reset 行为。

该维度关注“测试执行是否处于受控状态”。
`executability` 评价步骤能否执行；`state_and_environment_control` 评价执行前后系统和测试环境是否清楚、稳定、可恢复。

| 分值 | 描述 |
|------|------|
| **1** | 几乎没有状态或环境控制。无法判断 SUT 初始状态、BMS mode、HIL 配置、仿真状态或执行后如何恢复。 |
| **2** | 有零散 precondition 或 restore 描述，但关键状态缺失；执行者需要自行假设 BMS state、仿真模型状态、故障状态或故障清除方式。 |
| **3** | 基本说明初始状态和部分恢复行为，但 environment、state transition、fault injection state、postcondition 或 reset 行为不够完整。 |
| **4** | 状态与环境控制较好。preconditions、environment assumptions 和 restore/reset 行为基本清楚；测试过程中系统状态可控，仅有少量细节需人工确认。 |
| **5** | 状态与环境控制完整且一致。初始状态、测试环境、状态转换、故障注入/清除、restore/reset 和 postcondition 都清楚；case 执行后 SUT/HIL 回到安全、受控、可继续测试的状态。 |

### Typical State / Environment Items

- BMS operation mode
- SUT initialized / observable / controllable
- HIL model loaded and stable
- Required signals / measurements available
- Communication or diagnostic interface available
- Fault injection state, if simulated
- Initial voltage / current / temperature condition, if provided by context
- Restore modified inputs
- Clear simulated faults
- Return SUT / HIL to safe and controlled state

### Notes

- 不要求 AI 编造具体 bench configuration。
- 如果 environment 或 state 信息缺失，应使用 `[NEEDS REVIEW]`，不要假设具体 HIL channel、tool command 或平台能力。
- precondition 应描述状态；如果需要执行动作，应放入 steps。
- postcondition 应描述恢复后状态，不应暗示真实危险操作。

---

# 8. automation_readiness — 自动化转写友好度

评价单条 case 是否结构稳定、步骤原子化、字段清晰，适合后续转换为自动化脚本、测试规程或结构化测试资产。

该维度关注“能不能低成本转写为 AutomationDesk、ECU-TEST、Python、内部测试框架或其他结构化测试资产”。
它不评价测试意图是否正确，也不评价覆盖是否充分。

| 分值 | 描述 |
|------|------|
| **1** | 自动化转写价值很低。内容主要是自然语言段落，结构混乱，字段边界不清，难以转成自动化步骤。 |
| **2** | 有基本结构，但步骤粒度不稳定、action/expected 混用、多个动作合并、字段职责混乱，自动化转写成本高。 |
| **3** | 结构基本稳定，主要步骤可转写，但仍需要人工拆分动作、补全字段、统一表达或清理叙述性内容。 |
| **4** | 自动化转写友好。字段清楚，步骤原子化程度较好，action/expected 边界清晰，set/wait/check/restore 结构稳定；适合低成本转成自动化脚本。 |
| **5** | 高度自动化友好。case 高度结构化、原子化、表达一致；每步职责单一，字段边界清晰，缺失信息显式占位；可直接进入自动化转写或测试资产管理流程，仅需少量人工 review。 |

### Notes

- `automation_readiness` 不等于 `executability`。
- `executability` 评价工程师能不能执行。
- `automation_readiness` 评价机器或脚本生成器能不能稳定转写。
- 简洁、一致、原子化的表达应获得更高分。
- 大段自然语言、混合动作和期望、字段职责混乱会降低该分数。

---

# Scoring Principles — 评分原则

## 1. 维度独立，但允许合理关联

每个维度应根据自己的评分焦点评分。

同一条 case 可以出现：

- `requirement_alignment = 5`
- `executability = 4`
- `observability = 3`
- `information_integrity = 5`

这表示：case 测对了需求，也比较可执行，但可观测对象还需要补充。

同一条 requirement 可以出现：

- case-level 平均质量较高
- `coverage_value = 3`

这表示：已有 cases 质量尚可，但整组 cases 的覆盖互补性仍不足。

---

## 2. 不要机械计数 checklist item

评分应基于工程语义判断，不是字符串匹配。

例如：

- action 超过 15 词不一定低分，关键看是否原子化、清晰、可执行。
- expected result 没有具体 signal name 不一定低分，关键看是否明确指出需要哪类可观察证据。
- 出现多个 `[NEEDS REVIEW]` 不一定低分，关键看它们是否准确标注真实缺口。

---

## 3. 存疑取下限

如果评分在两档之间犹豫，取较低分，并在 note 中说明原因。

示例：

- score: 3
- note: The case is mostly executable, but several actions still mix intent description with operation.

---

## 4. requirement_alignment 与 coverage_value 分离

- `requirement_alignment` 评价单条 case 是否测对当前 requirement。
- `coverage_value` 评价同一 requirement 下整组 cases 是否形成有价值的覆盖。

不要因为 case set 覆盖不完整，就降低某条本身聚焦且正确的 case 的 `requirement_alignment`。
但如果多条 cases 都跑题，即使数量很多，`coverage_value` 也不应高。

---

## 5. observability 与 pass_fail_clarity 分离

- `observability` 评价是否知道“看什么”。
- `pass_fail_clarity` 评价是否知道“看到什么算通过/失败”。

示例：

- Expected: Check `BMS_CellOV_Flag`.

可能评分：

- `observability = 4`
- `pass_fail_clarity = 2`

原因：有观察对象，但缺少期望值。

---

## 6. information_integrity 与 observability 的关系

信息缺失会限制 `observability` 的上限，但不应导致重复扣分。

- 已知具体观察对象：`observability` 可到 5。
- 缺失但用 `[NEEDS REVIEW]` 标出观察证据类型：`observability` 可到 3-4。
- 缺失且未标 `[NEEDS REVIEW]`：`observability` 最高不应超过 3。
- 编造观察对象：`observability` 最高不应超过 3，`information_integrity` 应低分。

---

## 7. 缺失信息不等于低质量

AI 生成 draft test case 时，诚实暴露未知信息比编造完整内容更好。

高质量写法：

- Expected: `[NEEDS REVIEW]` overvoltage detection status becomes active.

低质量写法：

- Expected: `BMS_CellOV_L3_Flag = 1`.

如果 `BMS_CellOV_L3_Flag` 没有来自 requirement/context，它虽然看起来具体，但属于无依据编造。

---

# Suggested Weights — 建议权重

如果需要计算 weighted score，可使用以下权重：

```yaml
weights:
  requirement_alignment: 20
  information_integrity: 20
  executability: 15
  observability: 15
  pass_fail_clarity: 10
  coverage_value: 10
  state_and_environment_control: 5
  automation_readiness: 5
```

计算方式示例：

```text
per_requirement_score =
  avg(requirement_alignment) * 0.20
+ avg(information_integrity) * 0.20
+ avg(executability) * 0.15
+ avg(observability) * 0.15
+ avg(pass_fail_clarity) * 0.10
+ coverage_value * 0.10
+ avg(state_and_environment_control) * 0.05
+ avg(automation_readiness) * 0.05

run_score =
  average(per_requirement_score for all evaluated requirements)
```

其中：

- `coverage_value` 是 requirement-level 分数，不按 case 重复计入。
- 其他 7 个维度先在同一 requirement 下的 cases 上取平均。
- 代码层可以额外记录关键维度最低分，例如 `requirement_alignment_min`、`information_integrity_min`、`executability_min`、`observability_min`。

---

# Recommended Evaluator Output Format

LLM evaluator 应输出结构化评分。
不要输出 `overall_score`。
不要输出最终 `decision`。
代码层负责权重计算、平均分、hard gates 和最终接受规则。

示例：

```json
{
  "requirements": [
    {
      "requirement_key": "REQ-BMS-OVP-002",
      "coverage_value": 4,
      "coverage_value_note": "The case set covers trigger and no-trigger paths, but boundary timing is not split.",
      "cases": [
        {
          "case_index": 0,
          "case_title": "Overvoltage detection at threshold",
          "requirement_alignment": 5,
          "requirement_alignment_note": "The case is clearly aligned with the overvoltage detection requirement.",
          "executability": 4,
          "executability_note": "The set-wait-check flow is executable, but restore behavior could be clearer.",
          "observability": 3,
          "observability_note": "The expected result identifies the detection status but lacks a concrete observable signal.",
          "pass_fail_clarity": 3,
          "pass_fail_clarity_note": "Expected activation is clear, but the timing criterion is still marked as [NEEDS REVIEW].",
          "information_integrity": 5,
          "information_integrity_note": "Missing signal and timing information are marked instead of invented.",
          "state_and_environment_control": 4,
          "state_and_environment_control_note": "Initial state is mostly clear; postcondition could specify fault clearing more explicitly.",
          "automation_readiness": 4,
          "automation_readiness_note": "Steps are mostly atomic and suitable for downstream conversion."
        }
      ]
    }
  ]
}
```

Output rules:

- Return only a JSON object.
- Output every requirement from the input.
- Output every case under its requirement. Do not skip any case.
- Every score must be an integer from 1 to 5.
- Every score must have a corresponding `_note` field.
- Notes should be concise and explain the main reason for the score.
- If a dimension scores below 3, the note must clearly state the main flaw.