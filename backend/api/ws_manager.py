"""WebSocketManager + WS /api/chat 端点（v0.6 s3.6 重写）

对应 spec.md §4 + core.md §B.4

v0.6 改造：
- 所有用户消息统一进 /api/chat（v0.5 时 Onboarding / 章节 / 干预走不同入口）
- 改用 NovelSteward 处理（不再是 SimpleStateGraph）
- Intent 路由（项目级 / 用户级）由管家决定
- 流式推送 ReAct loop 过程：agent_thinking → tool_calling → tool_result → agent_message

事件类型（spec.md §4.4 拍板）：
- agent_thinking: LLM 思考中
- tool_calling: Agent 准备调 tool
- tool_result: tool 执行结果
- agent_message: 管家最终回复（含 structured_data 用于前端渲染）
- error: 失败
- interrupted: 用户主动中断
- confirm_required: 危险操作需二次确认
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)


# ============ WebSocketManager ============

class WebSocketManager:
    """per-user WS 连接 + 活动任务管理"""

    def __init__(self):
        self.connections: dict[str, WebSocket] = {}
        self.active_tasks: dict[str, asyncio.Task] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.connections[user_id] = ws
        log.info(f"ws_manager: user_id={user_id} connected")

    async def disconnect(self, user_id: str):
        self.connections.pop(user_id, None)
        # 用 pop + 顺序重排，避免 race condition
        task = self.active_tasks.pop(user_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        log.info(f"ws_manager: user_id={user_id} disconnected")

    async def send_event(self, user_id: str, event: dict):
        """通用事件推送"""
        if user_id in self.connections:
            try:
                await self.connections[user_id].send_json(event)
            except Exception as e:
                log.warning(f"ws_manager: send_event failed: {e}")

    async def interrupt(self, user_id: str):
        if user_id in self.active_tasks:
            self.active_tasks[user_id].cancel()
            log.info(f"ws_manager: interrupted user_id={user_id}")

    def has_active_task(self, user_id: str) -> bool:
        return user_id in self.active_tasks


# 全局单例
ws_manager = WebSocketManager()


# ============ WS 端点 ============

router = APIRouter()


@router.websocket("/api/chat")
async def chat_endpoint(websocket: WebSocket):
    """WS /api/chat 主对话端点（v0.6：所有用户消息统一进）

    流程：
    1. 连接 → ws_manager.connect
    2. 接收消息（user_message / interrupt / confirm）
    3. user_message → 调 NovelSteward → 流式推 ReAct 过程
    4. interrupt → 取消当前任务
    5. 异常断开 → 清理
    """
    user_id = "anonymous"  # v0.4 单机单用户（后续扩展多用户）
    await ws_manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "user_message":
                # 检查是否已有任务在跑
                if ws_manager.has_active_task(user_id):
                    await websocket.send_json({
                        "type": "error",
                        "code": "TASK_BUSY",
                        "message": "已有任务在跑，请先中断或等待完成",
                    })
                    continue

                # 启动新任务处理消息
                task = asyncio.create_task(
                    handle_user_message(websocket, user_id, data)
                )
                ws_manager.active_tasks[user_id] = task

                # 任务结束自动清理
                def _cleanup(t, uid=user_id):
                    if uid in ws_manager.active_tasks and ws_manager.active_tasks[uid] is t:
                        del ws_manager.active_tasks[uid]
                task.add_done_callback(_cleanup)

            elif msg_type == "interrupt":
                await ws_manager.interrupt(user_id)
                try:
                    await websocket.send_json({
                        "type": "interrupted",
                        "message": "当前生成已取消",
                    })
                except Exception:
                    pass

            elif msg_type == "confirm":
                # 二次确认（v0.6 s3 阶段先 echo）
                await websocket.send_json({
                    "type": "agent_message",
                    "content": f"收到 confirm 消息：{data.get('action', '?')}",
                    "structured_data": {},
                })

            elif msg_type == "ping":
                # 心跳
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({
                    "type": "error",
                    "code": "INVALID_MESSAGE_TYPE",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id)
    except Exception as e:
        log.error(f"ws_manager: 异常断开: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "code": "WEBSOCKET_ERROR",
                "message": str(e),
            })
        except Exception:
            pass
        await ws_manager.disconnect(user_id)


# ============ 消息处理 ============

async def handle_user_message(ws: WebSocket, user_id: str, data: dict):
    """处理单条 user_message：调 NovelSteward + 流式推送

    v0.6 s3.6：
    1. 落 messages 表（user 消息）
    2. 推 agent_thinking
    3. 调 NovelSteward.receive()
    4. 推最终回复（agent_message）+ structured_data

    项目级 intent（GENERATE/INTERVENE）会触发下游 Agent ReAct loop
    - 推 tool_calling + tool_result（每个 tool 调用前后）
    - 推 agent_thinking（每轮 LLM 调用前）
    """
    from backend.agent.agents.novel_steward import get_novel_steward
    from backend.persistence import ConversationRepository, MessageRole

    conv_repo = ConversationRepository()
    steward = get_novel_steward()

    try:
        # 1. 创建对话 + 落 user message
        project_id = data.get("project_id")

        conversation = await conv_repo.create_conversation(user_id=user_id)
        user_msg = await conv_repo.add_message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=data["content"],
            project_id=project_id,
        )

        # 2. 推 agent_thinking
        await ws.send_json({
            "type": "agent_thinking",
            "content": "正在分析你的消息...",
        })

        # 3. 调 NovelSteward（核心路由）
        result = await steward.receive(
            user_message=data["content"],
            project_id=project_id,
            user_id=user_id,
            in_onboarding=data.get("in_onboarding", False),
            conversation_id=conversation.id,
        )

        # 4. 推流式事件（如果有 downstream 调用 + tool_calls trace）
        await _push_agent_trace(ws, result)

        # 5. 推 confirm_required（如果是危险操作）
        if result.get("structured_data", {}).get("require_confirm"):
            await ws.send_json({
                "type": "confirm_required",
                "action": result.get("intent", ""),
                "details": result.get("structured_data", {}),
            })

        # 6. 推 agent_message（最终回复）
        await ws.send_json({
            "type": "agent_message",
            "content": result.get("response", ""),
            "intent": result.get("intent", ""),
            "structured_data": result.get("structured_data", {}),
        })

        # 7. 落 assistant message
        # v0.6 简化：intent / downstream 信息放到 tool_calls 字段里（schema 允许 dict）
        await conv_repo.add_message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=result.get("response", ""),
            project_id=project_id,
            tool_calls={
                "intent": result.get("intent", ""),
                "downstream_called": result.get("downstream_called", ""),
                "confidence": result.get("confidence", 0.0),
            } if result.get("intent") else None,
        )

    except asyncio.CancelledError:
        log.info(f"ws_manager: handle_user_message cancelled user_id={user_id}")
        try:
            await ws.send_json({
                "type": "interrupted",
                "message": "已中断",
            })
        except Exception:
            pass
    except Exception as e:
        log.error(f"ws_manager: handle_user_message failed: {e}", exc_info=True)
        try:
            await ws.send_json({
                "type": "error",
                "code": "HANDLER_ERROR",
                "message": str(e),
            })
        except Exception:
            pass


async def _push_agent_trace(ws: WebSocket, result: dict):
    """把管家调用的下游 Agent 的 tool_calls trace 推送给前端

    适用场景：
    - WorldTreeManager ReAct loop 调了 search_memory + edit_artifact
    - NovelWriter ReAct loop 调了 load_project + read_chapter

    structured_data 里如果有 tool_calls_trace 字段，则逐条推送
    """
    structured = result.get("structured_data", {})
    trace = structured.get("tool_calls_trace", [])

    if not trace:
        # 看 downstream_called 是否有（说明调了下游但没 trace）
        # 比如 NovelWriter.generate_chapter 返回 iterations + tool_calls_count
        iterations = structured.get("iterations", 0)
        tool_calls_count = structured.get("tool_calls_count", 0)
        if iterations > 0:
            await ws.send_json({
                "type": "agent_thinking",
                "content": f"已调下游 Agent（{iterations} 轮推演）",
            })
        return

    for tc in trace:
        # tool_calling
        await ws.send_json({
            "type": "tool_calling",
            "tool": tc.get("tool_name", "?"),
            "args": tc.get("arguments", {}),
            "iteration": tc.get("iteration", 0),
        })
        # tool_result
        await ws.send_json({
            "type": "tool_result",
            "tool": tc.get("tool_name", "?"),
            "result": tc.get("result", {}),
            "status": tc.get("status", "unknown"),
            "iteration": tc.get("iteration", 0),
        })