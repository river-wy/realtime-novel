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

    v0.4 简化版：keyword 匹配（不调 LLM）
    """
    msg = state.user_message.lower()
    if "删除" in msg or "delete" in msg:
        intent = Intent.CHAT  # delete 走 agent 二次确认，先按 chat 处理
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


# ============ consult_experts ============

async def consult_experts_node(state: AgentState) -> dict:
    """节点 2：并行咨询 3 个专家 stub"""
    chapter_stub = ChapterGeneratorStub()
    world_stub = WorldTreeKeeperStub()
    memory_stub = MemoryKeeperStub()
    results = await asyncio.gather(
        chapter_stub.consult({"intent": state.intent.value if state.intent else ""}),
        world_stub.consult({"intent": state.intent.value if state.intent else ""}),
        memory_stub.consult({"intent": state.intent.value if state.intent else ""}),
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
    """节点 6：包装 result 为最终回复"""
    if not state.tool_calls:
        return {"final_response": state.user_message}
    last_tc = state.tool_calls[-1]
    if last_tc.error:
        return {"final_response": f"抱歉，处理失败：{last_tc.error}"}
    # 取 result 第一个有内容的字段
    if last_tc.result:
        result = last_tc.result
        # 尝试取 'content' / 'image_url' / 'opinion' 等
        for key in ("content", "image_url", "opinion", "new_pov", "new_chapter_plan", "next_step"):
            if key in result:
                return {"final_response": str(result[key])}
        # 兜底：序列化 result
        import json
        return {"final_response": json.dumps(result, ensure_ascii=False, indent=2)[:500]}
    return {"final_response": "完成"}


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
