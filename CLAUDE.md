# Testcase-agent

Python 自动化测试智能体项目。基于本地 LLM（7B-8B）从结构化需求生成 BMS HIL 测试用例。

## 核心理念

- **代码 = 流程骨架** — 提供 pipeline 编排、provider 抽象、质量门、I/O
- **Prompt = 灵魂** — 覆盖维度推断、case 写作哲学、领域知识全部在独立 prompt 文件中
- **LLM 一次只做一件事** — 小模型约束下，每次调用任务单一、prompt 精干

## Agent skills

### Issue tracker

GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses five canonical labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — CONTEXT.md at root, ADRs under docs/adr/. See `docs/agents/domain.md`.
