# Backend Agent 系统

> 状态: **current** · 编写日期: 2026-07-02 · 项目: realtime-novel
> 版本基线: **v0.9.6** (commit `e717e5b`)

---

## 1. 元信息

| 项 | 值 |
|---|---|
| 模块 | `backend/agent/` |
| 当前版本 | v0.9.6 |
| 关键 commit | `e717e5b` |
| 编写日期 | 2026-07-02 |
| 后端框架 | FastAPI + asyncio |
| LLM 接入 | `backend/adapters/llm_adapter.py`（单例） |
| 执行模型 | ReAct loop（executor）+ Session cache + 后置 middleware |

**核心入口**：

| Agent | 工厂方法 | 源文件 |
|---|---|---|
| NovelSteward | `get_novel_steward()` | `backend/agent/agents/novel_steward.py:1` |
| NovelWriter | `get_novel_writer()` | `backend/agent/agents/novel_writer.py:1` |
| WorldTreeManager | `get_world_tree_manager()` | `backend/agent/agents/world_tree_manager.py:1` |
| Validator | `get_validator()` | `backend/agent/agents/validator.py:1` |
| AgentExecutor | `get_agent_executor()` | `backend/agent/runtime/executor.py:1` |
| SessionCache | `get_session_cache_manager()` | `backend/agent/runtime/session_cache.py:1` |

---

## 2. Agent 系统总览

系统由 **1 个入口 + 3 个专家** 共 4 个顶层 Agent 组成，全部跑在同一个 `AgentExecutor` 实例上。管家是唯一对外入口，专家不直接接触用户。

### 2.1 角色定位

| Agent | 角色 | 是否接触用户 | 走 ReAct | 落库能力 |
|---|---|---|---|---|
| **NovelSteward** | 唯一用户入口 / 调度中枢 | ✅ 唯一 | ✅ | 间接（委托） |
| **NovelWriter** | 章节正文生成 | ❌（被管家委托） | ✅ | 通过 `generate_chapter` 工具 |
| **WorldTreeManager** | 世界树基座管理 | ❌（被管家委托） | ✅ | 8 个 `add_*` + `update_base` + `edit_artifact` |
| **Validator** | 校验 Agent（v0.9 引入） | ❌（被专家调用） | ✅ | **只读，不落库** |

**关键约束**（v0.8 改造，`novel_steward.py:43-44`）：

> 管家**禁止直接编辑世界树基座**（`edit_artifact` / `update_base` 已从管家白名单移除）。改基座必须委托 WTM。

### 2.2 委托关系图

```
                       ┌─────────────────────┐
                       │   User (user_msg)   │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │    NovelSteward     │
                       │   (唯一用户入口)     │
                       │                     │
                       │  • ReAct 自主推演    │
                       │  • session cache    │
                       │  • 委托决策         │
                       └──┬───────┬──────┬───┘
                          │       │      │
            delegate_to_agent (同步)       │ dispatch_background_task (异步)
            「用户在等结果吗？」→ 是        │ 「否」→ 立即回复
                          │       │      │
              ┌───────────┘       │      └──────────┐
              ▼                   ▼                  ▼
   ┌────────────────────┐  ┌────────────────────┐  ┌──────────────┐
   │   NovelWriter      │  │ WorldTreeManager   │  │  Background  │
   │  (生成章节正文)    │  │  (基座维护)         │  │   Task       │
   │                    │  │                    │  │ (生成封面等)  │
   │ 工具:              │  │ 工具:              │  └──────────────┘
   │  • generate_       │  │  • load_project    │
   │    chapter         │  │  • edit_artifact   │
   │  • summarize_      │  │  • update_base     │
   │    chapter         │  │  • 8× add_*        │
   └─────────┬──────────┘  └────────┬───────────┘
             │                       │
             │    落库完成后调        │
             └──────────┬────────────┘
                        ▼
              ┌─────────────────────┐
              │     Validator       │
              │   (v0.9 引入)       │
              │                     │
              │ • 走 ReAct 读基座   │
              │ • 4 档 status       │
              │ • 不落库 / 只审判   │
              │                    │
              │  ├→ PASS/WARN: 放行│
              │  ├→ BLOCKED: 章节  │
              │  │   retry 1次     │
              │  └→ FATAL: WTM     │
              │      全清回滚       │
              └─────────────────────┘
```

**委托原则**（`novel_steward.py:53-56`）：

```
用户在等这个结果吗？
  是 → delegate_to_agent（同步，管家等待专家完成后回复）
  否 → dispatch_background_task（异步，管家立即回复）
```

---

## 3. 三个核心 Agent 详解

### 3.1 NovelSteward（唯一用户入口）

**源文件**：`backend/agent/agents/novel_steward.py:1`

#### 职责

1. **唯一用户入口** — 首页聊天、项目内聊天、创建项目、闲聊问答**全部**进管家
2. **职责范围内**：ReAct loop 直接调 tools（项目管理 / onboarding / 生成图片 / 探索度调整）
3. **职责范围外**：通过 `delegate_to_agent`（同步）/`dispatch_background_task`（异步）委托专家

#### 关键方法

- `NovelSteward.receive(user_message, project_id, user_id, conversation_id)` — `novel_steward.py:188`
  - 走 `executor.execute()` 跑 ReAct loop（不再预分类 intent）
  - 构造 `session_key = f"{user_id}:{conversation_id}:novel_steward"`
  - cache miss 时调 `load_chat_history`（15 轮）rebuild
  - 返回 `StewardResponse`（含 `response` / `structured_data` / `tool_calls_history` / `iterations`）

#### 关键设计（设计哲学）

| 约束 | 来源 |
|---|---|
| **纯 ReAct**，不做预分类 | `novel_steward.py:5-6` |
| **进程内 session cache**，重启后从 DB rebuild | `novel_steward.py:7-8` |
| **不直接生成章节正文**（必须委托 writer） | `novel_steward.py:9-10` |
| **不直接修改世界树基座**（必须委托 WTM） | `novel_steward.py:11-12`（v0.8 改造） |

#### 消息流

```
User → NovelSteward.receive()
  ↓
  1. 拼 session_key (user:conv:agent)
  2. cache miss? → load_chat_history(15 轮)
  3. executor.execute(ReAct loop, max_iterations=15)
  4. 包装返回 StewardResponse
  ↓
  Response → User (via ws_manager)
```

#### 系统提示要点（`STEWARD_SYSTEM_PROMPT`）

- **白名单工具**：`create_project` / `load_project` / `delete_project`（⚠️ 危险）/ `generate_image` / `update_exploration_level` / `verify_world_tree_baseline` / `list_style_packs` / `adjust_style`
- **禁用工具**：`edit_artifact` / `update_base`（v0.8 改造后）
- **委托后处理**（`novel_steward.py:60-63`）：专家返回 `requires_double_confirm=true` 或 `risk_level=blocked` 时，**必须等用户确认**，不继续推演

---

### 3.2 NovelWriter（章节正文生成）

**源文件**：`backend/agent/agents/novel_writer.py:1`

#### 职责

1. **章节正文生成** + 落盘（`generate_chapter` 工具）
2. **Summary 抽取**（`summarize_chapter` 工具）
3. **文风控制**（system_prompt 由 `agent_prompt_factory` 注入笔风+法则）
4. **历史承接**（`build_project_context_message` 注入 7 件基座 + 章节摘要）

#### 关键方法

- `NovelWriter.generate_chapter(project_id, user_message, max_iterations=15)` — `novel_writer.py:79`
  - 走 ReAct loop
  - **session_key 按 project 维度隔离**（`f"{project_id}:novel_writer"`），不跨 project
  - 每次都重新构造 system_prompt + context_message（7 件基座快照）

- `delegate_chapter_generation(project_id, intervention, source, extra_context)` — `novel_writer.py:265`
  - **统一外部入口**（管家和其他模块都走这个）
  - **v0.9 改造**：生成后调 Validator 校验（见 §3.4）
  - **C 方案**：Validator `BLOCKED` → retry 1 次（注入 issues 到 user_message）→ 仍 BLOCKED → 加 `<!-- [unverified] -->` 标记

#### 章节生成完整流程（含 v0.9 Validator 联动）

```
delegate_chapter_generation(project_id)
  │
  ├─ 1. _validate_world_tree_completeness(project_id)  [前置 7 件基座校验]
  │     ├─ world_tree.story_core / genre_tags / core_rules 非空
  │     ├─ characters 至少 1 个 protagonist
  │     ├─ main_plot 至少 1 个 pending 节点
  │     ├─ volumes 至少 1 个
  │     └─ style_pack_id 非空
  │
  ├─ 2. NovelWriter.generate_chapter()  [ReAct loop]
  │     └─ 文笔家 LLM 调 generate_chapter / summarize_chapter 工具
  │
  ├─ 3. ConsistencyChecker.check_hard_rules()  [硬约束违例扫描]
  │     └─ _extract_character_actions() 启发式抽取角色动作
  ├─ 4. ConsistencyChecker.check_world_entries()  [知识库矛盾检测]
  │     └─ 默认不阻断（只检测）
  │
  └─ 5. Validator.validate_chapter()  [v0.9 章节内容校验]
        │
        ├─ status=PASS/WARN → 放行
        ├─ status=BLOCKED → _retry_chapter_generation() 1 次
        │     └─ v0.9.6: session_key 加 chapter_num 隔离（避免多章 retry 累积）
        │     └─ 再次调 Validator
        │     └─ 仍 BLOCKED → 在 chapter_content 头部追加 [unverified] 注释
        └─ 全部结果写入 ChapterOutput.chapter_validation
```

#### 关键依赖

| 依赖 | 说明 |
|---|---|
| `build_writer_system_prompt` | 注入身份+笔风+法则+基座摘要 |
| `build_project_context_message` | 注入完整 7 件基座快照（不进 system_prompt） |
| `ConsistencyChecker` | 硬约束 + 知识库矛盾检测（两阶段） |
| `Validator` | v0.9 引入的内容合理性校验 |

---

### 3.3 WorldTreeManager（世界树基座管理）

**源文件**：`backend/agent/agents/world_tree_manager.py:1`

#### 职责（spec.md §3.3）

1. **基座一致性检查**（v0.6 s4 `_run_consistency_check`）
2. **剧情干预影响分析**（`analyze_intervention`）
3. **种子/伏笔预留**（`seed_table.add_seed`）
4. **走向调整**（`main_plot` / `sub_plots`）
5. **结构化 diff 输出**（`base_updates` + `plot_adjustments` + `new_seeds` + `consistency` + `risk_level`）

#### 关键方法

| 方法 | 行号 | 用途 |
|---|---|---|
| `analyze_intervention` | `world_tree_manager.py:380` | 同步分析干预影响（管家委托用） |
| `analyze_base_adjustment` | `world_tree_manager.py:445` | 分析基座调整（不落库） |
| `run_initial_baseline_react` | `world_tree_manager.py:507` | **v0.8 新增**：Onboarding 首次基座生成（走 ReAct） |
| `generate_volume_summary` | `world_tree_manager.py:248` | v004：卷总结（直接调 LLM，不走 ReAct） |
| `complete_volume` | `world_tree_manager.py:336` | v004：完结卷（status → completed） |
| `_rollback_all_writes` | `world_tree_manager.py:601` | v0.9：FATAL 时全清回滚 |
| `_rollback_issue_rows` | `world_tree_manager.py:632` | v0.9：BLOCKED 时精准回滚 |

#### v0.8 ReAct 改造

> **背景**：之前 `generate_full_world_tree_baseline` 是机械硬编码生成 9 张表。v0.8 欧尼酱拍板：WTM 走 ReAct loop 自主规划。

- 走 `executor.execute()` ReAct loop
- session_key：`f"{project_id}:world_tree_manager:initial_baseline"`（独立维度避免污染 intervention cache）
- 工具集新增 8 个 `add_*` 方法（`world_tree_manager.py:140-204`）：
  ```
  add_world_entry / add_timeline_event / add_geography_location
  add_main_plot_node / add_sub_plot / add_volume
  add_character / add_seed
  ```
- LLM 自主发挥角色名字/性格/关系/伏笔等细节（管家只传 `steward_payload` 作为 hint）

#### v0.9 Validator 联动策略

`analyze_intervention` 落库完成后（`world_tree_manager.py:436-456`）：

```
diff.validation.status == FATAL  → _rollback_all_writes  → risk_level="blocked"
diff.validation.status == BLOCKED → _rollback_issue_rows → risk_level 不变
diff.validation.status == PASS/WARN → 放行
```

**Onboarding 路径**（`run_initial_baseline_react`）：`run_initial_baseline_react` 同样调 Validator（`world_tree_manager.py:585-599`），但 `BLOCKED/FATAL` 直接返回 `success: false`，由 service 层捕获并回退 `info_state`。

#### 返回结构（`WorldTreeDiff`）

```python
class WorldTreeDiff(BaseModel):
    intent: str                          # intervene / adjust_base
    summary: str                         # 一句话总结
    base_updates: List[BaseUpdate]       # 7 件基座的字段更新
    plot_adjustments: List[PlotAdjustment]  # 主线/支线调整
    new_seeds: List[NewSeed]             # 新埋伏笔
    consistency: ConsistencyCheckResult  # PASS / WARN / FAIL
    risk_level: str                      # low / medium / high / blocked
    requires_double_confirm: bool        # 是否需用户二次确认
    iterations: int                      # ReAct 循环次数
    tool_calls_count: int
    tool_calls_trace: List[dict]         # 完整 tool 调用链路
```

---

### 3.4 Validator（v0.9 新增的审核 Agent）

**源文件**：`backend/agent/agents/validator.py:1`

> ⚠️ **v0.9 重构**：从散落的硬编码校验整合为独立 Agent，是本次架构最易遗漏的改动。

#### 职责

1. **世界树基座一致性校验**（WTM 落库后调）
2. **章节内容合理性校验**（文笔家生成后调）

#### 设计原则

- 走 ReAct loop（`executor.execute`）— Validator 自己调 `load_project` / `read_chapter` 读表
- 引入 session cache（按 `project + kind` 维度，见 `validator.py:104-107`）
- **不支持 `delegate_to_agent`**（避免元循环）
- 校验范围：**全覆盖所有基座**（7 大类）
- **不落库 / 不改基座** —— 职责是「审判」

#### 关键方法

| 方法 | 入口 | 触发位置 |
|---|---|---|
| `validate_world_tree` | `validator.py:124` | WTM 落库后（`analyze_intervention` + `run_initial_baseline_react`） |
| `validate_chapter` | `validator.py:213` | NovelWriter 生成后（`delegate_chapter_generation`） |

#### Status 枚举

**基座校验 4 档**（`validator.py:35-38`）：

```python
class ValidationStatus(str, Enum):
    PASS = "PASS"        # 全部通过
    WARN = "WARN"        # 有 warning，不阻断
    BLOCKED = "BLOCKED"  # 有 error 级问题，需回滚
    FATAL = "FATAL"      # 严重违例（违反 hard rule），全清
```

**章节校验 3 档**（`validator.py:41-44`）：

```python
class ChapterValidationStatus(str, Enum):
    PASS = "PASS"        # 全部通过
    WARN = "WARN"        # 有 warning，不阻断
    BLOCKED = "BLOCKED"  # 章节内容不合理 → retry 1 次
```

#### LLM 调用方式

Validator 走与管家/专家**完全相同**的 `executor.execute()` ReAct loop，但**只用只读工具**（`load_project` / `read_chapter` / `list_*`），不能调 `edit_artifact` / `update_base` / `add_*`。

```
executor.execute(
    agent=AgentConfig(
        agent_name="validator_world_tree" 或 "validator_chapter",
        system_prompt=build_validator_system_prompt(kind="..."),
    ),
    context_message=f"项目 ID + 用户意图 + 校验对象",
    session_key=f"{project_id}:validator:{kind}",  # kind = world_tree / chapter
    max_iterations=15,
)
```

#### 与 NovelWriter 的协作（C 方案）

`novel_writer.py:355-393`：

```
Validator.validate_chapter() → ChapterValidationResult
  │
  ├─ PASS/WARN
  │     └─ 直接放行，章节落盘
  │
  └─ BLOCKED
        ├─ 第一次：把 issues 注入 user_message，重写章节
        │     └─ _retry_chapter_generation()
        │         └─ session_key 加 chapter_num 隔离（v0.9.6 防多章 retry 累积）
        │     └─ 再次调 Validator
        │
        └─ 仍 BLOCKED
              └─ 在 chapter_content 开头加注释：
                  <!-- [unverified] 本章节可能与基座矛盾：{summary} -->
```

#### 与 WorldTreeManager 的协作（B 方案精准回滚 / FATAL 全清）

`world_tree_manager.py:436-456`：

```
Validator.validate_world_tree() → ValidationResult
  │
  ├─ PASS/WARN → 放行
  │
  ├─ BLOCKED → _rollback_issue_rows
  │     └─ 只删 issues 标记的 row（severity=error/fatal）
  │     └─ 找最新匹配行（简化：取 list 末尾）
  │
  └─ FATAL → _rollback_all_writes
        └─ 从 tool_calls_trace 提取所有 edit_artifact 成功的 row_id 逐个 delete
        └─ risk_level = "blocked", requires_double_confirm = True
```

---

## 4. ReAct 执行引擎（executor.py）

**源文件**：`backend/agent/runtime/executor.py:1`

### 4.1 `AgentExecutor` 类

单例（`get_agent_executor()` 工厂，`executor.py:561`），所有 Agent 共享同一实例。持有：

- `self.llm`：`LLMAdapter` 单例
- `self.registry`：`ToolRegistry` 单例
- `self._middlewares: Dict[Optional[str], List[MiddlewareFn]]` — 后置节点表（`None` key = 全局）

### 4.2 `execute()` 方法签名

`executor.py:158-174`：

```python
async def execute(
    self,
    agent: AgentConfig,                          # agent_name + system_prompt + extra_tools
    user_message: str,
    project_id: Optional[str] = None,
    context: Optional[dict] = None,              # 注入 system_prompt context_block
    context_message: Optional[str] = None,       # 7 件基座快照，独立 user message
    history: Optional[List[dict]] = None,        # cache miss 时 rebuild 用
    session_key: Optional[str] = None,           # "user_id:conv_id:agent_name"
    max_iterations: int = 15,
) -> AgentOutput
```

### 4.3 ReAct Loop ASCII 图

```
execute(agent, user_message, ...)
  │
  ├─ 1. 加载工具集 ──────────────────────────────────────
  │     tool_instances = registry.get_agent_tools(agent.agent_name)
  │     + agent.extra_tools (临时扩展)
  │     openai_tools = registry.to_openai_tools(agent.agent_name)
  │
  ├─ 2. session cache HIT/MISS 决策 ─────────────────────
  │     if session_key:
  │       if cache_mgr.has_valid_cache(uid, conv, agent):
  │         # HIT：复用 messages，sys_prompt hash 校验
  │         session_cache_obj = cache_mgr.get(...)
  │         messages = list(session_cache_obj.messages)
  │       else:
  │         # MISS：组装 system_prompt，rebuild
  │         system_prompt = _build_system_prompt(...)
  │         session_cache_obj = cache_mgr.create(...)
  │     else:
  │       # 无 session_key：原始路径（无 cache）
  │
  ├─ 3. 注入 context_message ───────────────────────────
  │     if context_message:
  │       session_cache_obj.patch_context(context_message)  # 原地替换 messages[1]
  │     messages.append({"role":"user","content":user_message})
  │
  └─ 4. ReAct loop (iteration 1..max_iterations) ─────
        │
        └─► ┌────────────────────────────────────────┐
            │  llm.complete(messages, tools=...)     │
            │  → LLM 响应                            │
            └─────────────┬──────────────────────────┘
                          │
                ┌─────────┴─────────┐
                │                   │
        tool_calls?            无 tool_calls?
                │                   │
                ▼                   ▼
        ┌──────────────┐    ┌─────────────────┐
        │ 解析 + 校验  │    │ last_response = │
        │ 每个 tool:   │    │ llm.content     │
        │  • 权限校验  │    │ → break         │
        │  • JSON parse│    └─────────────────┘
        │  • Pydantic  │
        │    validate  │
        │  • 调 tool   │
        │  • 写回 msg  │
        └──────┬───────┘
               │ continue
               ▼
        (下一轮 iteration)
        │
        ▼
   5. 退出后：
      - writeback delta to session cache
      - if needs_summary → asyncio.ensure_future(maybe_compress)
      - run _middlewares (全局 + agent 专属)
      - return AgentOutput
```

### 4.4 `AgentOutput` 标准结构

`executor.py:48-67`：

```python
class AgentOutput(BaseModel):
    final_response: str                          # LLM 最终自然语言回复
    structured_data: dict                        # 工具/后置节点写入的结构化数据
    tool_calls_history: List[dict]               # 完整 tool 调用链路
    iterations: int                              # 实际循环次数
    input_tokens: int
    output_tokens: int
    duration_ms: int
    error: Optional[str]
    # 流程控制（middleware 可写）
    needs_review: bool = False                   # 需人工审核
    skip_response: bool = False                  # middleware 拦截，不回复用户
```

`tool_calls_history` 每条记录结构：

```python
{
    "iteration": int,
    "tool_name": str,
    "arguments": dict,
    "result": dict,         # 成功时为工具输出，失败时为 {"error": ...}
    "status": str,          # success / rejected / invalid_args / validation_failed / tool_error / exception
}
```

### 4.5 Middleware 后置节点插槽

**目的**：在 `execute()` 返回前对 `AgentOutput` 做统一处理（安全审查 / 质量检测 / 日志埋点等）。

#### 装饰器注册（`executor.py:121-148`）

```python
executor = get_agent_executor()

# 全局后置节点（对所有 Agent 生效）
@executor.middleware()
async def safety_check(output: AgentOutput, context: dict) -> AgentOutput:
    if contains_sensitive(output.final_response):
        output.final_response = "[已过滤]"
    return output

# Agent 专属后置节点
@executor.middleware(agent_name="novel_writer")
async def word_count_check(output: AgentOutput, context: dict) -> AgentOutput:
    if len(output.final_response) < 500:
        output.structured_data["quality_warn"] = "章节字数不足"
    return output
```

#### 执行顺序（`_run_middlewares`, `executor.py:165-187`）

```
全局 middleware（注册顺序） → agent 专属 middleware（注册顺序）

单个 middleware 抛异常 → 记 WARNING 并跳过，不中断后续。
```

#### Middleware 上下文（`mw_context`）

```python
{
    "agent_name": "novel_writer",
    "project_id": "proj-123",
    **(调用方传入的 context dict)
}
```

#### 编程式注册（`executor.py:150-163`）

```python
executor.add_middleware(my_fn, agent_name="novel_writer")
```

---

## 5. Session Cache（session_cache.py）

**源文件**：`backend/agent/runtime/session_cache.py:1`

### 5.1 目的

为管家/两个专家 Agent 维护**进程内**的 messages 缓存，避免每轮 LLM 调用都重新组装完整 messages。

### 5.2 Cache 内部 messages 布局

```
messages[0]  → {"role":"system", "content": sys_prompt + 工具清单}    ← 固定头，可原地替换
messages[1]  → {"role":"system", "content": "[上下文] ..."}            ← 可选，原地替换
messages[2+] → 历史对话轮次 (user/assistant/tool)
```

### 5.3 Cache Key 格式

`session_cache.py:259`：

```python
f"{user_id}:{conversation_id}:agent_name}"
```

**典型 key**：

| 维度 | session_key |
|---|---|
| 管家会话 | `{user_id}:{conv_id}:novel_steward` |
| 文笔家（按 project 隔离） | `{project_id}:novel_writer` |
| 文笔家 retry（v0.9.6） | `{project_id}:novel_writer:retry:ch{chapter_num}` |
| WTM 干预 | `{project_id}:world_tree_manager` |
| WTM 首次基座 | `{project_id}:world_tree_manager:initial_baseline` |
| Validator 基座 | `{project_id}:validator:world_tree` |
| Validator 章节 | `{project_id}:validator:chapter` |

### 5.4 Hit / Miss 流程

```
AgentExecutor.execute(session_key=...)
  │
  ├─► cache_mgr.has_valid_cache(user_id, conv_id, agent_name)
  │     │  轻量检查：只校验 TTL，不校验 sys_prompt hash
  │     │
  │     ├─ False (MISS 或 TTL 过期)
  │     │     │
  │     │     ├─ 调用方决定是否 load_chat_history()
  │     │     ├─ 组装 system_prompt
  │     │     └─ cache_mgr.create(... sys_prompt, initial_messages, context_window)
  │     │
  │     └─ True (HIT)
  │           │
  │           ├─ cache_mgr.get(..., sys_prompt)
  │           │     ├─ sys_prompt 变化 → patch_sys_prompt 原地替换 messages[0]
  │           │     └─ 命中 → 返回 cache（messages 浅拷贝防止污染）
  │           │
  │           └─ 注入 context_message → patch_context 原地替换 messages[1]
  │
  └─► 走 ReAct loop ...
       完成后：
         - session_cache_obj.append_delta(delta)
         - if session_cache_obj.needs_summary():
             asyncio.ensure_future(maybe_compress(...))
```

### 5.5 超长压缩策略

#### 触发条件（`session_cache.py:75-77`）

```python
def needs_summary(self) -> bool:
    return self.used_tokens >= self.context_window * COMPRESS_THRESHOLD
```

- `COMPRESS_THRESHOLD = 0.70`（`session_cache.py:30`）
- `context_window` 从 `agents.json` 读，默认 `128000`（`session_cache.py:33`）
- 累计 token 通过 `add_tokens()` 累加（`session_cache.py:74`）

#### 压缩流程（`maybe_compress`, `session_cache.py:344-389`）

```
触发 maybe_compress
  │
  ├─ 1. 取对话历史 dialogue = get_dialogue_messages()
  │
  ├─ 2. 找最近 KEEP_RECENT_ROUNDS=10 轮的 user 消息起始 index
  │
  ├─ 3. 拆分：
  │     to_compress = dialogue[:keep_start]   # 待压缩的早期对话
  │     keep_recent = dialogue[keep_start:]   # 保留的最新 10 轮
  │
  ├─ 4. 调 LLM 生成摘要（_generate_summary, `session_cache.py:412-460`）
  │     └─ System prompt: 「请用 3-5 句话概括以下对话的关键信息」
  │     └─ max_tokens=512, temperature=0.3
  │
  └─ 5. 重建 messages：
        [sys_prompt] + [context] + [summary 系统消息] + keep_recent
```

#### Tool 结果截断（`truncate_tool_result`, `session_cache.py:463-481`）

- 单条 tool 返回 > 10 KB → 截断 + 追加提示
- 在 `execute()` 拼回 messages 前调用（`executor.py:339`）

#### TTL 过期（`is_expired`, `session_cache.py:70-71`）

- `CACHE_TTL_SECONDS = 86400`（24 小时，`session_cache.py:27`）
- 过期 → `get()` 返回 None → 走 MISS 路径全量 rebuild

#### 主动失效（`session_cache.py:296-316`）

| 方法 | 触发场景 |
|---|---|
| `invalidate(uid, conv, agent)` | 切换 conversation / Onboarding 完成 |
| `invalidate_user(uid)` | 用户级失效 |
| `invalidate_conversation(conv)` | 新建对话时 |

---

## 6. Onboarding 5 步流程（onboarding/）

**目录**：`backend/agent/onboarding/`
- `controller.py` — **DEPRECATED v0.7**（仅保留 stub 防 import 报错，`controller.py:11-15`）
- `hooks.py` — EventBus 订阅处理器

> **重要**：v0.7 后 Onboarding 不再走 controller 独立 LLM 推演，而是**管家通过 ReAct loop 多轮对话直接收集字段**。下面讲的 5 步流程对应管家中推进 Onboarding 的 5 个**工具调用节点**。

### 6.1 Onboarding 状态机

**Onboarding 状态**（`backend/persistence/onboarding_repository.py:23-104`）：

```
info_state: collecting → wtm_pending → ready
                ↓              ↓
            多轮收集       WTM 落库中       Onboarding 完成
```

| 状态 | 含义 | 持久化字段 |
|---|---|---|
| `collecting` | 管家正在多轮对话收集 6 维信息 | `onboarding_state.payload_json` |
| `wtm_pending` | WTM 正在跑 ReAct 落库 9 张表 | 同上 |
| `ready` | Onboarding 完成（项目名+封面由 hook 生成） | 同上 |

**v0.6 旧 5 步**（`onboarding_flow.py:25-27` 兼容保留）：

| step | 用途 | 当前状态 |
|---|---|---|
| 1 | 题材/风格/基调 | **废弃**（管家直接收集字段） |
| 2 | 主角/对手/盟友 | **废弃**（管家直接收集字段） |
| 3 | WTM 输出基座 | **v0.8 改造**：委托 `run_initial_baseline_react` |
| 4 | 落库确认 | **保留**（事件 `onboarding.step4_confirmed`） |
| 5 | 生成第 1 章 | **废弃**（用户后续显式触发） |

### 6.2 Onboarding 7 步用户视角流程（管家实际行为）

> 用户视角下，从「开始创建」到「可以开始写第 1 章」实际经过 7 个阶段（这是 v0.8 改造后的现状）：

```
1. 【对话收集】管家与用户自由对话，收集 6 维信息
   ├─ 项目名称 / 世界树基础 / 故事核心 / 主要角色 / 主线大纲 / 笔风标签
   └─ 自主推导的部分必须标注「我帮你推了...」
   ↓ 6 维齐 + 用户明确确认
2. 【确认环节】管家把 6 维清单展示给用户，等回复「确认/开始」
   ↓ 用户确认
3. 【create_project】管家调 create_project 工具 → 获得 project_id
   ↓
4. 【list_style_packs + adjust_style】管家调笔风选择工具
   ↓
5. 【verify_world_tree_baseline】管家调 verify_world_tree_baseline 校验 spec §5.6 6 项
   ├─ world_tree.story_core / genre_tags_json / core_rules_json 非空
   ├─ characters 至少 1 个 protagonist
   ├─ main_plot 至少 1 个 pending 节点
   └─ volumes 至少 1 个
   不通过 → 回到 step 1 继续对话
   ↓ 全部通过
6. 【delegate_to_agent(initial_baseline)】管家同步委托 WTM
   ├─ WTM.run_initial_baseline_react(payload=管家收集的 hint)
   ├─ WTM 走 ReAct loop 自主落库 9 张表
   ├─ 落库后调 Validator.validate_world_tree()
   └─ 失败 → 抛回管家，管家告知用户「基座生成失败」
   ↓ 成功
7. 【step4_confirmed 事件触发】后台并发：
   ├─ _generate_project_name()  → update_name
   └─ generate_and_save_cover() → update_cover_image_url
   ↓
   告知用户「世界树基座已就绪」 + 项目名 + 封面图
```

### 6.3 Step 3/4 controller 调用

**Step 3（基座生成）**：管家调 `delegate_to_agent(agent="world_tree_manager", intent="initial_baseline", payload=...)`，由 WTM 的 `run_initial_baseline_react()`（`world_tree_manager.py:507`）处理，**不再走 controller**。

**Step 4（基座校验）**：管家直接调 `verify_world_tree_baseline` 工具（`backend/agent/tools/onboarding_tools.py:45`），校验 spec §5.6 的 6 项。

**Step 5（用户确认）**：管家通过 `onboarding_user_confirm` 工具触发 `onboarding_flow.step()`（`onboarding_flow.py:45-103`），该方法**保留**作为 HTTP 路由兜底。

> ⚠️ `OnboardingController.consult(step=N)`（`controller.py:21-26`）**已废弃**，调用方抛 `NotImplementedError`。

### 6.4 `hooks.py` 通过 EventBus 订阅

**源文件**：`backend/agent/onboarding/hooks.py:1`

模块被 import 时**自动**向 `event_bus` 注册 handler，无需显式调用。

**当前注册事件**：

| 事件 | 触发位置 | Handler | 副作用 |
|---|---|---|---|
| `onboarding.step4_confirmed` | 管家确认 6 维 + WTM 落库成功 | `handle_step4_confirmed` | 并发生成项目名 + 封面图 |

**handler 流程**（`hooks.py:78-148`）：

```
@event_bus.on("onboarding.step4_confirmed")
async def handle_step4_confirmed(project_id, payload, ws=None):
  │
  ├─ 1. 并发触发：
  │     name_task  = _generate_project_name(story_core, characters, tone)
  │     cover_task = generate_and_save_cover(project_id, payload, projects_root)
  │     await asyncio.gather(name_task, cover_task, return_exceptions=True)
  │
  ├─ 2. 处理名称（成功时）：
  │     proj_repo.update_name(project_id, new_name)
  │     OnboardingFlow().update_project_name_in_state(project_id, new_name)
  │     尝试推 WS: {"type": "project_name_updated", ...}  # WS 断则静默忽略
  │
  └─ 3. 处理封面（成功时）：
        proj_repo.update_cover_image_url(project_id, cover_image_url)
        尝试推 WS: {"type": "cover_image_updated", ...}  # WS 断则静默忽略
```

**与 WS 完全解耦**（`hooks.py:91-95`）：落库操作不依赖 WS，WS 推送失败被 try/except 静默吞掉。

**项目名生成 prompt**（`hooks.py:20-37`）：

- 中文 1-15 字（鼓励），也可英文
- 携带故事核心悬念/冲突关键词
- 避免「小说/世界/世界线」等泛词
- 严格返回 1 个 string

---

## 7. Specialists

> 本节讨论的"Specialists"特指 `backend/agent/specialists/` 下的**轻量 LLM 工具函数**——与第 2 节的"3 顶层 Agent"是两个完全不同的概念。

### 7.1 Specialists 是什么

历史上（v0.6.1 之前）系统有 `ChapterGeneratorSpecialist` / `WorldTreeKeeperSpecialist` / `MemoryKeeperSpecialist` 三个 Specialist 类。v0.6.2 重构把整层"Specialist Agent"连同 `SpecialistAgent ABC` + 3 个 Stub 别名 + `ImageGeneratorStub` 全部删除（`backend/agent/specialists/__init__.py:1-22`），相关能力下沉到 Agent 工具（`GenerateChapterTool` / `WorldTreeManager` / `SearchMemoryTool`）。

**当前 `specialists/` 下只剩 2 个纯函数模块**（不是 Agent，不是 tool，调用方是 LLM 工具和 Agent 内部代码）：

| 模块 | 类型 | 用途 |
|---|---|---|
| `exploration.py` | 纯函数（无状态） | exploration_level 解析 + LLM 参数映射 + 探索度风格指导 + CHAPTER_GENERATOR_PROMPT 占位符填充 |
| `chapter_summarizer.py` | 纯函数（sentinel 解析） | 章节 summary 抽取（sentinel-tagged 块解析 + fallback 截断） |

它们**不是 LLM 角色**，**没有 ReAct loop**，**没有 session cache**——只是"被调用的辅助函数"。System prompt / 工具白名单里都不出现。

### 7.2 `exploration.py` — 探索度参数工具集

**源文件**：`backend/agent/specialists/exploration.py:1`

#### 4 个公开函数

| 函数 | 行号 | 输入 | 输出 | 用途 |
|---|---|---|---|---|
| `get_llm_params_for_project` | `exploration.py:14` | `project_id`, `role` | `{temperature, max_tokens, frequency_penalty}` | 按项目 exploration_level 返回 LLM 调用参数 |
| `get_style_directive` | `exploration.py:42` | `level: str` | prompt 字符串 | 按探索度返回创作风格指导段 |
| `get_chapter_word_count_range` | `exploration.py:74` | `level: str` | `"4750-5250"` 字符串 | 从 agents.json 读 chapter_word_count，生成 ±5% 浮动范围 |
| `fill_chapter_prompt_placeholders` | `exploration.py:95` | `template: str`, `project_id` | 填充后的字符串 | 填充 `CHAPTER_GENERATOR_PROMPT` 的探索度占位符 |
| `get_llm_params_for_chat` | `exploration.py:170` | `user_id`, `project_id`, `role` | `{temperature, max_tokens, frequency_penalty}` | 管家 CHAT/ReAct 路径获取 LLM 参数（v0.6.1 三级覆盖） |

#### 三级覆盖（v0.6.1）

`get_llm_params_for_chat` 走 `_resolve_exploration_level`（`exploration.py:138`）三级覆盖：

1. **项目级** `projects.exploration_level`（最高优先级）
2. **用户级** `user_preferences.default_exploration_level`（中间）
3. **硬默认** `agents.json exploration_levels.standard`（最低，fallback）

#### 3 档探索度的风格指令（`exploration.py:42-72`）

| Level | 风格指令要点 |
|---|---|
| `conservative` | 严守世界树基座, 不偏离用户设定；字数严格控制, 不超不欠；AI 补充范围 限, 只在用户设定上微调 |
| `standard` | 遵守世界树基座；字数控制 + AI 可合理补充 1-2 处细节 (人物动作/环境描写)；保持故事连贯性优先 |
| `wild` | 大胆探索: 在世界树框架内鼓励不同表述/节奏/视角；鼓励篇幅扩展: 字数可超上限 20%；添加 1-2 个用户没明说的细节；探索性 > 准确性 |

#### 调用位置

| 调用方 | 调哪个 | 在哪 |
|---|---|---|
| 文笔家 system_prompt 注入 | `get_style_directive` | `agent_prompt_factory.py:266-272` |
| 章节生成 prompt 填充 | `fill_chapter_prompt_placeholders` | `chapter_generator` 工具内 `prompts/specialists.py:1` 模板消费 |
| 管家 LLM 调用 | `get_llm_params_for_chat` | `novel_steward.py` + `executor.py` |
| 文笔家 LLM 调用 | `get_llm_params_for_project` | `novel_writer.py` |

### 7.3 `chapter_summarizer.py` — 章节 Summary 抽取

**源文件**：`backend/agent/specialists/chapter_summarizer.py:1`

#### Sentinel 块协议

文笔家 LLM 输出按以下结构生成（`chapter_summarizer.py:21-23`）：

```
[章节正文 3000-4500 字]

###SUMMARY###
1 句话剧情总结
###END_SUMMARY###
```

工具用 sentinel 块做 robust 解析。

#### 4 个公开函数

| 函数 | 行号 | 输入 | 输出 | 用途 |
|---|---|---|---|---|
| `extract_summary_from_llm_output` | `chapter_summarizer.py:26` | `llm_output: str` | `summary: str \| None` | 从 sentinel 块抽 1 句话 summary；>200 字截断 |
| `parse_chapter_summary` | `chapter_summarizer.py:51` | `llm_output: str` | 纯正文（剥掉 sentinel 块） | 给落盘用纯正文 |
| `fallback_summary` | `chapter_summarizer.py:76` | `content: str`, `max_chars=100` | 截断字符串 | sentinel 解析失败时取正文前 N 字 |
| `extract_summary_safe` | `chapter_summarizer.py:95` | `llm_output: str` | `(summary, body)` 元组 | safe 解析：sentinel 优先，fallback 兜底 |

#### 3 级 fallback 链（`summarize_chapter_tool.py` 内 `run` 方法）

```
sentinel 解析成功   → method="sentinel"          (主路径)
sentinel 失败      → 正文前 100 字截断           → method="fallback_truncate"
截断仍 < 5 字      → 调 LLM 单独生成              → method="llm_fallback"
仍失败            → ToolError("SUMMARY_FAILED")
```

#### 调用位置

| 调用方 | 在哪 |
|---|---|
| `SummarizeChapterTool` 主实现 | `tools/summarize_chapter_tool.py:42-83` |
| 文笔家 LLM 调 `summarize_chapter` 工具 | `novel_writer.py` ReAct loop 内 |

> **设计要点**：sentinel 块**不进**章节正文。`parse_chapter_summary` 在落盘前把 sentinel 块剥掉，保证 `data/projects/{id}/chapters/chapter_NNN.md` 文件里只有纯净的小说文本。

---

## 8. 上下文组装 + Prompt 系统

### 8.1 上下文组装（`context/`）

**目录**：`backend/agent/context/`
- `builders.py` — 3 角色 messages 拼装
- `_helpers.py` — DB 转换 + 字段格式化（私有 helper）
- `__init__.py` — 公开 API re-export（保持外部 import 路径不变）

#### 6 个 `build_messages_for_*` 函数 + `load_chat_history`

| 函数 | 行号 | 输入 | 输出 messages 结构 | 适用 Agent |
|---|---|---|---|---|
| `build_messages_for_steward` | `builders.py:26` | `user_id`, `current_user_message`, `system_prompt`, `max_history=20` | `[sys] + [summary(可选)] + [history N 轮] + [current user]` | NovelSteward（user 维度，**不绑 project**） |
| `build_messages_for_worldtree_keeper` | `builders.py:80` | `project_id`, `current_user_message`, `system_prompt`, `max_history=5` | `[sys] + [world_tree JSON] + [chapter_summaries 1句×N] + [history] + [current]` | WorldTreeManager（per-project） |
| `build_messages_for_chapter_generator` | `builders.py:122` | `project_id`, `current_user_message`, `system_prompt`, `max_history=5` | `[sys] + [world_tree] + [main_plot] + [sub_plot] + [character] + [seeds] + [chapter_summaries 分级] + [history] + [current]` | NovelWriter（per-project） |
| `build_messages_for_node` | `builders.py:198` | `conversation_id`, `current_user_message`, `max_history=10`, `system_prompt` | 简易 4 段（v0.4.1 兼容 API，**不推荐用于新代码**） | 旧 StateGraph intake/respond 节点（已废弃） |
| `load_history_messages` | `_helpers.py:78` | `conversation_id`, `max_history=10`, `exclude_message_id` | `[OpenAI 格式 history]` | 通用 |
| `load_chat_history` | `_helpers.py:300` | `user_id`, `session_rounds=15` | `[OpenAI 格式 history]` | NovelSteward cache miss 时的冷启动 rebuild |

> ⚠️ **实际运行时**：管家/文笔家/架构师都走 `executor.execute()` + `session_cache`（见 §4、§5），**不直接调** `build_messages_for_*`。这些函数保留供旧调用方/测试用，cache miss 走 `load_chat_history` 冷启动。

#### 7 件基座格式化 helper（`_helpers.py`）

| Helper | 行号 | 用途 |
|---|---|---|
| `_format_world_tree_compact` | `_helpers.py:159` | world_tree 5 字段压成字符串 |
| `_format_world_tree_baseline` | `_helpers.py:187` | 完整 7 件注入顺序（core_rules → world_entries → timeline → geography → story_core + genre_tags） |
| `_format_chapter_summaries_short` | `_helpers.py:142` | 所有章节 1 句拼一段（架构师用） |
| `_format_chapter_summaries_graded` | `_helpers.py:155` | 20 章前 1 句 / 20 章内 detailed（文笔家用） |
| `_format_chapter_summaries_by_volume` | `_helpers.py:357` | v004 按卷维度（当前卷全列 / 完结卷只列 vol.summary） |
| `_format_main_plot` | `_helpers.py:240` | arc_phrase + beats + metadata |
| `_format_sub_plot` | `_helpers.py:278` | sub_plot.threads[] 压缩 |
| `_format_characters` | `_helpers.py:296` | characters[] 压缩（带 traits/speech_style） |
| `_format_seeds` | `_helpers.py:325` | seeds[] 压缩（trigger/payoff/chapter 显示） |
| `json_dumps` | `_helpers.py:353` | 中文安全 JSON 序列化 |

#### `_load_project_data`（`_helpers.py:107`）

一次拉取项目所有基座数据：

```python
{
    "world_tree": {...},
    "style_pack_id": "...",
    "genre_resonance": {...},
    "main_plot": {...},
    "sub_plot": {...},
    "character_card": {...},
    "seed_table": {...},
    "chapters": [ChapterRow, ...],
    "volumes": [VolumeRow, ...],   # v004 新增
}
```

### 8.2 Prompt 系统（`prompts/`）

**目录**：`backend/agent/prompts/`

#### 5 个文件的职责分工

| 文件 | 职责 | 关键导出 |
|---|---|---|
| `agent_prompt_factory.py` | 拼装 Agent system_prompt 主体（**唯一工厂**） | `build_writer_system_prompt` / `build_worldtree_system_prompt` / `build_validator_system_prompt` / `build_project_context_message` |
| `specialists.py` | 3 个 Specialist 真实 prompt 模板（带占位符） | `WORLDTREE_KEEPER_PROMPT` / `CHAPTER_GENERATOR_PROMPT` / `MEMORY_KEEPER_PROMPT` |
| `style_packs.py` | 12 个写作笔风库（hard code 预设） | `STYLE_PACKS` 字典 / `list_style_packs` / `get_style_pack` / `get_default_pack_id` / `get_style_pack_or_default` |
| `writing_laws.py` | 17 条全局写作法则 + 4 条定向法则 + 8 条红线 | `WRITING_LAWS` / `RED_LINES` / `get_global_laws` / `get_laws_for_style` / `get_red_lines` |
| `onboarding.py` | **DEPRECATED**（v0.7 弃用） | `ONBOARDING_STEP3_PROMPT` / `ONBOARDING_STEP4_PROMPT`（空 stub 防 import 报错） |

#### `writing_laws.py` — 写作铁律（不可突破的底线）

**8 条红线**（`writing_laws.py:285-318`，恒定生效，所有笔风 + 所有 Agent 都必须遵守）：

| ID | 标题 |
|---|---|
| `red_01` | 禁用否定对比句式（"没有…没有…"/"不是…而是…"） |
| `red_02` | 禁用弱转折句式（"虽然…但是…"/"尽管…却…"） |
| `red_03` | 禁用机械流水账（一句话一动作、连续主语） |
| `red_04` | 禁用纯台词/上帝视角/AI 口癖/格式标记 |
| `red_05` | 禁用同质化句式与硬切（连续三句同结构、视角跳转、场景硬切） |
| `red_06` | 禁用脸谱化与模板化（人物/台词/情节/场景同质化） |
| `red_07` | 禁用冗余与矛盾（副词泛滥、无效修辞、细节矛盾） |
| `red_08` | 禁用无根写作（无动机行为、无铺垫转变、无回收伏笔） |

**17 条全局法则**（`writing_laws.py:13-264`，按 category 分类）：

| Category | 法则 ID |
|---|---|
| character | `character_consistency` / `healthy_personality` / `dialogue_full` |
| detail | `micro_carving` / `detail_consistency` |
| scene | `action_continuity` / `scene_immersion` |
| language | `anti_ai_cliche` / `sentence_variety` / `pure_text_format` |
| narrative | `pov_discipline` / `no_preaching` |
| plot | `plot_progression` / `hook_ending` / `opening_impact` / `foreshadow_registration` / `self_check` |

**4 条定向法则**（`scope=style_linked`，按 `linked_styles` 字段按笔风开启）：
- `longline_narrative` → `yanhuo_shiyi` / `huangjin_shidai`
- `human_warmth` → `yanhuo_shiyi`
- `localization_zh` → `yanhuo_shiyi` / `souffle_fairy`
- `combat_layered` → `huangjin_shidai`

#### `style_packs.py` — 风格包 Prompt

**12 个笔风预设**（`style_packs.py:11-746`）：

| ID | 名称 | 适用题材 |
|---|---|---|
| `shuise_qiangwei` | 都市言情·唯美系 | 现代/古典浪漫 |
| `souffle_fairy` | 甜宠治愈·少女向 | 校园/轻松日常 |
| `yanhuo_shiyi` | 现实主义·烟火气 | 现实题材（**默认**） |
| `huangjin_shidai` | 繁华奇观·奢靡华丽 | 富贵/民国/爵士时代 |
| `xianxia_ranhuo` | 仙侠热血·磅礴燃文 | 修仙/玄幻/仙侠 |
| `guwuxia_jianghu` | 古典武侠·侠骨柔情 | 武侠江湖 |
| `shuangwen_shengji` | 爽文流·升级反转 | 系统文/无敌流/逆袭文 |
| `guyuan_gonting` | 古典雅韵·宫廷古言 | 古代/架空/宫廷 |
| `xuanyi_zhanglie` | 暗调悬疑·张力叙事 | 悬疑/推理/犯罪/灵异 |
| `keji_saibo` | 科幻赛博·冷峻未来 | 科幻/赛博朋克/星际/AI |
| `qingchun_rexue` | 青春热血·成长燃情 | 校园/运动/成长 |
| `heian_renxing` | 黑暗压抑·人性深渊 | 暗黑/末世/心理/人性 |

每个 StylePack 包含：`name` / `tagline` / `core_idea.{shell,core,soul}` / `tone` / `worldview_texture[]` / `narrative.{focus,rhetoric,dialogue,rhythm}` / `imagery.{scenes,props,colors}` / `principles.{believe,avoid,achieve}` / `samples[]`。

**默认笔风**（`style_packs.py:753`）：`yanhuo_shiyi`（烟火气最通用，作为 fallback）。

#### `specialists.py` — 专家 Prompt

3 个 prompt 模板（`specialists.py:11-77`），含 `{world_tree}` / `{chapter_summaries}` / `{history}` / `{user_message}` / `{word_count_range}` / `{style_directive}` 占位符，由调用方注入：

| Prompt | 调用方 | 用途 |
|---|---|---|
| `WORLDTREE_KEEPER_PROMPT` | （保留导出，**当前未直接使用**——架构师 system_prompt 由 `agent_prompt_factory.build_worldtree_system_prompt` 拼装） | 历史沿用：世界树基座 diff 输出 |
| `CHAPTER_GENERATOR_PROMPT` | `fill_chapter_prompt_placeholders` 填充占位符 | 章节生成 |
| `MEMORY_KEEPER_PROMPT` | （保留导出，当前未直接使用——`SearchMemoryTool` 走 DB 检索） | 历史沿用：记忆检索 |

#### `onboarding.py` — Onboarding Prompt

**DEPRECATED**（`onboarding.py:1-12`）：v0.7 弃用旧 5 步 OnboardingController 后，两个 step prompt 保留为空 stub 防 import 报错。当前 Onboarding 走**管家 ReAct loop 直接收集 6 维字段**（见 §6），无独立 prompt。

#### `agent_prompt_factory.py` — Prompt 工厂（组装最终发送的 Prompt）

**唯一负责拼装 Agent system_prompt 主体**的入口。3 个核心函数 + 1 个 context message 构造器：

| 函数 | 行号 | 输出用途 |
|---|---|---|
| `build_writer_system_prompt` | `agent_prompt_factory.py:282` | 文笔家 system_prompt：身份 + 笔风 + 法则 + 红线 + 探索度指令 + 基座定调 |
| `build_worldtree_system_prompt` | `agent_prompt_factory.py:344` | 架构师 system_prompt：身份（按 intent 分支：intervention / initial_baseline）+ 笔风 + 法则 + 红线 + 基座定调 |
| `build_validator_system_prompt` | `agent_prompt_factory.py:165` | Validator system_prompt：按 kind 分支（world_tree / chapter）注入对应身份 + 工具集 + 禁止项 |
| `build_project_context_message` | `agent_prompt_factory.py:402` | 独立 user message：main_plot 未完成 + sub_plot 未完成 + characters 全量 + seeds 未了结 + 章节按卷摘要 |

##### `build_writer_system_prompt` 拼装顺序（`agent_prompt_factory.py:296-334`）

```
1. _WRITER_IDENTITY         — 身份/职责/工作流骨架
2. _format_style_pack       — 笔风（核心理念/基调/质感/笔法/意象/信念-禁区-目标/样本）
3. _format_laws             — 全局必备 17 条 + 定向关联 4 条
4. _format_red_lines        — 8 条红线
5. get_style_directive      — 探索度指令（按项目 exploration_level）
6. _format_base_summary     — 基座定调（精简 world_tree，完整走 context）
```

**executor 负责的尾部追加**（不在 factory 职责内）：

- 工具清单（动态生成，含 `extra_tools`）
- ReAct 输出格式 + 约束
- project_id / context dict

##### v0.9.4 `build_project_context_message` 5 条设计原则

`agent_prompt_factory.py:415-421`：

| Q | 原则 |
|---|---|
| Q1 | 不在 context 重复 world_tree / style_pack（完整信息已在 sys_prompt） |
| Q2 | main_plot / sub_plot 只写未完成（status != completed） |
| Q3 | characters 全量写入（上限 16，未来支持重要等级过滤） |
| Q4 | seeds 只写未了结（status not in harvested/abandoned） |
| Q5 | detailed_summary 字段已删 → 改用「历史卷维度 description」+「当前卷下所有章节 summary」 |

---

## 9. 工具系统 + 数据流

### 9.1 `BaseTool` 接口

**源文件**：`backend/agent/tools/base.py:1`

```python
class BaseTool(ABC):
    name: str = ""                                              # 工具注册名（与 AGENT_TOOLS 白名单匹配）
    description: str = ""                                       # 给 LLM 看的功能描述
    input_schema: type[BaseModel] = BaseModel                   # Pydantic 输入 schema
    output_schema: type[BaseModel] = BaseModel                  # Pydantic 输出 schema

    @abstractmethod
    async def run(
        self,
        input: BaseModel,
        progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> BaseModel:
        """执行工具
        - 成功：返回 output_schema 实例
        - 失败：返回 ToolError(code, message, details)（**不是抛异常**）
        """
        ...

    def is_dangerous(self) -> bool:                              # 危险工具 override 返回 True
        return False
```

**关键设计**（`base.py:27-34`）：
- 工具失败返回**结构化 `ToolError`**，不抛异常给 Agent（spec §5.2）——LLM 能看到 error 自行决定重试或换工具
- `progress_callback` 让长任务能向前端推送进度（`generate_chapter` / `generate_image` 使用）
- 全局 `_tools` dict 通过 `register_tool()` 在每个工具模块 import 时副作用注册

### 9.2 `ToolRegistry` + `AGENT_TOOLS` 白名单表

**源文件**：`backend/agent/tools/registry.py:1`

`AGENT_TOOLS` 是**唯一权威**的 Agent→工具白名单（`registry.py:18-67`），`ToolRegistry.get_agent_tools()` 在 executor 启动 ReAct loop 时读取。运行时可通过 `register_agent_tools()` 动态追加（测试/插件用）。

#### 管家 `novel_steward`（11 个工具）

| 可用工具 | 不允许的工具 |
|---|---|
| `load_project` / `list_projects` / `create_project` / `delete_project` / `generate_image` / `update_exploration_level` / `list_style_packs` / `adjust_style` / `verify_world_tree_baseline` / `delegate_to_agent` / `dispatch_background_task` | **`edit_artifact` / `update_base` / `edit_artifact_batch` / `weave_plot` / `introspect_character` / `switch_pov`**（v0.8 改造后管家**禁止直接修改世界树基座**，必须委托 WTM） |

#### 文笔家 `novel_writer`（5 个工具）

| 可用工具 | 不允许的工具 |
|---|---|
| `load_project` / `read_chapter` / `generate_chapter` / `summarize_chapter` / `generate_volume_summary` | **所有 `edit_artifact*` / `update_base` / `delete_project` / `delegate_to_agent` / `dispatch_background_task`**（文笔家职责 = 写正文 + 抽 summary + 生成卷总结，**不调基座、不委派**） |

#### 架构师 `world_tree_manager`（8 个工具）

| 可用工具 | 不允许的工具 |
|---|---|
| `load_project` / `edit_artifact` / `edit_artifact_batch` / `update_base` / `weave_plot` / `introspect_character` / `adjust_style` / `switch_pov` | **`generate_chapter` / `summarize_chapter` / `read_chapter` / `generate_volume_summary`**（架构师职责 = 基座维护，**不写章节**） |

#### Validator（**不在 `AGENT_TOOLS` 白名单**）

v0.6 架构调整后，Validator **不走 `ToolRegistry.get_agent_tools()` 拿工具**——它直接由 `executor.execute()` 跑 ReAct，system_prompt 里**硬编码**"只能调 `load_project` / `read_chapter`"（`agent_prompt_factory.py:165-180`），相当于在 prompt 层做白名单：

| 实际可用工具 | 禁止工具 |
|---|---|
| `load_project` / `read_chapter`（硬编码进 system_prompt） | **所有写工具**（`edit_artifact` / `update_base` / `add_*` / `generate_chapter` 等）——**不落库 / 只审判** |

### 9.3 21 个工具详细表

> **AGENT_TOOLS 白名单内的 21 个工具**（按 `registry.py` 实际统计）。注意：v0.7 已删除 `onboarding_propose_step` / `onboarding_user_confirm` / `onboarding_generate_chapter` 三个旧 Onboarding 工具（`onboarding_tools.py:10` 注释确认）。

#### 工具表

| 类别 | 工具名 | 文件 | 输入 schema 关键字段 | 输出 | 何时调用 | is_dangerous |
|---|---|---|---|---|---|---|
| **项目管理** | `load_project` | `project_tools.py:50` | `project_id` | `ProjectDetail`（id / name / palette / world_tree / chapters） | 管家/文笔家/架构师/Validator 几乎每个任务开头 | ❌ |
| **项目管理** | `list_projects` | `project_tools.py:144` | 无 | `ListProjectsOutput` | 管家（"我有什么项目"用，v0.9.1 新增） | ❌ |
| **项目管理** | `create_project` | `project_tools.py:80` | `name` / `palette` / `exploration_level` (conservative/standard/wild) / `initial_prompt` / `style_pack_id` | `ProjectDetail` | 管家 Onboarding 阶段 | ❌ |
| **项目管理** | `delete_project` | `project_tools.py:109` | `project_id` / `confirm: Literal[True]` | `ProjectDetail` | 管家（"删了这个项目"用） | ✅ |
| **探索度** | `update_exploration_level` | `exploration_tools.py:70` | `level` / `scope` (project/user) / `project_id` / `user_id` | `UpdateExplorationLevelOutput` | 管家（"这篇用 wild 档"用） | ❌ |
| **笔风** | `list_style_packs` | `style_tools.py:45` | 无 | `ListStylePacksOutput` | 管家（Onboarding/调整笔风时先读） | ❌ |
| **笔风** | `adjust_style` | `style_tools.py:80` | `project_id` / `style_pack_id` | `AdjustStyleResult` | 管家（写入 style_pack_id） | ❌ |
| **Onboarding** | `verify_world_tree_baseline` | `onboarding_tools.py:45` | `project_id` | `VerifyWorldTreeBaselineOutput`（ready / missing_items / all_items） | 管家（Onboarding 6 项校验 spec §5.6） | ❌ |
| **委托** | `delegate_to_agent` | `delegation_tools.py:110` | `agent` (novel_writer / world_tree_manager) / `intent` / `task` / `project_id` / `mode` (analyze / full_baseline) | `DelegateToAgentOutput` | 管家（用户在等结果时同步委托） | ❌ |
| **委托** | `dispatch_background_task` | `delegation_tools.py:374` | `agent` / `task_type` / `project_id` / `task` | `DispatchBackgroundTaskOutput` | 管家（用户不等待的维护任务，结果走 WS push） | ❌ |
| **章节** | `generate_chapter` | `chapter_tools.py:30` | `project_id` / `content` (≥100 字) / `intervention` (可选) | `ChapterContent`（num / title / content / word_count / generated_at / summary） | 文笔家 LLM 写完正文后落盘 | ❌（**有 per-project 锁**，并发返回 409） |
| **章节** | `read_chapter` | `chapter_tools.py:131` | `project_id` / `chapter_num` | `ChapterContent` | 文笔家/Validator（"重读第 N 章"用） | ❌ |
| **章节** | `summarize_chapter` | `summarize_chapter_tool.py:31` | `project_id` / `chapter_num` / `content` (≥100 字) | `SummarizeChapterOutput`（summary + method: sentinel / fallback_truncate / llm_fallback） | 文笔家（生成章节后抽 1 句话 summary） | ❌ |
| **卷** | `generate_volume_summary` | `volume_tools.py:22` | `project_id` / `volume_id` / `auto_complete_volume` (bool) | `GenerateVolumeSummaryOutput`（summary / summary_len / auto_completed / status） | 文笔家（本卷所有章节都生成完后调，v0.9.5 新增） | ❌ |
| **基座编辑** | `update_base` | `base_edit_tools.py:20` | `project_id` / `key` (7 件名 Literal) / `new_value` | `UpdateBaseResult` | 架构师（整段写入 7 件之一） | ❌ |
| **基座编辑** | `edit_artifact` | `edit_artifact_tool.py:15` | `project_id` / `target` (13 个 Literal) / `operation` (add/update/delete) / `identifier` / `data` | `EditArtifactResult` | 架构师（结构化增量编辑 6 件基座，36 种组合） | ❌ |
| **基座编辑** | `edit_artifact_batch` | `edit_artifact_tool.py:756` | `project_id` / `items` (1-50 个) / `atomic` (bool) | `EditArtifactBatchResult` | 架构师（v0.9.1 新增：1 tool_call 落 N 行；atomic=true 任一失败全回滚） | ❌ |
| **基座编辑** | `rollback_base` | `base_edit_tools.py:50` | `project_id` / `to_chapter` (≥1) / `confirm: Literal[True]` | `ProjectDetail` | 架构师/管家（回档到指定章节） | ✅ |
| **基座编辑** | `weave_plot` | `plot_tools.py:42` | `project_id` / `plot_seed` | `WeavePlotResult`（3 段式 next_chapter_plan） | 架构师（编排下一段剧情） | ❌ |
| **基座编辑** | `introspect_character` | `character_tools.py:16` | `project_id` / `character_name` | `IntrospectResult`（character_card + inner_monologue） | 架构师（角色内省） | ❌ |
| **基座编辑** | `switch_pov` | `pov_tools.py:14` | `project_id` / `new_pov_char_id` (char-xxxxxxxx) | `SwitchPovResult`（previous + new + new_pov_name） | 架构师（切换 POV 角色） | ❌ |
| **图片** | `generate_image` | `image_tools.py:19` | `project_id` / `style_hint` (可选) | `ImageResult`（image_url / generated_at / cache_hit） | 管家（生成主立绘，按 prompt hash 缓存，**唯一**调 Gemini 图像的入口） | ❌ |

> **删除的工具**（v0.6/v0.7 已删，**不在 v0.9.6 工具集**）：`onboarding_propose_step` / `onboarding_user_confirm` / `onboarding_generate_chapter`（旧 5 步 Onboarding，OnboardingController 整体废弃后随工具集删除）。
> 
> **历史工具**（v0.6.2 删）：`ChapterGeneratorSpecialist` / `WorldTreeKeeperSpecialist` / `MemoryKeeperSpecialist`（`specialists.py` 旧版）—— 3 个 Specialist Agent 整体下沉到 `tools/` 下的同名 tool，类被删除。

### 9.4 工具白名单是 v0.6 重大变更

> **v0.6 工具白名单改造**——这是系统架构最关键的设计转折之一。

**改造前**（v0.5 之前）：

- Specialist 抽象层（`SpecialistAgent` ABC + 3 个具体类）
- 管家**直接调** LLM 工具做基座修改
- 文笔家走 `generate_chapter_via_specialist` 单步函数
- 工具集按"系统级"授权，**没有 Agent 维度的白名单**

**v0.6 改造后**（`registry.py:18-67` + 多个工具模块的 v0.6.2 注释）：

1. **AGENT_TOOLS 白名单显式化**：每个 Agent 走 `executor.execute()` 前，由 `ToolRegistry.get_agent_tools(agent_name)` 读白名单 → 拿 `BaseTool` 实例列表 → 转 OpenAI tools schema
2. **v0.8 进一步收紧管家**：管家**禁止直接修改世界树基座**（`edit_artifact` / `update_base` 从管家白名单移除），改基座必须走 `delegate_to_agent(agent="world_tree_manager", intent="intervention")`——**这是 v0.8 委托关系图清晰化的基础**
3. **v0.6.2 删除 Specialist 抽象层**（`specialists/__init__.py:1-22`）：3 个 Specialist Agent 类 + Stub 别名 + `ImageGeneratorStub` + `generate_chapter_via_specialist` 全部删除，能力下沉到 tools
4. **v0.9.1 引入批量工具**：`edit_artifact_batch` 让 WTM ReAct 落库 9 张表从"N round-trip"变成"1 round-trip"，原子事务支持
5. **v0.9.5 引入卷总结工具**：`generate_volume_summary` 让文笔家在卷末生成 1000 字总结供后续卷 context 复用

**设计意图**：
- **职责清晰**：管家 = 项目/对话/委托，文笔家 = 写章节，架构师 = 基座
- **防误操作**：管家不直接改基座 → 改基座前必须经过 WTM 分析 + Validator 校验
- **执行效率**：批量工具 + 锁机制保证并发安全
- **可测试性**：`register_agent_tools(agent_name, [...], replace=True)` 运行时动态授权，测试可注入 mock 工具

### 9.5 数据流示例 — 用户发"写下一章"

完整 ReAct 链路：

```
[1] 用户 WS 发 "写下一章"
    ↓ ws_manager.handle_user_message (backend/api/ws_manager.py:169)
    │
    │  1.1 落 messages 表（role=user）
    │  1.2 推 WS {"type": "agent_thinking", "content": "正在分析你的消息..."}
    │
[2] NovelSteward.receive(user_message, project_id, user_id, conversation_id)
    │
    │  2.1 拼 session_key = f"{user_id}:{conv_id}:novel_steward"
    │  2.2 cache miss? → load_chat_history(15 轮)  rebuild (specialists §7)
    │  2.3 executor.execute(ReAct loop, max_iterations=15)
    │
    ├─ 2.3.1 加载工具: registry.get_agent_tools("novel_steward") → 11 个 tool
    │         (load_project / create_project / generate_image / update_exploration_level /
    │          list_style_packs / adjust_style / verify_world_tree_baseline /
    │          delegate_to_agent / dispatch_background_task / delete_project / list_projects)
    │  2.3.2 messages 拼装 (context §8): sys_prompt + [summary(可选)] + history + context_message + current user
    │  2.3.3 LLM 思考 → 决定调 delegate_to_agent
    │         │
    │         │   → DelegateToAgentTool.run (tools/delegation_tools.py:130)
    │         │     agent="novel_writer", intent="intervention", task="写下一章"
    │         │
    │         └─► [3] 委托 NovelWriter
    │
[3] NovelWriter.delegate_chapter_generation(project_id, intervention, ...)
    (agents/novel_writer.py:265)
    │
    │  3.1 _validate_world_tree_completeness(project_id)
    │      └─ 校验 7 件基座齐：world_tree / characters / main_plot / volumes / style_pack
    │  3.2 executor.execute(agent=novel_writer, ...)  ReAct loop
    │         │
    │         │   加载工具: registry.get_agent_tools("novel_writer") → 5 个
    │         │     (load_project / read_chapter / generate_chapter / summarize_chapter / generate_volume_summary)
    │         │
    │         │   sys_prompt: build_writer_system_prompt (prompts §8.2)
    │         │     = 身份 + 笔风(style_packs) + 法则(writing_laws) + 红线 + 探索度 + 基座定调
    │         │   context_message: build_project_context_message (v0.9.4 5 条)
    │         │     = main_plot 未完成 + sub_plot 未完成 + characters 全量 + seeds 未了结 + 章节按卷摘要
    │         │
    │         │   LLM 思考 1: 调 load_project 看全貌 (load_project via 锁+ DB)
    │         │   LLM 思考 2: 调 read_chapter 看上一章 (如果有)
    │         │   LLM 思考 3: 写正文 3000-4500 字（按 style_packs + writing_laws + 探索度）
    │         │   LLM 思考 4: 调 generate_chapter(content, project_id, intervention)
    │         │         │
    │         │         │  → GenerateChapterTool.run (tools/chapter_tools.py:52)
    │         │         │    1. 拿当前章节数 → next_num
    │         │         │    2. 标 generating (ChapterStatusRepository)
    │         │         │    3. 写文件 data/projects/{id}/chapters/chapter_NNN.md
    │         │         │    4. 入 DB (ChapterRepository.create)
    │         │         │    5. 提取标题 (# 第 N 章 行)
    │         │         │    6. 返回 ChapterContent(num/title/content/word_count/...)
    │         │         │
    │         │   LLM 思考 5: 调 summarize_chapter(content, project_id)
    │         │         │
    │         │         │  → SummarizeChapterTool.run (tools/summarize_chapter_tool.py:42)
    │         │         │    1. sentinel 解析 (specialists/chapter_summarizer.py:26)
    │         │         │    2. fallback: 正文前 100 字截断
    │         │         │    3. llm_fallback: 单独 LLM 生成
    │         │         │    4. 写 DB ChapterRepository.update_summary
    │         │         │
    │         │   LLM 思考 6: final_response = "已落盘第 N 章《XXX》(X 字)，摘要: ..."
    │         │
    │  3.3 ConsistencyChecker.check_hard_rules()  — 硬约束违例扫描
    │  3.4 ConsistencyChecker.check_world_entries()  — 知识库矛盾检测（默认不阻断）
    │  3.5 Validator.validate_chapter()  v0.9 章节内容校验
    │         │
    │         ├─ PASS/WARN → 放行
    │         ├─ BLOCKED → _retry_chapter_generation() 1 次
    │         │     └─ session_key 加 chapter_num 隔离（v0.9.6 防多章 retry 累积）
    │         │     └─ 注入 issues 到 user_message 重写
    │         │     └─ 再次调 Validator
    │         └─ 仍 BLOCKED → chapter_content 头部加注释 <!-- [unverified] ... -->
    │
    │  3.6 章节落盘完成 → chapter_validation 写入 ChapterOutput
    │
    └─ 返回 DelegateToAgentOutput(success=True, response=..., tool_calls_trace=[...])
    │
[4] 管家拿到 NovelWriter 的结果，整合到自己的 final_response
    │
[5] 推 WS: tool_calling + tool_result 流（_push_agent_trace, ws_manager.py:271）
    │
[6] 推 WS: agent_message（最终回复）+ structured_data
    │
[7] 落 messages 表（role=assistant + tool_calls 字段含 intent / downstream_called）
    │
[8] 前端收到 agent_message → 渲染章节 + 摘要
```

**关键节点**：

| 节点 | 文件 | 行号 |
|---|---|---|
| WS 入口 | `backend/api/ws_manager.py:169` | `handle_user_message` |
| 管家入口 | `agents/novel_steward.py:188` | `NovelSteward.receive` |
| 委托工具 | `tools/delegation_tools.py:110` | `DelegateToAgentTool` |
| 章节生成委托 | `agents/novel_writer.py:265` | `delegate_chapter_generation` |
| 章节落盘 | `tools/chapter_tools.py:30` | `GenerateChapterTool` |
| Summary 抽取 | `tools/summarize_chapter_tool.py:31` | `SummarizeChapterTool` |
| Summary sentinel 解析 | `specialists/chapter_summarizer.py:26` | `extract_summary_from_llm_output` |
| 章节校验 | `agents/validator.py:213` | `Validator.validate_chapter` |
| WS 推送 | `api/ws_manager.py:271` | `_push_agent_trace` |

> **完整链路涉及的模块**：`ws_manager` → `novel_steward` → `executor` → `delegation_tools` → `novel_writer` → `executor` → `chapter_tools` → `summarize_chapter_tool` → `chapter_summarizer` → `validator` → `executor` → `novel_steward` → `ws_manager`。
> 
> **核心 ReAct 工具调用链**（NovelWriter 内）：`load_project` → `read_chapter` → `generate_chapter` → `summarize_chapter` → `final_response`。**5 步闭环**，每步都是结构化 Pydantic 输入/输出。

