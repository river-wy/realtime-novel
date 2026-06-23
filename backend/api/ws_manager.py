"""WebSocketManager + WS /api/chat 端点

对应 core.md §B.4

Event Schema 定义已迁移到 api/schemas/events.py，此文件只负责：
- WebSocketManager 连接管理
- /api/chat WS 端点
- handle_user_message / handle_onboarding_request_proposal / handle_onboarding_confirm
"""
from __future__ import annotations

import asyncio
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.agent.state import AgentState
from backend.agent.state_graph import build_graph
# Event Schema 统一从 api.schemas.events 导入（不在此处定义）
from backend.api.schemas.events import (  # noqa: F401  (供外部 import 兼容)
    AgentThinkingEvent, ToolCallingEvent, ToolResultEvent, AgentMessageEvent,
    ErrorEvent, InterruptedEvent, ConfirmRequiredEvent,
    OnboardingProposalEvent, OnboardingConfirmedEvent, OnboardingStepDoneEvent,
)
from backend.persistence import (
    ConversationRepository, MessageRole,
)


# ============ WebSocketManager ============

class WebSocketManager:
    """per-user WS 连接 + 活动任务管理"""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.active_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections[user_id] = ws

    async def disconnect(self, user_id: str):
        if user_id in self.connections:
            del self.connections[user_id]
        if user_id in self.active_tasks:
            self.active_tasks[user_id].cancel()
            del self.active_tasks[user_id]

    async def send_event(self, user_id: str, event: dict):
        if user_id in self.connections:
            try:
                await self.connections[user_id].send_json(event)
            except Exception:
                pass

    async def interrupt(self, user_id: str):
        if user_id in self.active_tasks:
            self.active_tasks[user_id].cancel()


# 全局单例
ws_manager = WebSocketManager()


# ============ WS 端点 ============

router = APIRouter()


@router.websocket("/api/chat")
async def chat_endpoint(websocket: WebSocket):
    """WS /api/chat 主对话端点

    流程：
    1. 连接
    2. 接收 user_message
    3. 启动 asyncio.Task（处理消息 + 流式推送）
    4. 接收 interrupt 消息 → 取消任务
    5. 异常断开 → 清理
    """
    user_id = "anonymous"  # v0.4 单机单用户
    await ws_manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                # 启动处理任务
                task = asyncio.create_task(
                    handle_user_message(websocket, user_id, data)
                )
                ws_manager.active_tasks[user_id] = task

            elif msg_type == "interrupt":
                # 打断
                await ws_manager.interrupt(user_id)
                await websocket.send_json({
                    "type": "interrupted",
                    "message": "当前生成已取消",
                })

            elif msg_type == "confirm":
                # 二次确认（v0.4 stub：先 echo）
                await websocket.send_json({
                    "type": "agent_message",
                    "content": f"收到 confirm 消息：{data.get('action', '?')}",
                })

            # ============ m-v0.5-onboarding s1.2: Onboarding WS 路由 ============
            elif msg_type == "onboarding_request_proposal":
                # 客户端请求 Agent 提议 Step N 字段
                # { type: "onboarding_request_proposal", project_id, step: 3|4 }
                task = asyncio.create_task(
                    handle_onboarding_request_proposal(websocket, user_id, data)
                )
                ws_manager.active_tasks[user_id] = task

            elif msg_type == "onboarding_confirm":
                # 用户确认 4 字段, 写 7 件
                # { type: "onboarding_confirm", project_id, step, fields: {...} }
                task = asyncio.create_task(
                    handle_onboarding_confirm(websocket, user_id, data)
                )
                ws_manager.active_tasks[user_id] = task

            else:
                await websocket.send_json({
                    "type": "error",
                    "code": "INVALID_MESSAGE_TYPE",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id)
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "code": "WEBSOCKET_ERROR",
                "message": str(e),
            })
        except Exception:
            pass
        await ws_manager.disconnect(user_id)


async def handle_user_message(ws: WebSocket, user_id: str, data: dict):
    """处理单条 user_message：触发状态机 + 流式推送 (v0.4 P1-2: progress_callback 透传到 act_node)"""
    conv_repo = ConversationRepository()
    try:
        # 1. 创建/获取 active conversation
        # v0.5 拍板 (讨论 1.2): user-valid conversation 一对一, **不**绑 project
        # project_id 只用于 message 上下文 (前端用), conversation 本身是 user 维度
        conversation = await conv_repo.create_conversation(
            user_id=user_id,
        )
        # 2. 写 user message (project_id 存在 message 上下文里, v0.5 拍板 1.2)
        user_msg = await conv_repo.add_message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=data["content"],
            project_id=data.get("project_id"),
        )
        # 3. 推 thinking
        await ws.send_json({
            "type": "agent_thinking",
            "content": "正在分析意图...",
        })
        # 4. 构造 state + 跑 state graph (传 progress_callback)
        state = AgentState(
            user_message=data["content"],
            project_id=data.get("project_id"),
            conversation_id=conversation.id,
            message_id=user_msg.id,
        )
        graph = build_graph()

        async def on_progress(event: dict):
            """P1-2 修复：工具执行进度事件透传到 WS"""
            try:
                await ws.send_json({
                    "type": "tool_progress",
                    "step": event.get("step", ""),
                    "percentage": event.get("percentage", 0),
                })
            except Exception:
                pass

        final_state = await graph.ainvoke(state, progress_callback=on_progress)

        # 5. 推 tool_calling + tool_result + 写 tool message 到 messages
        for tc in final_state.tool_calls:
            if tc.tool_name:  # 跳过空工具调用
                await ws.send_json({
                    "type": "tool_calling",
                    "tool": tc.tool_name,
                    "args": tc.args,
                })
                await ws.send_json({
                    "type": "tool_result",
                    "tool": tc.tool_name,
                    "result": tc.result or {},
                })
                # v0.8.2: 写 tool 消息到 messages 表 (role=TOOL)
                await conv_repo.add_message(
                    conversation_id=conversation.id,
                    role=MessageRole.TOOL,
                    tool_results={
                        "name": tc.tool_name,
                        "args": tc.args,
                        "result": tc.result or {},
                    },
                    project_id=data.get("project_id"),
                )

        # 6. 推最终回复
        await ws.send_json({
            "type": "agent_message",
            "content": final_state.final_response or "完成",
        })

        # 7. 写 assistant message (project_id 存到 message 上下文, v0.5 拍板 1.2)
        await conv_repo.add_message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=final_state.final_response or "",
            tool_calls={"calls": [tc.model_dump() for tc in final_state.tool_calls]},
            project_id=data.get("project_id"),
        )

    except asyncio.CancelledError:
        await ws.send_json({"type": "interrupted", "message": "生成被取消"})
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "code": "GENERATION_FAILED",
            "message": str(e),
        })


# ============ Onboarding 处理器 ============

def _format_user_message_with_current(user_input: str, current_fields: dict) -> str:
    """v0.8.3: 拼接 user message + current_fields 原值, 让 LLM 知道改的是哪个字段

    示例: "主角改成女性\\n\\n[当前字段]\\n- story_core: 主角是男性...\\n- characters: 白云飞..."
    """
    if not current_fields:
        return user_input
    lines = [user_input, "", "[当前字段原值]"]
    for k, v in current_fields.items():
        if v:
            # 截长防超 token
            v_short = v[:200] + "..." if len(v) > 200 else v
            lines.append(f"- {k}: {v_short}")
    return "\n".join(lines)


def _format_fields_as_text(fields: dict, step: int) -> str:
    """v0.8.3: 把 fields dict 转成纯文本摘要, 给 LLM 读 history 时用

    不存 JSON 字符串, 存自然语言描述.
    """
    if not fields:
        return f"Step {step} 提议完成 (无字段)"
    lines = [f"我为 Step {step} 提议了以下大纲:"]
    for k, v in fields.items():
        if v:
            v_short = v[:300] + "..." if len(v) > 300 else v
            lines.append(f"- {k}: {v_short}")
    return "\n".join(lines)


async def handle_onboarding_request_proposal(ws: WebSocket, user_id: str, data: dict):
    """处理 onboarding_request_proposal: 调 OnboardingAgent 生成 4 字段

    v0.8.2: 同步写 user + agent 消息到 messages 表
    v0.8.3: user 消息携带 current_fields 原值 (LLM 改的时候知道改哪个字段)
            agent 消息存纯文本摘要 (LLM 读 history 时像读自然语言)

    Args:
        data: {
            type: "onboarding_request_proposal",
            project_id: str,
            step: 3 | 4,
            user_message?: str,  # 用户修改场景 (e.g. "改一下情感锚点")
            current_fields?: dict,  # 当前已有字段
        }
    """
    from backend.agent.onboarding_agent import OnboardingAgent
    import json
    import time
    from backend.utils.logger import get_logger

    log = get_logger(__name__)
    t0 = time.monotonic()

    project_id = data.get("project_id")
    step = data.get("step")
    user_input = data.get("user_message", "")
    if not project_id or step not in (3, 4):
        log.warning("onboarding_request_proposal invalid: project_id=%s, step=%s", project_id, step)
        await ws.send_json({
            "type": "error",
            "code": "INVALID_ONBOARDING_REQUEST",
            "message": f"Missing project_id or invalid step={step}",
        })
        return

    log.info("onboarding_request_proposal START: project_id=%s, step=%d, user_msg_len=%d, is_regen=%s",
             project_id, step, len(user_input),
             any(kw in user_input for kw in ["重新提议", "重新生成", "再想想", "再想一下", "不一样", "为什么没变", "换个", "重做", "再来", "不同的", "另外的", "其他方案", "再给"]))

    # 0. v0.8.2: 拿/建 conversation, 写 user 消息
    conv_repo = ConversationRepository()
    conversation = await conv_repo.get_or_create_active_conversation(user_id)
    current_fields = data.get("current_fields", {})
    if not user_input:
        # 如果前端没传 user_message, 用默认描述
        user_input = f"请提议 Step {step} 字段"
    # v0.8.3: 拼接 current_fields 原值, 让 LLM 知道要改哪个字段
    user_message_with_current = _format_user_message_with_current(user_input, current_fields)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=user_message_with_current,
        project_id=project_id,
    )

    # 1. 推 thinking
    await ws.send_json({
        "type": "agent_thinking",
        "content": f"正在为 Step {step} 提议字段...",
    })

    # 2. 调 OnboardingAgent
    agent = OnboardingAgent()
    try:
        result = await agent.consult(
            project_id=project_id,
            step=step,
            user_message=user_message_with_current,  # v0.8.3: 传带 current 的版本, 与 history 一致
            current_fields=current_fields,
        )
    except Exception as e:
        log.error("onboarding_request_proposal EXCEPTION: project_id=%s, step=%d, error=%s, elapsed=%.2fs",
                  project_id, step, str(e), time.monotonic() - t0, exc_info=True)
        await ws.send_json({
            "type": "error",
            "code": "AGENT_CONSULT_FAILED",
            "message": str(e),
        })
        return

    if "error" in result:
        log.error("onboarding_request_proposal LLM ERROR: project_id=%s, step=%d, error=%s, elapsed=%.2fs",
                  project_id, step, result["error"], time.monotonic() - t0)
        await ws.send_json({
            "type": "error",
            "code": "AGENT_CONSULT_ERROR",
            "message": result["error"],
        })
        return

    # 2.5 v0.8.3: 写 agent 消息 (content 存纯文本, thinking 存 JSON 结构供调试/UI 用)
    fields = result.get("fields", {})
    fields_text = _format_fields_as_text(fields, step)
    fields_json = json.dumps(fields, ensure_ascii=False)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=fields_text,
        thinking={"raw": result.get("raw", ""), "step": step, "fields_json": fields_json},
        project_id=project_id,
    )

    # 3. 推 onboarding_proposal 事件
    await ws.send_json({
        "type": "onboarding_proposal",
        "step": step,
        "fields": result["fields"],
    })

    log.info("onboarding_request_proposal END: project_id=%s, step=%d, fields_keys=%s, raw_len=%d, elapsed=%.2fs",
             project_id, step, list(fields.keys()) if isinstance(fields, dict) else "N/A",
             len(result.get("raw", "") or ""), time.monotonic() - t0)


async def handle_onboarding_confirm(ws: WebSocket, user_id: str, data: dict):
    """处理 onboarding_confirm: 用户确认 4 字段, 写 7 件

    v0.8.2: 同步写 user + tool + agent 消息到 messages 表

    Args:
        data: {
            type: "onboarding_confirm",
            project_id: str,
            step: 3 | 4,
            fields: dict,  # 用户最终确认的 4 字段
        }
    """
    import json
    from backend.utils.logger import get_logger

    log = get_logger(__name__)

    project_id = data.get("project_id")
    step = data.get("step")
    fields = data.get("fields", {})

    if not project_id or step not in (3, 4) or not fields:
        await ws.send_json({
            "type": "error",
            "code": "INVALID_ONBOARDING_CONFIRM",
            "message": f"Missing project_id/step/fields",
        })
        return

    # 0. v0.8.2: 拿/建 conversation, 写 user 消息
    conv_repo = ConversationRepository()
    conversation = await conv_repo.get_or_create_active_conversation(user_id)
    fields_json = json.dumps(fields, ensure_ascii=False)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=f"确认 Step {step} 字段: {fields_json}",
        project_id=project_id,
    )

    # 1. 推 thinking
    await ws.send_json({
        "type": "agent_thinking",
        "content": f"正在写入 Step {step} 4 字段到 7 件...",
    })

    # 2. 调工具写 7 件
    try:
        artifacts_written = await _write_onboarding_to_artifacts(
            project_id=project_id,
            step=step,
            fields=fields,
        )
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "code": "WRITE_ARTIFACTS_FAILED",
            "message": str(e),
        })
        return

    # 2.5 v0.8.2: 写 tool 消息 (artifact 写入记录为 tool)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.TOOL,
        tool_results={
            "name": "write_onboarding_to_artifacts",
            "args": {"project_id": project_id, "step": step, "fields": fields},
            "result": {"artifacts_written": artifacts_written},
        },
        project_id=project_id,
    )

    # 3. 推 onboarding_confirmed + onboarding_step_done
    await ws.send_json({
        "type": "onboarding_confirmed",
        "step": step,
        "fields": fields,
        "artifacts_written": artifacts_written,
    })
    await ws.send_json({
        "type": "onboarding_step_done",
        "step": step,
        "next_step": step + 1,  # 3 -> 4, 4 -> 5
    })

    # 3.5 v0.8.2: 写 agent 消息 (确认结果)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=f"已写入 Step {step} 字段到 7 件 ({len(artifacts_written)} 件)",
        project_id=project_id,
    )

    # v0.8.3: Step 4 完成 → LLM 自动生成项目名
    if step == 4:
        try:
            from backend.services.onboarding_artifacts import load_payload
            from backend.persistence.project_repository import ProjectRepository
            from backend.agent.onboarding_agent import _generate_project_name
            from backend.services.async_onboarding_flow import AsyncOnboardingFlow

            payload = load_payload(project_id)
            new_name = await _generate_project_name(
                story_core=payload.get("story_core", ""),
                characters=payload.get("characters", ""),
                tone=payload.get("tone", []),
            )
            if new_name:
                # 1. 改 projects.name
                ProjectRepository().update_name(project_id, new_name)
                # 2. 存到 state_json.project_name（委托给 service 层）
                AsyncOnboardingFlow().update_project_name_in_state(project_id, new_name)
                log.info("auto-generated project name: project_id=%s, name=%s", project_id, new_name)
        except Exception as e:
            log.warning("auto-generate project name failed: %s", str(e))


async def _write_onboarding_to_artifacts(
    project_id: str,
    step: int,
    fields: dict,
) -> list[str]:
    """v0.7 s2 重构: 调 onboarding_artifacts.assemble_7_artifacts 完整拼 7 件

    旧实现 (v0.5-v0.7) 在 ws_manager.py 里直接写 200+ 行 SQL 操作 7 件,
    跟 assemble_7_artifacts (services/onboarding_artifacts.py) 重复。
    v0.7 s2 重构: 收口到 assemble_7_artifacts, 这里只负责 merge_payload + 调拼装。

    Args:
        project_id: 项目 ID
        step: 3 | 4
        fields: 用户确认的字段 (Step 3: story_core/characters/opening_scene;
                               Step 4: main_arc/sub_plots/seeds/reader_feeling)

    Returns:
        写入的 7 件列表, e.g. ["world_tree", "style_charter", ..., "seed_table"]
    """
    from backend.services.onboarding_artifacts import (
        assemble_7_artifacts, merge_payload_to_state, load_payload,
    )

    if step not in (3, 4):
        return []

    # 1. 合并 fields 到 state_json.payload (Step 3/4 字段都进 payload)
    try:
        merge_payload_to_state(project_id, step, fields)
    except ValueError as e:
        # state 不存在 (用户跳过 Step 1-2 直接进 Step 3?) - 兼容: 静默继续
        import logging
        logging.warning(f"merge_payload_to_state failed: {e}")

    # 2. 调 assemble_7_artifacts 完整拼 7 件
    payload_full = load_payload(project_id)
    artifacts_written = assemble_7_artifacts(project_id, payload_full)
    return artifacts_written
