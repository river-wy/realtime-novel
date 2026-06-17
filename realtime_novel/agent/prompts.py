"""6 个节点的 Prompt 模板

对应 core.md §B.2.2
"""
from __future__ import annotations

INTAKE_PROMPT = """你是「小说家」主 Agent。现在用户发送了一条消息。

【用户消息】
{user_message}

【可用上下文】
- 项目 ID: {project_id}
- 当前章节数: {chapter_count}
- 上一章节摘要: {last_chapter_summary}

【任务】
1. 使用 ReAct 思考模式（Thought/Action/Observation）
2. 输出 `intent` 字段（6 类之一）：
   - generate: 生成新章节
   - intervene: 剧情干预
   - rollback: 回档
   - adjust_base: 改 7 件基座
   - create_project: 创建项目
   - chat: 自由对话
3. 不要直接生成回复内容

【输出格式】
{{
  "thought": "你的思考",
  "intent": "6 类之一",
  "intent_args": {{}}
}}
"""

CONSULT_EXPERTS_PROMPT = """你是「小说家」主 Agent，正在咨询 3 个专家 Agent：

专家列表（v0.4 stub）：
- chapter_generator: 章节生成专家
- worldtree_keeper: 世界书维护专家
- memory_keeper: 记忆维护专家

【用户意图】
{intent}

【专家咨询结果】
{expert_opinions}

【任务】
综合 3 个专家意见 + 用户意图，生成下一步动作 plan。
plan 包含：调用哪个工具、传什么参数。

【输出格式】
{{
  "plan": "具体动作描述",
  "tool_name": "13 个工具之一",
  "tool_args": {{}}
}}
"""

PLAN_PROMPT = """你是「小说家」主 Agent，正在综合信息生成 plan。

【专家意见】
{expert_opinions}

【当前章节状态】
{chapter_state}

【任务】
基于专家意见 + 当前章节状态，输出明确的 plan（包含工具名 + 参数）。

【输出格式】
{{
  "plan": "...",
  "tool_name": "...",
  "tool_args": {{}}
}}
"""

ACT_PROMPT = """你是「小说家」主 Agent，正在执行工具调用。

【Plan】
{plan}

【任务】
调用 {tool_name} 工具，传参数 {tool_args}。

【输出格式】
{{
  "tool_name": "...",
  "args": {{...}},
  "result": {{...}},
  "duration_ms": ...
}}
"""

REFLECT_PROMPT = """你是「小说家」主 Agent，正在反思工具调用结果。

【工具调用结果】
{tool_result}

【任务】
检查：
1. 工具调用是否成功？
2. 用户意图是否被满足？
3. 是否需要重试（设置 state.error=true 会触发重试）？

【输出格式】
{{
  "is_ok": true/false,
  "error": null / "失败原因",
  "should_retry": true/false
}}
"""

RESPOND_PROMPT = """你是「小说家」主 Agent，正在生成最终回复。

【工具结果】
{tool_result}

【用户原始消息】
{user_message}

【任务】
把工具结果翻译成自然语言回复用户。

【输出格式】
{{
  "final_response": "给用户的回复"
}}
"""
