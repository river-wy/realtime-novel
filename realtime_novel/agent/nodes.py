"""6 个节点函数（intake → consult_experts → plan → act → reflect → respond）

对应 core.md §B.2.2

v0.4 简化版：
- intake: 简单 keyword 匹配 intent（不调真实 LLM）
- consult_experts: 返回 3 个 stub 意见
- plan: 简单映射 intent → tool
- act: 调 13 个工具之一
- reflect: 检查 result 是否 is_ok
- respond: 简单包装 result 为文本
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from realtime_novel.agent.state import AgentState, Intent, ExpertOpinion, ToolCall
from realtime_novel.agent.specialists import (
    ChapterGeneratorStub, WorldTreeKeeperStub, MemoryKeeperStub,
)
from realtime_novel.agent.tools import get_tool


# ============ intake ============

async def intake_node(state: AgentState) -> dict:
    """节点 1：解析用户输入，输出 intent

    v0.4.1 增强：可选调 LLM（传 history_messages + system_prompt）
    - 如果 state.system_prompt 为空 → 走 v0.4 简化版（keyword 匹配）
    - 如果 state.system_prompt 非空 → 调 LLM 解析 intent（带多轮上下文）
    """
    if not state.system_prompt:
        # v0.4 简化版（keyword 匹配）
        return _intake_keyword(state.user_message)
    return await _intake_llm(state)


def _intake_keyword(user_message: str) -> dict:
    """v0.4 keyword 匹配版"""
    msg = user_message.lower()
    if "删除" in msg or "delete" in msg:
        intent = Intent.CHAT
    elif "生成" in msg or "写" in msg or "generate" in msg or "下一章" in msg:
        intent = Intent.GENERATE
    elif "回滚" in msg or "rollback" in msg:
        intent = Intent.ROLLBACK
    elif "干预" in msg or "intervene" in msg or "加点" in msg:
        intent = Intent.INTERVENE
    elif "改" in msg and any(k in msg for k in ["基座", "风格", "pov", "风格"]):
        intent = Intent.ADJUST_BASE
    elif "创建" in msg or "create" in msg or "新项目" in msg:
        intent = Intent.CREATE_PROJECT
    else:
        intent = Intent.CHAT
    return {"intent": intent}


async def _intake_llm(state: AgentState) -> dict:
    """v0.4.1 LLM 版（带多轮上下文）"""
    from realtime_novel.adapters.llm_adapter import get_llm_adapter
    from realtime_novel.adapters.types import ModelRole
    from realtime_novel.agent.context_builder import build_messages_for_node

    adapter = get_llm_adapter()

    # 拼 messages（system + history + current user）
    # 管家 system prompt 可以包含意图枚举
    intent_enum_text = "\n".join([f"- {i.value}: {i.name}" for i in Intent])
    full_system = f"""{state.system_prompt}

## Intent 分类参考
{intent_enum_text}

## 输出格式
只输出一个 intent 单词（不加解释）：
generate / intervene / rollback / adjust_base / create_project / chat
"""
    messages = build_messages_for_node(
        conversation_id=state.conversation_id,
        current_user_message=state.user_message,
        max_history=20,
        system_prompt=None,  # system 走 system_prompt 字段
    )
    try:
        response = await adapter.complete_with_messages(
            messages=messages[1:],  # 去掉 system（下面传）
            system_prompt=full_system,
            max_tokens=20,
            temperature=0.2,
            role=ModelRole.TEXT,
        )
        intent_str = response.content.strip().lower()
        # 解析为 Intent enum
        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.CHAT  # fallback
        return {"intent": intent, "history_messages": messages}
    except Exception as e:
        # LLM 失败 → fallback keyword
        return _intake_keyword(state.user_message)


# ============ consult_experts ============

async def consult_experts_node(state: AgentState) -> dict:
    """节点 2：并行咨询 3 个专家 stub

    v0.4.1：传 history_messages 让专家看到多轮上下文
    """
    chapter_stub = ChapterGeneratorStub()
    world_stub = WorldTreeKeeperStub()
    memory_stub = MemoryKeeperStub()
    # 拼 context（含 intent + history_messages）
    common_context = {
        "intent": state.intent.value if state.intent else "",
        "history_messages": state.history_messages or [],
    }
    results = await asyncio.gather(
        chapter_stub.consult(common_context),
        world_stub.consult(common_context),
        memory_stub.consult(common_context),
    )
    opinions = []
    for r in results:
        opinions.append(ExpertOpinion(
            expert_name=r.get("expert_name", "unknown"),
            opinion=r.get("opinion", ""),
            confidence=r.get("confidence", 0.8),
            suggested_actions=r.get("suggested_actions", []),
        ))
    return {"expert_opinions": opinions}


# ============ plan ============

async def plan_node(state: AgentState) -> dict:
    """节点 3：综合意见生成 plan（intake → plan 简化映射）"""
    intent_to_tool = {
        Intent.GENERATE: ("generate_chapter", {}),
        Intent.ROLLBACK: ("rollback_base", {}),
        Intent.INTERVENE: ("update_base", {}),
        Intent.ADJUST_BASE: ("adjust_style", {}),
        Intent.CREATE_PROJECT: ("create_project", {}),
        Intent.CHAT: ("", {}),  # 自由对话不调工具
    }
    tool_name, tool_args = intent_to_tool.get(
        state.intent or Intent.CHAT, ("", {})
    )
    plan = f"基于 intent={state.intent.value if state.intent else 'chat'}，调 {tool_name or '无工具'}"
    return {"plan": plan, "tool_calls": state.tool_calls + [
        ToolCall(tool_name=tool_name, args=tool_args) if tool_name else ToolCall(tool_name="", args={})
    ]}


# ============ act ============

async def act_node(state: AgentState, progress_callback=None) -> dict:
    """节点 4：执行 plan 选中的工具（v0.4 P1-1：透传 progress_callback）"""
    if not state.tool_calls:
        return {"tool_calls": state.tool_calls}
    last_tc = state.tool_calls[-1]
    if not last_tc.tool_name:
        return {"tool_calls": state.tool_calls}
    tool = get_tool(last_tc.tool_name)
    # 构造 input（按 tool.input_schema）
    try:
        input_obj = tool.input_schema(**last_tc.args)
    except Exception as e:
        new_tcs = state.tool_calls[:-1] + [last_tc.model_copy(update={"error": str(e), "duration_ms": 0})]
        return {"tool_calls": new_tcs}
    start = time.time()
    try:
        # 透传 progress_callback
        output = await tool.run(input_obj, progress_callback=progress_callback)
        duration_ms = int((time.time() - start) * 1000)
        # 如果是 ToolError，标 error
        from realtime_novel.agent.tools.base import ToolError
        error = None
        if isinstance(output, ToolError):
            error = output.message
        new_tc = last_tc.model_copy(update={
            "result": output.model_dump() if hasattr(output, "model_dump") else {"_raw": str(output)},
            "duration_ms": duration_ms,
            "error": error,
        })
        return {"tool_calls": state.tool_calls[:-1] + [new_tc]}
    except Exception as e:
        new_tc = last_tc.model_copy(update={"error": str(e), "duration_ms": int((time.time() - start) * 1000)})
        return {"tool_calls": state.tool_calls[:-1] + [new_tc]}


# ============ reflect ============

async def reflect_node(state: AgentState) -> dict:
    """节点 5：检查结果质量，决定重试"""
    if not state.tool_calls:
        return {"error": None}
    last_tc = state.tool_calls[-1]
    if last_tc.error:
        return {"error": last_tc.error}
    return {"error": None}


# ============ respond ============

async def respond_node(state: AgentState) -> dict:
    """节点 6：包装 result 为最终回复

    v0.4.1 增强：可选调 LLM 生成管家语气回复（带多轮上下文）
    """
    # 收集 tool result 摘要
    if not state.tool_calls:
        tool_summary = "无工具调用"
    else:
        last_tc = state.tool_calls[-1]
        if last_tc.error:
            tool_summary = f"工具调用失败: {last_tc.error}"
        elif last_tc.result:
            import json
            tool_summary = json.dumps(last_tc.result, ensure_ascii=False)[:500]
        else:
            tool_summary = "完成"

    if not state.system_prompt:
        # v0.4 简化版（直接拼结果）
        if not state.tool_calls:
            return {"final_response": state.user_message}
        if state.tool_calls[-1].error:
            return {"final_response": f"抱歉，处理失败：{state.tool_calls[-1].error}"}
        if state.tool_calls[-1].result:
            for key in ("content", "image_url", "opinion", "new_pov", "new_chapter_plan", "next_step"):
                if key in state.tool_calls[-1].result:
                    return {"final_response": str(state.tool_calls[-1].result[key])}
            import json
            return {"final_response": json.dumps(state.tool_calls[-1].result, ensure_ascii=False, indent=2)[:500]}
        return {"final_response": "完成"}

    # v0.4.1 LLM 版（带多轮上下文 + 管家语气）
    return await _respond_llm(state, tool_summary)


async def _respond_llm(state: AgentState, tool_summary: str) -> dict:
    """v0.4.1 LLM 版 respond（管家语气 + 多轮上下文）"""
    from realtime_novel.adapters.llm_adapter import get_llm_adapter
    from realtime_novel.adapters.types import ModelRole
    from realtime_novel.agent.context_builder import build_messages_for_node

    adapter = get_llm_adapter()

    full_system = f"""{state.system_prompt}

## 任务
根据工具调用结果，用你的身份语气生成自然语言回复给用户。

## 工具调用结果
{tool_summary}
"""
    # 拿 history（包括上轮 assistant + 工具调用的 tool 消息）
    messages = build_messages_for_node(
        conversation_id=state.conversation_id,
        current_user_message=state.user_message,
        max_history=20,
        system_prompt=None,
    )
    try:
        response = await adapter.complete_with_messages(
            messages=messages[1:],
            system_prompt=full_system,
            max_tokens=500,
            temperature=0.7,
            role=ModelRole.TEXT,
        )
        return {
            "final_response": response.content,
            "history_messages": messages,
        }
    except Exception:
        return {"final_response": tool_summary[:500]}


# ============ 条件边 ============

def should_retry(state: AgentState) -> str:
    """reflect 节点的条件边：error + retry_count < 3 → plan"""
    if state.error and state.retry_count < 3:
        return "plan"
    return "respond"


def should_interrupt(state: AgentState) -> str:
    """WS 打断标记"""
    if state.interrupt_requested:
        return "__end__"
    return "respond"
