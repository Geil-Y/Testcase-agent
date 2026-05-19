# Testcase-agent

Python 自动化测试智能体项目。基于本地 LLM（7B-8B）从结构化需求生成 BMS HIL 测试用例。

## 核心理念

- **代码 = 流程骨架** — 提供 pipeline 编排、provider 抽象、质量门、I/O
- **Prompt = 灵魂** — 覆盖维度推断、case 写作哲学、领域知识全部在独立 prompt 文件中
- **LLM 一次只做一件事** — 小模型约束下，每次调用任务单一、prompt 精干
- **创建新文件前，必须向用户确认目标路径**

## Agent skills

### Issue tracker

GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses five canonical labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — CONTEXT.md at root, ADRs under docs/adr/. See `docs/agents/domain.md`.

### Git commit

提交时使用 `git-commit` skill，遵循 Conventional Commits 规范（`<type>[scope]: <description>`）。

| Type | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 仅文档变更 |
| `style` | 格式/样式，无逻辑变更 |
| `refactor` | 重构（无功能变更/修复） |
| `perf` | 性能优化 |
| `test` | 添加/更新测试 |
| `build` | 构建系统/依赖 |
| `ci` | CI/配置变更 |
| `chore` | 维护/杂项 |
| `revert` | 回滚提交 |

**规则：**
- 一次一个逻辑变更，禁止大锅饭提交
- description 用祈使语气、现在时（"add" 而非 "added"），不超过 72 字符
- 破坏性变更用 `!` 标记（如 `feat!:`）或 `BREAKING CHANGE:` footer
- 如有关联 issue，footer 中引用 `Closes #N` / `Refs #N`
- 禁止提交 secrets（.env、credentials.json 等）
- 禁止 `--force` / `--no-verify`，除非用户明确要求
- 禁止修改 git config
