# Optimization Run Protocol

## 流程总览

```
Phase 2 (一次性)
├── 1. 生成 checklist_v1.md → 人工审核
├── 2. 冒烟测试 CLI 脚本是否可运行
└── 3. 确认评估流程可用

Phase 3 (迭代循环)
└── for round in 1..5:
    ├── ① 采样 20 条需求
    ├── ② 保存本轮 prompts → prompts/
    ├── ③ 运行 CLI → generated_cases.json
    ├── ④ Claude Code 逐项评估 → evaluation_report.html
    ├── ⑤ 如果通过率 ≥ 90% 或 round == 5: 终止
    └── ⑥ Claude Code 分析失败项 → 修改 prompts → 下一轮
```

## 目录结构

```
optimization_runs/
├── checklist_v1.md                         # 初始 checklist（Phase 2 产物）
├── README.md                               # 本文件
└── run_YYYYMMDD_HHMMSS/
    ├── round_01/
    │   ├── prompts/                        # 本轮使用的 prompt 文件
    │   │   ├── analyze_and_plan.system.md
    │   │   ├── analyze_and_plan.user.md
    │   │   ├── generate_case.system.md
    │   │   └── generate_case.user.md
    │   ├── sampled_requirements.json       # 本轮抽到的 20 条需求
    │   ├── summary.json                    # 生成汇总
    │   ├── generated_cases.json            # 所有生成结果
    │   └── evaluation_report.html          # 评估报告（中文 HTML）
    ├── round_02/
    │   └── ...
    ├── ...
    └── final_summary.html                  # 最终汇总报告
```

## 评估协议

评估者: Claude Code (不是 7B 本地模型)

评估输入:
1. `checklist_v1.md` — 55 个检查项
2. `generated_cases.json` — 本轮生成的所有 case数据

评估过程:
对每个检查项，评估其是否适用于每个 case。如果一个检查项在 N 个 case 中都通过，该检查项通过率为 N/总case数 × 100%。
如果一个 case 在某项检查上失败，记录具体失败原因和 case 详情。

评估输出: `evaluation_report.html` (中文报告)

## Prompt 修改协议

Claude Code 全自动执行，但需遵守以下约束:

1. **保持架构** — 不改变 LLM#1 → LLM#2 的两阶段结构
2. **保持输出格式** — HTML 输出格式不变
3. **Token 预算**:
   - analyze_and_plan.system: ≤ 800 tokens
   - generate_case.system: ≤ 1200 tokens
4. **修改策略** — 优先强化被忽略的规则（在 prompt 末尾重复关键约束），
   而非添加新规则
5. **U-shaped attention** — 最重要的约束放在 system prompt 的前部和后部
6. **不引入矛盾** — 新增规则不能与已有规则冲突
7. **压缩冗长表达** — 用紧凑语言替换啰嗦表述
8. **记录变更** — 每轮 prompt 修改后生成 diff
