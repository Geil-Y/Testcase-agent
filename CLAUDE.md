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

### ADR 触发条件

以下任一发生时，AI 应向用户提议是否写 ADR（不自动写，最终决定权在用户）：

- 新增包/依赖（改动 `pyproject.toml` dependencies）
- 新增或删除顶层目录（`src/`、`tests/`、`prompts/` 等同级目录）
- 新增架构约束规则到 `CLAUDE.md` 本身
- 管道流程变更（pipeline 阶段增删、LLM 调用顺序调整）
- 用户在设计讨论中明确做了二选一决策

ADR 格式：遵循 `docs/adr/` 下已有风格，~5 行即可，重点记录**当时为什么这么选**，而非描述现状。

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

## Testing Discipline

- ALWAYS run the full test suite and confirm all tests pass before declaring work complete or making a commit. Never rely on assumptions about test coverage — verify.
- Before committing, trace the full call chain from entry point through every integration/wiring layer to verify no parameter is dropped, no signature is mismatched, and no provider path is left unhandled.
- When writing or updating tests, verify they actually exercise the real code path (no false positives that pass without reaching the new logic).

## Scope Discipline

- When a user explicitly asks for ANALYSIS ONLY (e.g., "analyze and plan", "diagnose root cause", "just explain"), DO NOT edit any files. Summarize your findings and ask for confirmation before making any changes.
- If you are mid-analysis and discover a potential fix, present it as a recommendation — do not apply it automatically.

### Prompt-Only vs Code Changes

- When the user says "just change the prompts, not the code" or "revert the code changes," respect that boundary absolutely. Do not add programmatic enforcement, validation layers, or helper functions in code unless the user explicitly requests it.
- Prompt-driven logic changes should stay in prompt files (`.md`, template strings, prompt constants).

## Before Proposing a Solution

- Before designing a complex solution or jumping to implementation, first validate that the problem actually needs solving in the user's context. Ask clarifying questions when requirements are unclear.
- For architectural redesign discussions, explore alternatives and tradeoffs before writing proposal documents.
