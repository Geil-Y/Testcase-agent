---
name: scoring-rubrics
description: BMS HIL 测试用例 4 维评分标准 — 供 LLM 评估器使用
status: draft
created: 2026-05-20
---

# BMS HIL 测试用例 4 维评分标准

每个维度 1-5 分。3 分为及格基线——case 基本可用但有改进空间。

---

## executability — 可执行性

每个 step 能否被 HIL 操作员直接执行？

| 分值 | 描述 |
|------|------|
| **1** | 步骤缺失或为空；凭空编造数值（4.2V、500ms）替代参数名；缺失 signal/threshold/timing/state/observation 却未标注 [NEEDS REVIEW]；action 写成了意图叙述长段落 |
| **2** | 基本结构存在但多项硬伤：[NEEDS REVIEW] 带 category 后缀、放在 title/objective 等错误位置、set 和 wait 合并为一步、action 超 15 词 |
| **3** | 步骤结构正确，每步一个操作；set→wait→verify 分离；[NEEDS REVIEW] 格式和位置基本正确；但部分 action 含 "in order to" / "to verify" 等意图叙述 |
| **4** | 所有步骤可直接执行；action 只描述操作无叙述；[NEEDS REVIEW] 仅放在 action/expected 且格式正确；少量次要项可改进（如 expected 拼在了 wait 步上） |
| **5** | 所有步骤对 HIL 操作员可直接执行；每个 action ≤15 词且纯操作；set/wait/verify 完整分离；[NEEDS REVIEW] 精确覆盖需要的五类语义缺失且仅出现在 action/expected；所有值使用已知参数名无发明 |

## observability — 可观测性

Expected result 是否具体且可被 HIL 系统检查？

| 分值 | 描述 |
|------|------|
| **1** | 所有 expected 为 null/空；或包含完全模糊描述（"system works correctly"、"behaves as expected"） |
| **2** | 仅个别 expected 有内容但模糊（"response is correct"、"fault detected"）；关键验证点未放 expected |
| **3** | 关键步骤有 expected 但部分不够具体：如仅写 "!= null"、"set/not set" 未说明具体字段；expected 放在 wait 步等非观测步骤 |
| **4** | 所有关键观测步骤 expected 具体且 signal-oriented；wait 步 expected 为 null；无段落式 expected |
| **5** | 每条 expected 具体到信号名+期望值（如 `BMS_CellOV_Flag := 1`）；用 & 连接多条件简洁清晰；每条 ≤15 词；仅关键验证点有 expected；所有可观测检查点正确覆盖 |

## coverage_value — 覆盖价值

本条 case（及其兄弟 case）是否提供了有意义的覆盖？

| 分值 | 描述 |
|------|------|
| **1** | 单条 case 测试多个不相关行为（如同时验证过压和欠温）；未匹配任何 coverage dimension；触发/不触发等价类完全缺失 |
| **2** | case 勉强匹配声明的 coverage dimension，但内容偏离（如 boundary 维度的 case 只测了 normal）；或合并了多个阈值场景 |
| **3** | case 正确覆盖声明的 dimension；对阈值判定覆盖了「触发」但缺「不触发」等价类（或反过来）；边界值未拆分「恰好触发」和「恰好不触发」 |
| **4** | 触发/不触发等价类均有对应 case；边界值拆分到位；单行为聚焦正确；但参数阈值和时序阈值未正交拆分 |
| **5** | 完整等价类覆盖（触发+不触发）；边界值拆分为恰好触发/恰好不触发；参数阈值和时序阈值正交独立拆分；每条 case 仅验证一个需求的一个行为 |

## missing_information_detection — 缺失信息识别

语义缺口是否被 [NEEDS REVIEW] 正确识别和标注？

| 分值 | 描述 |
|------|------|
| **1** | 应标 [NEEDS REVIEW] 的部位凭空编造了数值或信号名；NEEDS REVIEW 带 category 后缀（[NEEDS REVIEW: timing]）；NEEDS REVIEW 出现在 title/objective/precondition/postcondition |
| **2** | 遗漏了多个语义缺口未标 NEEDS REVIEW（如时序缺失但 Wait 步无 NEEDS REVIEW）；或写了不存在的信号名假装满足需求 |
| **3** | 主要语义缺口已标 NEEDS REVIEW 但个别遗漏（如 observation 缺失未标）；或需求语义完整却添加了不必要的 NEEDS REVIEW |
| **4** | 五类语义缺口（signal/threshold/timing/state/observation）正确识别并标注；NEEDS REVIEW 裸格式、位置正确；仅边缘 case 有少量 over-flagging |
| **5** | 所有语义缺口精确识别——不多标（需求已有则不用 NEEDS REVIEW）、不漏标（需求缺失则必有占位）；NEEDS REVIEW 仅放在需要该值的 action/expected 字段中；完全不依赖 HIL 通道名/工具命令等非五类语义 |

## 评分原则

- **3 分 = 及格基线** — case 基本可用但有改进空间
- **整体判断** — 每个维度内综合评价，不要机械计数 checklist item
- **维度独立** — 一个 case 可以 executability=5 但 coverage_value=1
- **存疑取下限** — 两档间犹豫时取较低分，并在 note 中说明原因
- **不机械字符串匹配** — 语义判断，不是字符串比对
