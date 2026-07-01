# Agent 角色矩阵（v0.6.1 重塑版）

> **对应 spec**：`.spec/m-v0.6-novel-steward/spec.md §3`
> **重写日期**：2026-06-25（v0.6.1 agent/ 模块重塑完成）
> **状态**：✅ 全部完成（v0.6 端到端已实装 + 跑通）

---

## 1. 架构总览

v0.6.1 重塑后，`backend/agent/` 按"**目录 = 抽象边界**"重组为 7 个模块：

```
backend/agent/
├── agents/         ← 3 顶层 Agent（用户直接对话）
├── runtime/        ← ReAct 引擎（执行/路由/状态）
├── onboarding/     ← 5 步流程统一入口（吸收原 OnboardingAgent）
├── specialists/    ← 内部专家工具（降级，不再是顶层 Agent）
├── context/        ← 上下文/工具（按角色裁剪 messages）
├── prompts/        ← Prompt 模板集中
└── tools/          ← 13 个工具（ToolRegistry）
```

---

## 2. 3 顶层 Agent（agents/）

### 2.1 小说管家 NovelSteward

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/agents/novel_steward.py` |
| **类** | `NovelSteward` |
| **工厂方法** | `get_novel_steward()` |
| **职责** | 唯一用户入口 + 意图识别 + 路由分发 + 接管 Onboarding |
| **调用方** | API 入口（`/api/chat` WebSocket / HTTP POST） |
| **被调方** | NovelWriter, WorldTreeManager, OnboardingController（内部） |

**主入口**：
```python
async def receive(
    user_message: str,
    project_id: Optional[str] = None,
    user_id: str = "default",
    in_onboarding: bool = False,
    conversation_id: Optional[str] = None,
) -> dict
```

**响应结构**：
```python
{
    "intent": str,           # Intent 枚举值
    "confidence": float,     # 0.0~1.0
    "response": str,         # 对用户的最终回复（自然语言）
    "structured_data": dict, # 结构化数据（项目列表/跳转 URL/确认卡片等）
    "downstream_called": str | None,  # 调用的下游 Agent 名
}
```

**关键约束**：
- ❌ 不直接修改世界树基座（转发给 WorldTreeManager）
- ❌ 不直接生成章节正文（转发给 NovelWriter）
- ❌ 不分析干预影响（转发给 WorldTreeManager）
- ✅ 只负责「听懂用户 → 找对人 → 回话」

### 2.2 小说文笔家 NovelWriter

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/agents/novel_writer.py` |
| **类** | `NovelWriter` |
| **工厂方法** | `get_novel_writer()` |
| **职责** | 章节正文生成 + summary 抽取 + 文风控制 + 历史承接 |
| **调用方** | NovelSteward（intent=GENERATE 时） |
| **被调方** | ChapterGeneratorSpecialist（`backend/agent/specialists/specialists.py`） |

**主入口**：
```python
async def generate_chapter(
    project_id: str,
    user_message: str = "请生成下一章",
    max_history: int = 5,
) -> ChapterOutput
```

**关键约束**：
- ❌ 不决定剧情走向（走向由世界树基座约束）
- ❌ 不修改任何基座（只读）
- ✅ 调用 MemoryKeeper 检索历史章节上下文

### 2.3 世界树管理 WorldTreeManager

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/agents/world_tree_manager.py` |
| **类** | `WorldTreeManager` |
| **工厂方法** | `get_world_tree_manager()` |
| **职责** | 基座一致性 + 干预影响分析 + 种子预留 + 走向调整 + diff 输出 |
| **调用方** | NovelSteward（intent=INTERVENE/ADJUST_BASE 时） |
| **被调方** | WorldTreeKeeperSpecialist（`backend/agent/specialists/specialists.py`） |

**主入口**：
```python
async def analyze_intervention(
    project_id: str,
    intervention_text: str,
    max_history: int = 5,
) -> WorldTreeDiff
```

**Diff 结构**（核心）：
```python
{
    "intent": "intervene",
    "summary": "一句话总结这次干预的影响",
    "base_updates": [        # 7 件基座的字段级更新
        {"artifact": "character_card", "field": "师父.role",
         "old_value": "师父", "new_value": "幕后反派", "reason": "..."},
    ],
    "plot_adjustments": [    # 主线/支线走向调整
        {"arc": "main_arc", "adjustment": "...",
         "impact_chapters": [3, 5, 12]},
    ],
    "new_seeds": [           # 新埋的种子/伏笔
        {"name": "师父秘密", "trigger": "第 3 章主角发现...",
         "payoff": "第 12 章决战", "estimated_chapter": 3},
    ],
    "consistency": {         # 一致性检查结果
        "status": "PASS",
        "conflicts": [],
        "warnings": [],
    },
    "risk_level": "low",     # low/medium/high
    "requires_double_confirm": False,
}
```

**关键约束**：
- ❌ 不生成章节正文（写不是它的职责）
- ❌ 不直接和用户对话（通过管家中转）
- ✅ 调用 MemoryKeeper 检索历史干预

---

## 3. ReAct 运行时（runtime/）

| 文件 | 职责 |
|---|------|
| `executor.py` | ReAct loop 引擎 + Middleware 后置节点插槽 |
| `intent_recognizer.py` | Intent 分类（v0.6.1 后管家已不调用，保留备用） |
| `state.py` | Intent 枚举 + AgentState 数据类 |

**ReAct loop 工作流**：
1. 调 LLM（带 tools 列表）
2. LLM 决定调工具 / 输出 final_response
3. 调工具 → 结果回传 LLM → 下一轮
4. 退出条件：① final_response ② max_iterations ③ 死循环检测
5. 退出后依次执行后置 Middleware 节点

**AgentOutput 标准化（v0.6.2）**：
```python
class AgentOutput(BaseModel):
    final_response: str           # LLM 自然语言回复
    structured_data: dict         # 工具产生的结构化数据（由 tool/middleware 写入）
    tool_calls_history: List[dict]
    iterations: int
    error: Optional[str]
    needs_review: bool            # 后置节点可标记需人工审核
    skip_response: bool           # 后置节点可拦截回复
```

**Middleware 后置节点插槽（v0.6.2）**：
```python
executor = get_agent_executor()

@executor.middleware()                        # 全局（所有 Agent）
async def safety_check(output, ctx): ...

@executor.middleware(agent_name="novel_writer")  # 仅对文笔家生效
async def quality_check(output, ctx): ...

executor.add_middleware(fn, agent_name=None)  # 编程式注册
```

---

## 4. Onboarding 5 步（onboarding/）

| 文件 | 职责 |
|---|------|
| `controller.py` | 5 步统一入口（HTTP 5 步端点 + WS Step 3/4 推演共享） |
| `hooks.py` | 事件总线订阅（Step 4 完成后生成项目名 + 封面图） |

**v0.6.1 重大变更**：
- ❌ 删除 `backend/agent/onboarding_agent.py`（v0.5 旧版）
- ✅ `OnboardingController` 吸收原 `OnboardingAgent` 全部能力（DB 读 / context_builder / LLM 调 / JSON 解析 / Pydantic 校验 / 重新提议检测）
- ✅ 暴露统一入口：`OnboardingController.consult(project_id, step, user_message, current_fields)`
- ✅ HTTP 5 步端点仍走 `OnboardingFlow` 状态机（service），Step 3/4 走 controller LLM 推演
- ✅ `_generate_project_name` 从 onboarding_agent 移入 hooks.py（事件触发时调用）

**能力清单**：
- Step 1-2: 按钮交互（题材/风格/基调 + palette）
- Step 3-4: LLM 多轮推演（`controller.consult()`）
- Step 5: 调 NovelWriter 生成第 1 章
- 重新提议检测（11 关键词）
- 完整 LLM CALL/RESPONSE/PARSE 边界日志

---

## 5. 内部专家工具（specialists/）

| 文件 | 职责 |
|---|------|
| `specialists.py` | 3 specialist + ImageGeneratorStub + 章节生成包装 |
| `chapter_summarizer.py` | 章节 summary 抽取（sentinel 解析 + fallback） |
| `exploration.py` | 探索度参数 (conservative/standard/wild) |

**3 个 Specialist**（v0.5 降级为内部工具，v0.6.1 仍降级）：

| 类 | 文件位置 | 调用方 |
|---|---|---|
| `ChapterGeneratorSpecialist` | `specialists/specialists.py` | NovelWriter |
| `WorldTreeKeeperSpecialist` | `specialists/specialists.py` | WorldTreeManager |
| `MemoryKeeperSpecialist` | `specialists/specialists.py` | NovelWriter / WorldTreeManager |
| `ImageGeneratorStub` | `specialists/specialists.py` | 管家（生成封面/插图） |

**v0.6.1 重大变更**：
- ❌ 删除 `backend/agent/state_graph_stub.py`（v0.4 残留）
- ✅ 全部能力吸收到 `specialists.py:generate_chapter_via_specialist()`
- ❌ 删除 `backend/services/chapter_generator.py`（dead service，42 行仅包一层日志）

**章节生成新入口**：
```python
from backend.agent.specialists.specialists import generate_chapter_via_specialist

result = await generate_chapter_via_specialist(
    project_id=project_id,
    intervention=intervention,         # 可选（v003 删 actor_feedback/actor_character）
)
# 返回 {num, title, content, file_path, word_count, summary}
```

---

## 6. 上下文/工具（context/）

| 文件 | 职责 |
|---|------|
| `builders.py` | 3 角色 messages 拼装 + 通用 node builder |
| `onboarding_builders.py` | Step 3/4 推演 messages 拼装 |
| `_helpers.py` | 私有 helper（DB 转换 + 字段格式化 + json_dumps） |
| `style_inference.py` | style_charter 字段推断（12 风格 + 7 基调 + 5 题材映射） |

**v0.6.1 重大变更**：
- ❌ 删除 `backend/agent/context_builder.py`（745 行单文件）
- ✅ 拆为 3 文件（`_helpers.py` / `builders.py` / `onboarding_builders.py`）
- ✅ `__init__.py` re-export 7 公共 API，保持外部 import 路径不变

**公开 API**（从 `backend.agent.context` import）：
```python
build_messages_for_steward
build_messages_for_worldtree_keeper
build_messages_for_chapter_generator
build_messages_for_onboarding_step3
build_messages_for_onboarding_step4
build_messages_for_node
load_history_messages
```

---

## 7. Prompt 集中（prompts/）

| 文件 | 职责 |
|---|------|
| `specialists.py` | 3 个 specialist prompt (WORLDTREE/CHAPTER/MEMORY) |
| `onboarding.py` | Step 3/4 推演 prompt (ONBOARDING_STEP3/STEP4) |
| `__init__.py` | re-export 5 活 prompt |

**v0.6.1 重大变更**：
- ❌ 删除 9 个 v0.4 死 prompt（无外部引用）：
  - `INTAKE_PROMPT` / `CONSULT_EXPERTS_PROMPT` / `PLAN_PROMPT` / `ACT_PROMPT` / `REFLECT_PROMPT` / `RESPOND_PROMPT`（v0.4 6 节点 StateGraph 时代）
  - `CHAPTER_SUMMARY_PROMPT` / `CHAPTER_DETAILED_SUMMARY_PROMPT` / `CONVERSATION_SUMMARY_PROMPT`（旧版 summary）
- ✅ 拆 `prompts.py` 386 行 → 2 文件 + __init__ re-export

---

## 8. 工具（tools/）

15 个工具，由 `ToolRegistry` 统一管理（v0.6.2 新增 2 个委托工具）：

| 类别 | 文件 | 工具名 |
|---|---|---|
| 基础 | `base.py` / `base_edit_tools.py` | — / `update_base` `rollback_base` |
| 章节 | `chapter_tools.py` | `generate_chapter` `read_chapter` |
| 角色 | `character_tools.py` | `introspect_character` |
| 情节 | `plot_tools.py` | `weave_plot` |
| 视角 | `pov_tools.py` | `switch_pov` |
| 项目 | `project_tools.py` | `load_project` `create_project` `delete_project` |
| 风格 | `style_tools.py` | `adjust_style` |
| 图片 | `image_tools.py` | `generate_image` |
| 通用 | `edit_artifact_tool.py` | `edit_artifact` |
| Onboarding（v0.7.1 合并后）| `onboarding_tools.py` | `verify_world_tree_baseline` |
| **委托** | **`delegation_tools.py`** | **`delegate_to_agent`**（含 mode=analyze 写章节前 / mode=full_baseline Onboarding）`dispatch_background_task` |
| Schema | `schemas.py` | — |
| Registry | `registry.py` | — |
| Locks | `locks.py` | — |

**v0.6.2 新增：委托工具**

| 工具 | 语义 | 适用场景 |
|---|---|---|
| `delegate_to_agent` | **同步**委托，管家等待专家结果 | 用户明确等待：生成章节、干预基座 |
| `dispatch_background_task` | **异步**派发，立即返回 task_id | 管家自主识别：更新 summary、生成封面 |

判断原则（写在 STEWARD_SYSTEM_PROMPT）：「用户在等这个结果吗？」→ 是用同步，否用异步。

**ToolRegistry v0.6.2 改进**：
- 新增 `register_agent_tools(agent_name, tools, replace=False)` —— 运行时动态授权（测试/插件）
- 新增 `reset_overrides()` —— 清除运行时覆盖
- 新增 `list_agents()` —— 列出所有已配置 Agent

---

## 9. 路由协议（管家大厅 vs 项目管家）

```
用户消息（带可选 projectId 上下文）
   ↓
NovelSteward.receive(message, project_id=None/str)
   ↓
判断上下文：
   ├─ project_id is None → 「管家大厅」模式
   │     → IntentRecognizer.classify_user_level()
   │     → intent ∈ {LIST, QUERY, RECOMMEND, CREATE, OPEN, ADJUST_GLOBAL_PREF, CHAT}
   │
   └─ project_id is not None → 「项目管家」模式
         → IntentRecognizer.classify_project_level()
         → intent ∈ {GENERATE, INTERVENE, ROLLBACK, ADJUST_BASE, ONBOARDING_CONTINUE, CHAT}
```

---

## 10. Intent 完整枚举（v0.6 拍板）

### 项目级（管家大厅内不响应）
- `GENERATE` - 生成下一章 → NovelWriter
- `INTERVENE` - 剧情干预 → WorldTreeManager
- `ROLLBACK` - 回档 → NovelSteward 直处理（危险操作）
- `ADJUST_BASE` - 调整基座 → WorldTreeManager
- `ONBOARDING_CONTINUE` - Onboarding 多轮对话 → NovelSteward 内部

### 用户级（管家大厅响应）
- `LIST_PROJECTS` - 列出项目 → NovelSteward 直查 DB
- `QUERY_PROJECTS` - 按条件筛选 → NovelSteward 直查 DB
- `RECOMMEND_PROJECTS` - 推荐项目 → NovelSteward 查 DB + LLM 推荐语
- `CREATE_PROJECT` - 创建项目 → NovelSteward 启动 Onboarding
- `OPEN_PROJECT` - 进入项目 → NovelSteward LLM 模糊匹配 + 用户确认
- `ADJUST_GLOBAL_PREFERENCE` - 全局偏好（最小可用：default_exploration_level）
- `CHAT` - 闲聊/问答/不确定 → NovelSteward 调 LLM

---

## 11. 版本历程（参考）

### v0.6.1 重塑（2026-06-25）

| Phase | 任务 | commit |
|---|---|---|
| P0 | 备份 data/ 目录 | (无 commit, data.backup-20260625-1045.tar.gz) |
| P1 | 死代码清场 (state_graph.py / nodes.py / 2 空目录) | `f795d6f` |
| P2 | Onboarding 收口 (controller 吸收 OnboardingAgent 能力 + 删 OnboardingAgent) | `a0f9392` |
| P3 | 17 .py 移位到 6 个子目录 + 6 个新 __init__.py | `52530a7` |
| P4-1 | 拆 context_builder.py 745 行 → 3 文件 | `9720b63` |
| P4-2 | 拆 prompts.py 386 行 → 2 文件 + 删 9 个死 prompt | `003b3a7` |
| P5 | state_graph_stub 归一到 specialists | `e9c7033` |
| P6 | agents_README 重写 | (本 commit) |

**重构原则**（欧尼酱 11:40 拍板）：完整重构不向前兼容 / 目录=抽象边界 / 死代码立刻删 / 文件大小失控就拆

### v0.6.2 架构扩展（2026-06-25）

| 改动 | 文件 | 说明 |
|---|---|---|
| 新增 | `tools/delegation_tools.py` | `delegate_to_agent`（同步）+ `dispatch_background_task`（异步） |
| 改 | `tools/registry.py` | 运行时动态授权 `register_agent_tools()` + `list_agents()` |
| 改 | `tools/__init__.py` | 加入 `delegation_tools` 自动注册 |
| 改 | `agents/novel_steward.py` | STEWARD_SYSTEM_PROMPT 补充专家委托规则 |
| 改 | `runtime/executor.py` | AgentOutput 标准化（`structured_data` / `needs_review` / `skip_response`）+ Middleware 后置节点插槽 |

**架构变化**：管家从"预分类路由"→ 纯 ReAct，通过 `delegate_to_agent` 工具将专家 Agent 纳入 ReAct loop（专家返回结果注入 messages，管家继续推演后回复用户）。`dispatch_background_task` 则通过 EventBus fire-and-forget 触发后台任务，结果由 WS push 推送前端。
