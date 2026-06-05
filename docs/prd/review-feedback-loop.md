# PRD: Review 反馈循环 — Accept / Edit / Regenerate

**Status:** Draft
**Date:** 2026-06-05
**Related ADR:** [ADR-0007](../adr/0007-review-feedback-loop.md)

---

## Problem Statement

当前 Pipeline Console 的 review 功能本质上是一个**闸门**：人在每个 LLM 阶段（A/B/C）结束后可以查看输出、编辑内容，然后点"Advance"进入下一阶段。但人的 review 意见**完全不参与 LLM 的决策循环**——Regenerate 按钮在 UI 上存在但未接线，Accept 按钮也是视觉占位。哪怕 Run 创建时勾选了 `review_required`，review 也只是暂停了流水线，没有提供任何反馈机制。

这意味着：
- 人对 LLM-A 的提取结果不满意，只能手动改，不能写意见让 LLM 重新提取
- 人对 LLM-B 的意图规划不满意，只能手动删，不能写意见让 LLM 重新规划
- 人无法"确认"一个阶段的输出是权威的——Accept 按钮不起作用
- 人对上游数据修改后，下游不会感知到变更

## Solution

将 review 从"闸门"升级为**交互式反馈循环**，核心是三个标准动作：

| 动作 | 含义 | 适用阶段 |
|---|---|---|
| **Accept** | 整体确认当前阶段输出为权威，锁定数据，允许 advance | A / B / C |
| **Edit** | 直接手动修改内容，改完即生效 | A / B / C |
| **Regenerate** | 写一段必填的 review comment 说明问题，让 LLM 带着反馈重新生成 | A / B |

关键行为规则：
- Accept 是 advance 的硬前置条件——未 Accept 不允许推进
- Accept 后数据锁定，要修改必须先 Unlock
- Unlock 上游阶段 → 下游全部数据标记为 stale，必须重新运行
- Regenerate 时 comment 必填，comment 作为最高优先级注入 prompt
- LLM-B 整体 Regenerate 最多 3 次，超限进入 Force Edit 状态（禁用 Regenerate，必须手动处理）
- LLM-B 每次 Regenerate 保留历史版本（version 号递增），UI 可查看历史
- `review_required` 配置语义不变——未勾选的阶段自动 Accept，直通下游

## User Stories

### Accept 相关

1. 作为 reviewer，我希望在检查完 LLM-A 的全部 test basis items 后，点击一次"Accept"按钮来整体确认，这样我就不需要逐条点击确认。
2. 作为 reviewer，我希望 Accept 之后所有 item 被锁定，防止误触修改，这样我可以安心地推进到下一阶段。
3. 作为 reviewer，我希望在没有 Accept 的情况下点击 Advance 时，系统提示我"请先 Accept 当前阶段"，这样我不会意外跳过 review。
4. 作为 reviewer，如果 Run 创建时某个阶段没有被勾选为 `review_required`，该阶段应自动 Accept，我不需要手动操作。

### Unlock 相关

5. 作为 reviewer，我希望 Accept 之后可以点击"Unlock"按钮来取消 Accept，这样我可以在 advance 之前回头修改内容。
6. 作为 reviewer，当我在 LLM-C 阶段 Unlock LLM-A 时，系统应弹出确认对话框警告我"此操作将使下游所有 intent 和 case 标记为 stale，需要重新生成"，防止我误操作。
7. 作为 reviewer，确认级联作废后，下游 LLM-B 的 intent 和 LLM-C 的 case 应全部标记为 stale，Run 状态回退到 LLM-A pending。

### Edit 相关

8. 作为 reviewer，我可以在 LLM-A 阶段编辑任意 test basis item 的 content、status、need 字段，修改后自动生效，不需要额外确认。
9. 作为 reviewer，我可以在 LLM-B 阶段删除不满意的 intent，删除操作视为 Edit，不影响整体 Accept。
10. 作为 reviewer，我可以在 LLM-C 阶段编辑任意 case 的 title、objective、precondition、postcondition、steps，修改后自动生效。

### Regenerate 相关（LLM-A）

11. 作为 reviewer，在 LLM-A 阶段我可以对某条不满意的 item 点击 Regenerate，写一段 comment 说明问题，LLM-A 会重新生成整个 test basis（以该 comment 为重点上下文），然后将新结果覆盖到当前 item 上。
12. 作为 reviewer，LLM-A 的 Regenerate 不对次数设上限，但我预期它的使用频率很低（大部分情况下直接 Edit 更快）。

### Regenerate 相关（LLM-B）

13. 作为 reviewer，在 LLM-B 阶段我对整体 intent plan 不满意时，可以点击 Regenerate，写一段总 comment 说明问题（如"应该多关注故障保护场景"），LLM-B 会根据我的意见重新规划全部 intent。
14. 作为 reviewer，Regenerate 时 comment 是必填的——如果我没写 comment 就提交，系统应提示"请填写驳回原因"。
15. 作为 reviewer，LLM-B 每次 Regenerate 后旧版本会被保留（version 号递增），我可以通过"查看历史"按钮浏览之前所有的 intent plan 版本。
16. 作为 reviewer，当 LLM-B Regenerate 达到 3 次上限后，系统进入 Force Edit 状态：Regenerate 按钮被禁用，我只能手动编辑/删除 intent，但 Accept 按钮仍然可用。
17. 作为 reviewer，在 Force Edit 状态下我可以手动调整 intent plan 直到满意，然后 Accept 并 advance。

### 审计相关

18. 作为 reviewer，我希望所有的 Accept、Unlock、Regenerate、Edit 操作都有记录（谁、什么时候、什么操作、什么 comment），这样后续可以追溯评审历史。

### Advance 相关

19. 作为 reviewer，当我 Accept 了当前阶段并点击 Advance 后，系统运行下一个 LLM 阶段，新生成的输出 review_status 为 pending，等待我的 review。
20. 作为 reviewer，当连续的后续阶段都是 auto-approve（未勾选 review_required）时，Advance 应该自动链式运行直到下一个需要 review 的阶段或结束。

### 状态可见性

21. 作为 reviewer，我需要在 UI 上清晰看到每个阶段的当前状态：pending（等待 review）、accepted（已确认锁定）、force_edit（超限手动模式）、stale（上游变更导致过期）。
22. 作为 reviewer，在 LLM-B 的 Force Edit 状态下，我需要看到一个醒目的提示告诉我原因（"已超过 3 次 Regenerate 上限，请手动编辑"）。

## Implementation Decisions

### 模块划分

```
M1: Database Migration + Schema
M2: Review State Machine (新模块)
M3: Regenerate Runner (扩展现有 pipeline_runner)
M4: Regenerate Prompt 文件 (新建)
M5: API Router 扩展 (扩展现有 router)
M6: Advance 逻辑改造
M7: 前端 UI 改造
```

依赖关系: M1 → M2+M3+M4 → M5 → M6+M7

---

### M1 — Database Schema 变更

#### test_basis_items 表新增列

```sql
ALTER TABLE test_basis_items ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE test_basis_items ADD COLUMN review_comment TEXT;
ALTER TABLE test_basis_items ADD COLUMN regenerate_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE test_basis_items ADD COLUMN accepted_at TEXT;
```

`review_status` 可选值：`pending` | `accepted`
`accepted_at` 为 ISO 8601 时间戳，Accept 时写入

#### case_intents 表新增列

```sql
ALTER TABLE case_intents ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE case_intents ADD COLUMN review_comment TEXT;
ALTER TABLE case_intents ADD COLUMN regenerate_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE case_intents ADD COLUMN accepted_at TEXT;
ALTER TABLE case_intents ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
```

`review_status` 可选值：`pending` | `accepted` | `stale`
`version` 每次 LLM-B Regenerate 时递增，旧版本保留（不删除）

#### test_cases 表新增列

```sql
ALTER TABLE test_cases ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE test_cases ADD COLUMN accepted_at TEXT;
```

LLM-C 无 Regenerate，不需要 `review_comment` 和 `regenerate_count`

#### runs 表新增列

```sql
ALTER TABLE runs ADD COLUMN llm_a_accepted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE runs ADD COLUMN llm_b_accepted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE runs ADD COLUMN llm_c_accepted INTEGER NOT NULL DEFAULT 0;
```

布尔值：0 = 未 Accept，1 = 已 Accept。Accept 时置 1，Unlock 时置 0。

#### 新增 review_actions 审计表

```sql
CREATE TABLE IF NOT EXISTS review_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    stage TEXT NOT NULL,              -- 'a' | 'b' | 'c'
    action TEXT NOT NULL,             -- 'accept' | 'unlock' | 'edit' | 'regenerate'
    target_type TEXT,                 -- 'test_basis_item' | 'case_intent' | 'test_case' | 'stage'
    target_id INTEGER,                -- item/intent/case 的主键 id
    comment TEXT,                     -- review comment (Regenerate 时必填)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

每次 Accept / Unlock / Edit / Regenerate 都插入一条记录。

#### 数据迁移策略

已有数据库中的旧数据兼容：
- 已有 `test_basis_items`：`review_status = 'accepted'`（视为已被隐式确认）
- 已有 `case_intents`：`review_status = 'accepted'`，`version = 1`
- 已有 `test_cases`：`review_status = 'accepted'`
- 已有 `runs`：根据当前 `status` 推断 —— 如果 `status >= extraction_ready`，则 `llm_a_accepted = 1`；如果 `status >= intents_ready`，则 `llm_b_accepted = 1`；如果 `status >= cases_ready`，则 `llm_c_accepted = 1`

Migration 函数需要先检查列是否已存在（`PRAGMA table_info`），避免重复执行报错。

---

### M2 — Review State Machine

新建模块，纯逻辑函数，所有函数接受 `db: sqlite3.Connection` 参数。

#### 函数签名与行为

```python
def accept_stage(db: sqlite3.Connection, run_id: int, stage: str) -> None:
    """
    整体 Accept 某个 stage。
    - stage='a': 将所有 test_basis_items.review_status 设为 'accepted'，写入 accepted_at
    - stage='b': 将所有 case_intents.review_status 设为 'accepted'，写入 accepted_at
    - stage='c': 将所有 test_cases.review_status 设为 'accepted'，写入 accepted_at
    - 同时设置 runs.llm_{stage}_accepted = 1
    - 插入 review_actions 记录
    - 如 stage 已经 accepted，抛出 ReviewStateError
    """

def unlock_stage(db: sqlite3.Connection, run_id: int, stage: str, cascade: bool = False) -> dict | None:
    """
    取消 Accept，解锁 stage。
    - 将 runs.llm_{stage}_accepted 设为 0
    - 清除该 stage 所有 item 的 accepted_at
    - 如果 cascade=True（仅适用于 upstream unlock）：
      - 解锁 LLM-A 时：所有 case_intents 和 test_cases 的 review_status 设为 'stale'
      - 解锁 LLM-B 时：所有 test_cases 的 review_status 设为 'stale'
      - 同时重置下游的 llm_X_accepted 为 0
    - 插入 review_actions 记录
    - 如果 cascade 会产生下游影响，返回 {'cascade_warning': True, 'affected_intents': N, 'affected_cases': M}
      让调用方先给前端展示警告，前端确认后再次调用 unlock_stage(..., cascade=True)
    """

def check_cascade_impact(db: sqlite3.Connection, run_id: int, stage: str) -> dict:
    """
    预检查 unlock 的级联影响（不实际执行）。
    返回 {'has_downstream_data': bool, 'affected_intents': int, 'affected_cases': int}
    用于前端展示确认弹窗。
    """

def can_advance(db: sqlite3.Connection, run_id: int) -> tuple[bool, str | None]:
    """
    检查当前 stage 是否可以 advance。
    返回 (True, None) 或 (False, '当前阶段需要 Accept 后才能推进')
    根据 runs.status 确定当前 stage，然后检查对应的 review_required 和 llm_X_accepted。
    """

def can_regenerate_intents(db: sqlite3.Connection, run_id: int) -> tuple[bool, str | None]:
    """
    检查 LLM-B 是否可以 Regenerate。
    返回 (False, '已超过重试上限(3次)，请手动编辑') 当 regenerate_count >= 3。
    """

def get_stage_states(db: sqlite3.Connection, run_id: int) -> dict:
    """
    返回所有 stage 的当前 review 状态，前端用。
    {
        'a': {'status': 'accepted', 'can_accept': False, 'can_unlock': True},
        'b': {'status': 'force_edit', 'can_accept': True, 'can_unlock': False, 'can_regenerate': False},
        'c': {'status': 'pending', 'can_accept': True, 'can_unlock': False},
    }
    """

def record_action(db: sqlite3.Connection, run_id: int, stage: str, action: str,
                  target_type: str = None, target_id: int = None, comment: str = None) -> None:
    """插入一条 review_actions 记录。"""
```

#### LLM-B Regenerate 状态机

```
LLM-B 生成 v1
  │ review_status = 'pending', regenerate_count = 0
  │
  ├─ 人点 Regenerate (comment 必填)
  │   regenerate_count += 1
  │   LLM-B 重新生成 → v2 (旧 v1 保留不删)
  │   review_status 保持 'pending'
  │
  ├─ 再次 Regenerate
  │   regenerate_count += 1 → 2
  │   生成 v3
  │
  ├─ 第三次 Regenerate
  │   regenerate_count += 1 → 3
  │   生成 v4
  │
  ├─ 第四次点 Regenerate
  │   can_regenerate_intents() 返回 False
  │   review_status → 'force_edit'
  │   Regenerate 按钮禁用
  │
  └─ 人 Accept
      review_status → 'accepted'
      所有 version 中只有最新 version 的 intent 为 accepted
```

---

### M3 — Regenerate Runner

修改 `src/testcase_agent/console/pipeline_runner.py`。

#### 函数签名

```python
def regenerate_test_basis(
    db: sqlite3.Connection,
    run_id: int,
    item_id: int,
    comment: str,
    provider: LlmProvider,
) -> dict:
    """
    重新运行 LLM-A 整体提取，以 comment 为重点上下文。
    
    流程：
    1. 读取当前 test_basis_items 作为上下文
    2. 渲染 regenerate_test_basis_item.*.md prompt，注入：
       - original_requirement（原始需求文本）
       - previous_output（当前全部 test_basis_items）
       - review_comment（最高优先级标记）
       - focus_item_id（被驳回的那条 item）
    3. 调用 provider.complete(sys, usr)
    4. 解析 LLM-A 返回的完整 test basis
    5. 将新结果覆盖写入 test_basis_items（不是仅更新一条，是全量更新）
    6. 所有 item 的 regenerate_count 不变（LLM-A 不计上限）
    7. 插入 review_actions 记录（target_id=item_id）
    8. 返回新的 test basis
    """

def regenerate_case_intents(
    db: sqlite3.Connection,
    run_id: int,
    comment: str,
    provider: LlmProvider,
) -> dict:
    """
    重新运行 LLM-B 整体规划。
    
    流程：
    1. 调用 can_regenerate_intents() 检查是否超限
    2. 如果超限，将 case_intents.review_status 设为 'force_edit'，抛出 ReviewStateError
    3. 读取当前 test_basis_items（已人工审核的版本）
    4. 读取当前 intents 的 regenerate_count 和最新 version
    5. new_version = current_version + 1, new_count = current_count + 1
    6. 渲染 regenerate_case_intents.*.md prompt，注入：
       - test_basis（已审核的 extracted sections）
       - previous_intent_plan（当前最新版本的 intent plan）
       - review_comment（标记为最高优先级）
    7. 调用 provider.complete(sys, usr)
    8. 解析结果，INSERT 新 version 的 case_intents（version = new_version, regenerate_count = new_count）
    9. 旧 version 的 intent 保留不删
    10. 更新所有旧 version intent 的 review_status 为 'stale'（如果之前是 'pending'）
    11. 插入 review_actions 记录
    12. 返回新生成的 intent plan
    """
```

---

### M4 — Regenerate Prompt 文件

新建 4 个文件：

#### prompts/regenerate_test_basis_item.system.md

```
你是 BMS HIL 测试基础提取专家。你需要根据人工评审意见重新提取测试基础。

规则：
1. 人工评审意见的优先级最高，必须严格遵循
2. 原始需求文本作为上下文参考
3. 之前提取结果中与人工意见不矛盾的部分可以保留
4. 输出格式与初次提取完全一致
```

#### prompts/regenerate_test_basis_item.user.md

```
## 原始需求
{{ requirement_text }}

## 之前的提取结果
{{ previous_output }}

## 人工评审意见（最高优先级）
{{ review_comment }}

## 重点关注 Item
{{ focus_item_description }}

请根据人工评审意见重新提取完整的测试基础。特别关注上述"重点关注 Item"。
```

#### prompts/regenerate_case_intents.system.md

```
你是 BMS HIL 测试用例意图规划专家。你需要根据人工评审意见重新规划全部用例意图。

规则：
1. 人工评审意见的优先级最高，必须严格遵循
2. 测试基础（已由人工审核）是唯一的事实来源
3. 之前的意图规划仅供参考，无需保留
4. 输出格式与初次规划完全一致（JSON，包含 intents 列表和 coverage_dimension）
```

#### prompts/regenerate_case_intents.user.md

```
## 测试基础（已人工审核）
{% for section_name, items in test_basis.items() %}
### {{ section_name }}
{% for item in items %}
- [{{ item.status }}] {{ item.content }}{% if item.need %} → NEED: {{ item.need }}{% endif %}
{% endfor %}
{% endfor %}

## 上一次的意图规划（被驳回，仅供参考）
{{ previous_intent_plan }}

## 人工评审意见（最高优先级）
{{ review_comment }}

请根据人工评审意见重新规划全部用例意图。人工意见的优先级高于测试基础中的任何推断。
```

---

### M5 — API Router 扩展

修改 `src/testcase_agent/console/router.py`，新增以下端点：

#### POST /runs/{run_id}/accept/{stage}

- stage: `a` | `b` | `c`
- 调用 `accept_stage(db, run_id, stage)`
- 成功返回 200 `{"status": "accepted", "stage": stage}`
- 已 Accept 返回 409 `{"detail": "Stage already accepted"}`
- 有 item 处于 regenerating 状态返回 409 `{"detail": "Cannot accept: N item(s) still regenerating"}`

#### POST /runs/{run_id}/unlock/{stage}

- Query param: `cascade` (bool, default false)
- 如果 `cascade=false` 且存在下游数据，先调 `check_cascade_impact()`，返回 200 `{"cascade_warning": true, ...}` 让前端弹窗
- 前端确认后再次请求 `?cascade=true`，实际执行 unlock + 级联作废
- 成功返回 200

#### POST /runs/{run_id}/sections/{section}/items/{item_id}/regenerate

- 仅 LLM-A 阶段
- Body: `{"comment": "这条信号提取不对，应该是..."}` （必填）
- comment 为空返回 422 `{"detail": "Review comment is required for regenerate"}`
- 调用 `regenerate_test_basis(db, run_id, item_id, comment, provider)`
- 返回更新后的 test basis items

#### POST /runs/{run_id}/regenerate-intents

- 已有端点（line 269），需要改造
- Body: `{"comment": "整体方向偏了，应该多覆盖故障保护场景"}` （必填）
- comment 为空返回 422
- 调用 `regenerate_case_intents(db, run_id, comment, provider)`
- 超限返回 409 `{"detail": "Regenerate limit (3) exceeded. Stage is now in force_edit mode."}`

#### GET /runs/{run_id}/intents/history

- 返回所有版本的 case_intents，按 version 倒序
- Response: `{"versions": [{"version": 3, "intents": [...], "created_at": "..."}, ...]}`

#### GET /runs/{run_id}/review-state

- 调用 `get_stage_states(db, run_id)`
- 返回各 stage 的 review 状态，前端初始化工作区时调用

#### GET /runs/{run_id}/review-actions

- 返回该 run 的所有 review_actions 记录，按时间倒序

#### 改造 POST /runs/{run_id}/advance

- 开头加 `can_advance()` 检查
- 不满足返回 409 `{"detail": "当前阶段需要 Accept 后才能推进"}`

---

### M6 — Advance 逻辑改造

修改 `src/testcase_agent/console/advance.py`。

#### advance_run() 改造

```python
def advance_run(run_id: int, provider: LlmProvider, db: sqlite3.Connection) -> dict | None:
    run = get_run(db, run_id)
    status = run["status"]
    
    if status == "extraction_ready":
        # 检查 LLM-A 是否已 Accept（如果 review_required 包含 'a'）
        if run["review_llm_a"] == 1 and not run["llm_a_accepted"]:
            raise ReviewRequiredError("LLM-A stage requires Accept before advancing")
        
        run_llm_b(run_id, provider, db)
        # 更新 case_intents 的 review_status = 'pending', version = 1
        
        # Auto-chain: 如果 LLM-B 和 LLM-C 都不需要 review，自动跑到底
        if run["review_llm_b"] == 0 and run["review_llm_c"] == 0:
            run_llm_c(run_id, provider, db)
            return {"status": "cases_ready"}
        return {"status": "intents_ready"}
    
    if status == "intents_ready":
        # 检查 LLM-B 是否已 Accept
        if run["review_llm_b"] == 1 and not run["llm_b_accepted"]:
            raise ReviewRequiredError("LLM-B stage requires Accept before advancing")
        
        run_llm_c(run_id, provider, db)
        # 更新 test_cases 的 review_status = 'pending'
        
        if run["review_llm_c"] == 0:
            # Auto-accept LLM-C
            accept_stage(db, run_id, 'c')
            return {"status": "evaluated"}  # 或保持 cases_ready
        return {"status": "cases_ready"}
    
    if status == "cases_ready":
        if run["review_llm_c"] == 1 and not run["llm_c_accepted"]:
            raise ReviewRequiredError("LLM-C stage requires Accept before advancing")
        # 到 evaluation 或结束
        return {"status": "evaluated"}
```

#### cascade_stale_data() — 级联作废函数

```python
def cascade_stale_data(db: sqlite3.Connection, run_id: int, from_stage: str) -> None:
    """当上游 stage Unlock 时，作废下游所有数据"""
    if from_stage == 'a':
        # 作废 LLM-B 和 LLM-C
        db.execute("UPDATE case_intents SET review_status = 'stale' WHERE run_id = ?", (run_id,))
        db.execute("UPDATE test_cases SET review_status = 'stale' WHERE run_id = ?", (run_id,))
        db.execute("UPDATE runs SET llm_b_accepted = 0, llm_c_accepted = 0 WHERE id = ?", (run_id,))
        db.execute("UPDATE runs SET status = 'extraction_ready' WHERE id = ?", (run_id,))
    elif from_stage == 'b':
        # 作废 LLM-C
        db.execute("UPDATE test_cases SET review_status = 'stale' WHERE run_id = ?", (run_id,))
        db.execute("UPDATE runs SET llm_c_accepted = 0 WHERE id = ?", (run_id,))
        db.execute("UPDATE runs SET status = 'intents_ready' WHERE id = ?", (run_id,))
```

---

### M7 — 前端 UI 改造

#### Workspace.tsx

- 顶部操作栏：每个 stage 区域增加 Accept / Unlock 按钮
- Accept 按钮：stage 状态为 pending 或 force_edit 时可用，点击调用 `POST /runs/{id}/accept/{stage}`
- Unlock 按钮：stage 状态为 accepted 时可用，点击调用 `POST /runs/{id}/unlock/{stage}`
  - 如果响应包含 `cascade_warning`，弹出确认对话框
  - 用户确认后带 `?cascade=true` 再次请求
- Advance 按钮：如果 API 返回 409（需要 Accept），显示 toast 提示
- 页面加载时调用 `GET /runs/{id}/review-state` 获取初始状态

#### Sidebar.tsx + ItemModal.tsx（LLM-A）

- 每个 test basis item 行增加 Regenerate 按钮（小图标）
- 点击弹出 modal 包含必填的 comment 输入框
- 提交调用 `POST /runs/{id}/sections/{section}/items/{item_id}/regenerate`
- Accept 后所有 item 显示锁定图标，Edit/Regenerate 按钮隐藏
- Unlock 后恢复可编辑状态

#### IntentsPanel.tsx（LLM-B）

- 顶部操作栏：
  - Accept 按钮（整体）
  - Regenerate 按钮 + comment 输入框（必填）
  - "查看历史" 下拉/按钮 → 调用 `GET /runs/{id}/intents/history`
- Force Edit 状态：
  - Regenerate 按钮禁用灰掉
  - 显示醒目横幅："已超过 3 次 Regenerate 上限，请手动编辑意图规划"
  - Accept 按钮仍然可用
- 历史版本查看：
  - 弹出 modal 或侧边面板
  - 按 version 号排列，可切换查看
  - 显示每个版本的 intent 列表和生成时间

#### CaseGroup.tsx（LLM-C）

- Accept / Unlock 按钮（整体）
- Edit 按钮（已有 CaseEditModal，要接线）
- 去掉当前无效的 Regenerate 按钮

#### 级联确认弹窗（新增组件 CascadeConfirmDialog.tsx）

- Unlock 上游时弹出
- 显示警告文字："此操作将使下游数据标记为过期"
- 列出受影响的数据量（N 条 intent，M 条 case）
- "确认" / "取消" 按钮

#### Review Actions 面板

- Workspace 底部或侧边增加"评审记录"折叠面板
- 调用 `GET /runs/{id}/review-actions`
- 以时间线形式展示所有 Accept / Unlock / Edit / Regenerate 操作
- 每条显示：时间、操作类型、目标、comment（如有）

---

## Testing Decisions

### 测试策略

- 测试外部行为，不测实现细节
- 使用 mock LLM provider 避免实际调用
- 已有测试风格参考 `tests/test_console_backend.py`（FastAPI TestClient + 内存 SQLite）

### 必须测试的模块

| 模块 | 优先级 | 测试内容 |
|---|---|---|
| **M1** DB Migration | MUST | migration 幂等性（空库 + 已有数据库）、列存在性、默认值正确 |
| **M2** State Machine | MUST | 所有状态转换、double-accept 报错、unlock cascade 边界、3 次上限边界、can_advance 各种组合 |
| **M3** Regenerate Runner | MUST | mock provider 下验证 prompt 拼接正确、regenerate_count 递增、version 递增、超限后拒绝 |
| **M4** Prompt Files | 不测试 | Jinja2 模板的正确性由 M3 的集成测试隐式覆盖 |
| **M5** API Router | SHOULD | 至少测 Accept/Unlock/Regenerate 端点的 happy path + 错误 case（409/422） |
| **M6** Advance | SHOULD | 验证未 Accept 时 advance 被拒绝、Accept 后可通过、auto-chain 逻辑 |
| **M7** UI | 可选 | 后端稳定后补充 React 组件测试 |

### 集成测试

至少 1 条端到端测试：
```
create run (review_required=['a','b']) 
  → LLM-A 生成 → Accept → Advance 
  → LLM-B 生成 → Regenerate (comment) → 验证 regenerate_count=1 
  → 再次 Regenerate → 再次 Regenerate → 验证 regenerate_count=3 
  → 第 4 次 Regenerate → 验证返回 409 
  → 验证 review_status='force_edit' 
  → Edit intent → Accept → Advance 
  → LLM-C 生成 → Accept
```

---

## Out of Scope

- LLM-C 的 case 级别 Regenerate（如果需要重新生成 case，应回到 LLM-B 重新规划后重新运行 LLM-C）
- LLM-A Regenerate 的次数上限（先保留，后续按需添加）
- "Block Run" 功能（ADR-0005 中定义但未实现，不在本次范围）
- "Add" 功能（手动新增 item/intent，不在本次范围）
- 从 Excel 导入的批量 review 模式
- Review 任务分配（多人协作 review）
- 邮件/通知提醒

---

## Further Notes

- 本次变更的核心交付物是 **可工作的反馈循环**——人能看到 LLM 输出 → 给出意见 → LLM 根据意见改进 → 人确认 → 推进
- 所有 prompt 修改都走独立的 Regenerate prompt 文件，不修改原始生成 prompt，保持"Prompt = 灵魂"的解耦原则
- ADR-0005 中定义的 Accept/Edit/Add/Remove/Block Run 被本次的 Accept/Edit/Regenerate 模型取代。Add 和 Block Run 保留为未来功能
- 旧数据库迁移是单向的——不支持回退。建议在迁移前备份 `pipeline_console.db`
