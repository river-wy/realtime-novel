"""WebSocketManager + WS /api/chat 端点

对应 core.md §B.4

职责：
- WebSocketManager：连接管理（connect / disconnect / send_event / interrupt）
- /api/chat WS 端点：消息分发（user_message / interrupt / onboarding_* → 转发给各 handler）
- handle_user_message：通用对话处理

Onboarding WS handler 已迁移到 onboarding_routes.py
Event Schema 定义已迁移到 api/schemas/events.py
"""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict

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
    from backend.api.onboarding_routes import (
        handle_onboarding_request_proposal,
        handle_onboarding_confirm,
    )

    user_id = "anonymous"  # v0.4 单机单用户
    await ws_manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                task = asyncio.create_task(
                    handle_user_message(websocket, user_id, data)
                )
                ws_manager.active_tasks[user_id] = task

            elif msg_type == "interrupt":
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

            # ============ Onboarding WS 路由 ============
            elif msg_type == "onboarding_request_proposal":
                task = asyncio.create_task(
                    handle_onboarding_request_proposal(websocket, user_id, data)
                )
                ws_manager.active_tasks[user_id] = task

            elif msg_type == "onboarding_confirm":
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
    """处理单条 user_message：触发状态机 + 流式推送"""
    conv_repo = ConversationRepository()
    try:
        conversation = await conv_repo.create_conversation(
            user_id=user_id,
        )
        user_msg = await conv_repo.add_message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=data["content"],
            project_id=data.get("project_id"),
        )
        await ws.send_json({
            "type": "agent_thinking",
            "content": "正在分析意图...",
        })
        state = AgentState(
            user_message=data["content"],
            project_id=data.get("project_id"),
            conversation_id=conversation.id,
            message_id=user_msg.id,
        )
        graph = build_graph()

        async def on_progress(event: dict):
            try:
                await ws.send_json({
                    "type": "tool_progress",
                    "step": event.get("step", ""),
                    "percentage": event.get("percentage", 0),
                })
            except Exception:
                pass

        final_state = await graph.ainvoke(state, progress_callback=on_progress)

        for tc in final_state.tool_calls:
            if tc.tool_name:
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

        await ws.send_json({
            "type": "agent_message",
            "content": final_state.final_response or "完成",
        })

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
