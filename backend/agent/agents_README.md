# Agent 角色矩阵（v0.6 novel-steward 迭代）

> **对应 spec**：`.spec/m-v0.6-novel-steward/spec.md §3`
> **创建**：2026-06-24（s2 抽象定义阶段）
> **状态**：🟡 骨架已落地（s2），实装在 s3/s4

---

## 1. 3 顶层 Agent

### 1.1 小说管家 NovelSteward

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/novel_steward.py` |
| **类** | `NovelSteward` |
| **工厂方法** | `get_novel_steward()` |
| **职责** | 唯一用户入口 + 意图识别 + 路由分发 + 接管 Onboarding |
| **调用方** | API 入口（`/api/chat` WebSocket / HTTP POST） |
| **被调方** | NovelWriter, WorldTreeManager, OnboardingAgent（内部） |

**主入口**：
```python
async def receive(
    user_message: str,
    project_id: Optional[str] = None,
    user_id: str = "default",
    in_onboarding: bool = False,
    conversation_id: Optional[str] = None,
) -> dict:
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

### 1.2 小说文笔家 NovelWriter

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/novel_writer.py` |
| **类** | `NovelWriter` |
| **工厂方法** | `get_novel_writer()` |
| **职责** | 章节正文生成 + summary 抽取 + 文风控制 + 历史承接 |
| **调用方** | NovelSteward（intent=GENERATE 时） |
| **被调方** | ChapterGeneratorSpecialist（v0.5 已实装，复用） |

**主入口**：
```python
async def generate_chapter(
    project_id: str,
    user_message: str = "请生成下一章",
    max_history: int = 5,
) -> ChapterOutput:
```

**关键约束**：
- ❌ 不决定剧情走向（走向由世界树基座约束）
- ❌ 不修改任何基座（只读）
- ✅ 调用 MemoryKeeper 检索历史章节上下文（s3 扩展）

### 1.3 世界树管理 WorldTreeManager

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/world_tree_manager.py` |
| **类** | `WorldTreeManager` |
| **工厂方法** | `get_world_tree_manager()` |
| **职责** | 基座一致性 + 干预影响分析 + 种子预留 + 走向调整 + diff 输出 |
| **调用方** | NovelSteward（intent=INTERVENE/ADJUST_BASE 时） |
| **被调方** | WorldTreeKeeperSpecialist（v0.5 已实装，复用） |

**主入口**：
```python
async def analyze_intervention(
    project_id: str,
    intervention_text: str,
    max_history: int = 5,
) -> WorldTreeDiff:
```

**Diff 结构**（核心，对应 spec.md §1.2 目标 3）：
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
- ✅ 调用 MemoryKeeper 检索历史干预（s4 扩展）

---

## 2. 2 内部工具（降级）

### 2.1 MemoryKeeper（记忆专员）

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/specialists.py` 中的 `MemoryKeeperSpecialist` 类 |
| **调用方** | NovelWriter / WorldTreeManager（内部调用） |
| **职责** | 检索历史章节 / 历史干预 / 历史基座版本 |
| **不再是顶层 Agent** | 用户不会直接对它说话 |

### 2.2 ImageGenerator（图片生成）

| 项 | 内容 |
|---|------|
| **文件** | `backend/agent/specialists.py` 中的 `ImageGeneratorStub` 类 |
| **调用方** | NovelSteward（生成封面/插图时） |
| **职责** | 调 Gemini 生成图片 |
| **不再是顶层 Agent** | 由管家内部调用 |

---

## 3. 废弃/删除的模块

| 模块 | 状态 | 替代 |
|------|------|------|
| `backend/agent/state_graph.py` | 🟡 简化（v0.6 s3 阶段删除 6 节点 StateGraph） | 3 个 Agent 直接路由 |
| `backend/agent/state_graph_stub.py` | 🟡 简化（保留 generate_summary 部分） | 同上 |
| `backend/agent/onboarding_agent.py` | 🟡 重命名/合并（v0.6 s3 阶段） | 合并到 NovelSteward 的 onboard 分支 |
| `backend/agent/onboarding_hooks.py` | ✅ 保留 | 事件总线订阅（不专属 Onboarding） |
| `backend/agent/nodes.py` | 🟡 简化（v0.6 s3 阶段） | StateGraph 删除后无节点概念 |
| `backend/agent/specialists.py` | ✅ 保留 + 重构 | SpecialistAgent ABC 废除；3 个 specialist 降级为内部工具 |
| `backend/services/intervention_parser.py` | ❌ 删除（v0.6 s4 阶段） | 合并到 WorldTreeManager |

---

## 4. 路由协议（管家大厅 vs 项目管家）

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

## 5. Intent 完整枚举（v0.6 拍板）

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

## 6. s2 阶段交付物（已完成）

- ✅ `backend/agent/intent_recognizer.py` - 意图识别器（实装）
- ✅ `backend/agent/novel_steward.py` - 小说管家骨架（路由逻辑 + 占位响应）
- ✅ `backend/agent/novel_writer.py` - 小说文笔家骨架（委托给 ChapterGeneratorSpecialist）
- ✅ `backend/agent/world_tree_manager.py` - 世界树管理骨架（委托给 WorldTreeKeeperSpecialist + WorldTreeDiff schema）
- ✅ `backend/agent/state.py` - Intent 枚举扩展（加 6 类）+ AgentState 适配新流程
- ✅ `backend/agent/agents_README.md` - 本文件

## 7. s3/s4 阶段待办

### s3（管家实装）
- [ ] 实装 `_handle_list_projects` / `_handle_query_projects` / `_handle_recommend_projects`
- [ ] 实装 `_handle_create_project`（启动 Onboarding）
- [ ] 实装 `_handle_open_project`（LLM 模糊匹配 + 用户确认）
- [ ] 实装 `_handle_adjust_global_pref`（写 user_preferences）
- [ ] 实装 `_handle_generate`（调用 NovelWriter.generate_chapter）
- [ ] 重写 `backend/api/ws_manager.py`（统一进 /api/chat）

### s4（世界树管理实装）
- [ ] 实装一致性检查器（`backend/services/consistency_checker.py`）
- [ ] 完善 WorldTreeDiff 的 base_updates / plot_adjustments / new_seeds 解析
- [ ] 实装 risk_level 评估（基于改动数量）
- [ ] 删除 `backend/services/intervention_parser.py`（合并完成）
- [ ] 处理 requires_double_confirm 的 UI 弹窗逻辑