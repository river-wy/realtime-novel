"""WebSocketManager + WS /api/chat 端点 + 4 类事件

对应 core.md §B.4
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from realtime_novel.agent.state_graph import build_graph
from realtime_novel.agent.state import AgentState
from realtime_novel.persistence import (
    ConversationRepository, MessageRole,
)


# ============ 4+3 类事件 Pydantic Schema ============

class AgentThinkingEvent(BaseModel):
    type: str = "agent_thinking"
    content: str


class ToolCallingEvent(BaseModel):
    type: str = "tool_calling"
    tool: str
    args: dict


class ToolResultEvent(BaseModel):
    type: str = "tool_result"
    tool: str
    result: dict


class AgentMessageEvent(BaseModel):
    type: str = "agent_message"
    content: str


class ErrorEvent(BaseModel):
    type: str = "error"
    code: str
    message: str


class InterruptedEvent(BaseModel):
    type: str = "interrupted"
    message: str


class ConfirmRequiredEvent(BaseModel):
    type: str = "confirm_required"
    action: str
    details: dict


# ============ m-v0.5-onboarding s1.2: Onboarding 事件 ============

class OnboardingProposalEvent(BaseModel):
    """Agent 提议 Step 3/4 4 字段"""
    type: str = "onboarding_proposal"
    step: int  # 3 or 4
    fields: dict  # 4 字段 dict


class OnboardingConfirmedEvent(BaseModel):
    """用户确认后, Agent 写 7 件完成"""
    type: str = "onboarding_confirmed"
    step: int  # 3 or 4
    fields: dict
    artifacts_written: list  # 写入了哪些 7 件表 (e.g. ['style_charter', 'main_plot'])


class OnboardingStepDoneEvent(BaseModel):
    """Step 3/4 完成, 跳下一步"""
    type: str = "onboarding_step_done"
    step: int  # 3 or 4
    next_step: Optional[int]  # 4 or 5 or None


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
        # 1. 创建/获取 conversation
        conversation = await conv_repo.create_conversation(
            user_id=user_id,
            project_id=data.get("project_id"),
        )
        # 2. 写 user message
        user_msg = await conv_repo.add_message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=data["content"],
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

        # 5. 推 tool_calling + tool_result
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

        # 6. 推最终回复
        await ws.send_json({
            "type": "agent_message",
            "content": final_state.final_response or "完成",
        })

        # 7. 写 assistant message
        await conv_repo.add_message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=final_state.final_response or "",
            tool_calls={"calls": [tc.model_dump() for tc in final_state.tool_calls]},
            thinking={"plan": final_state.plan or ""},
        )

    except asyncio.CancelledError:
        await ws.send_json({"type": "interrupted", "message": "生成被取消"})
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "code": "GENERATION_FAILED",
            "message": str(e),
        })


# ============ m-v0.5-onboarding s1.2: Onboarding 处理器 ============

async def handle_onboarding_request_proposal(ws: WebSocket, user_id: str, data: dict):
    """处理 onboarding_request_proposal: 调 OnboardingAgent 生成 4 字段

    Args:
        data: {
            type: "onboarding_request_proposal",
            project_id: str,
            step: 3 | 4,
            user_message?: str,  # 用户修改场景 (e.g. "改一下情感锚点")
            current_fields?: dict,  # 当前已有字段
        }
    """
    from realtime_novel.agent.onboarding_agent import OnboardingAgent

    project_id = data.get("project_id")
    step = data.get("step")
    if not project_id or step not in (3, 4):
        await ws.send_json({
            "type": "error",
            "code": "INVALID_ONBOARDING_REQUEST",
            "message": f"Missing project_id or invalid step={step}",
        })
        return

    # 1. 推 thinking
    await ws.send_json({
        "type": "agent_thinking",
        "content": f"正在为 Step {step} 提议字段...",
    })

    # 2. 调 OnboardingAgent
    agent = OnboardingAgent()
    user_message = data.get("user_message", "")
    current_fields = data.get("current_fields", {})
    try:
        result = await agent.consult(
            project_id=project_id,
            step=step,
            user_message=user_message,
            current_fields=current_fields,
        )
    except Exception as e:
        await ws.send_json({
            "type": "error",
            "code": "AGENT_CONSULT_FAILED",
            "message": str(e),
        })
        return

    if "error" in result:
        await ws.send_json({
            "type": "error",
            "code": "AGENT_CONSULT_ERROR",
            "message": result["error"],
        })
        return

    # 3. 推 onboarding_proposal 事件
    await ws.send_json({
        "type": "onboarding_proposal",
        "step": step,
        "fields": result["fields"],
    })


async def handle_onboarding_confirm(ws: WebSocket, user_id: str, data: dict):
    """处理 onboarding_confirm: 用户确认 4 字段, 写 7 件

    Args:
        data: {
            type: "onboarding_confirm",
            project_id: str,
            step: 3 | 4,
            fields: dict,  # 用户最终确认的 4 字段
        }
    """
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

    # 1. 推 thinking
    await ws.send_json({
        "type": "agent_thinking",
        "content": f"正在写入 Step {step} 4 字段到 7 件...",
    })

    # 2. 调工具写 7 件
    # 根据 step 调不同的 edit_artifact 调用
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


async def _write_onboarding_to_artifacts(project_id: str, step: int, fields: dict) -> list:
    """把 4 字段写入 7 件基座

    Step 3 4 字段 -> 7 件:
    - core_relationship (Step 3) -> character_card.characters[].background
    - emotional_anchor (Step 3) -> style_charter.notes 追加
    - taboos (Step 3) -> style_charter.taboos 追加
    - ending_preference (Step 3) -> main_plot.metadata.ending_preference
    - main_conflict (Step 4) -> main_plot.arc_phrase + beats
    - sub_plots (Step 4) -> sub_plot.threads
    - characters (Step 4) -> character_card.characters
    - seeds (Step 4) -> seed_table.seeds

    Returns:
        artifacts_written: 写入了哪些 7 件表
    """
    from realtime_novel.persistence import get_store
    import json

    artifacts_written = []

    with get_store().connection() as conn:
        # 读当前 7 件
        sc_row = conn.execute(
            "SELECT prose_style_json, tone_json, density_json, taboos_json, notes_json, limits_json, metadata_json FROM style_charter WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        mp_row = conn.execute(
            "SELECT current_beat, arc_phrase, beats_json, metadata_json FROM main_plot WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        sp_row = conn.execute(
            "SELECT id, title, description, parent_beat_id, status, priority, linked_seeds_json, linked_chars_json, beats_json, metadata_json FROM sub_plot WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        cc_row = conn.execute(
            "SELECT id, name, role, traits_json, speech_style, background, arc, internal_state, metadata_json FROM characters WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        sd_row = conn.execute(
            "SELECT id, content, importance_primary, size, planned_interval, orientation, planted_at_chapter, planted_in_node, planted_context, last_seen_chapter, weight, status, linked_char_ids_json, linked_subplot_id, updated_at FROM seeds WHERE project_id = ?",
            (project_id,),
        ).fetchall()

        # Step 3 写入 style_charter + main_plot
        if step == 3:
            taboos = json.loads(sc_row['taboos_json']) if sc_row and sc_row['taboos_json'] else []
            notes = json.loads(sc_row['notes_json']) if sc_row and sc_row['notes_json'] else []
            metadata = json.loads(sc_row['metadata_json']) if sc_row and sc_row['metadata_json'] else {}

            # emotional_anchor -> notes 追加
            if fields.get('emotional_anchor'):
                notes.append(f"情感锚点: {fields['emotional_anchor']}")
            # taboos -> taboos 追加
            if fields.get('taboos'):
                taboos.append({
                    "id": f"T{len(taboos)+1}",
                    "text": fields['taboos'],
                    "source": "user_onboarding_step3"
                })
            # ending_preference -> main_plot.metadata
            if mp_row and fields.get('ending_preference'):
                mp_metadata = json.loads(mp_row['metadata_json']) if mp_row['metadata_json'] else {}
                mp_metadata['ending_preference'] = fields['ending_preference']
                mp_metadata['core_relationship'] = fields.get('core_relationship', '')

            # 写 style_charter
            if sc_row:
                conn.execute(
                    "UPDATE style_charter SET taboos_json = ?, notes_json = ?, metadata_json = ?, updated_at = ? WHERE project_id = ?",
                    (
                        json.dumps(taboos, ensure_ascii=False),
                        json.dumps(notes, ensure_ascii=False),
                        json.dumps(metadata, ensure_ascii=False),
                        datetime.now(),
                        project_id,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO style_charter (project_id, prose_style_json, tone_json, density_json, taboos_json, notes_json, limits_json, metadata_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        project_id, '{}', '{}', '{}',
                        json.dumps(taboos, ensure_ascii=False),
                        json.dumps(notes, ensure_ascii=False),
                        '{}', json.dumps(metadata, ensure_ascii=False),
                        datetime.now(),
                    ),
                )
            artifacts_written.append('style_charter')

            # 写 main_plot.metadata
            if mp_row and fields.get('ending_preference'):
                conn.execute(
                    "UPDATE main_plot SET metadata_json = ?, updated_at = ? WHERE project_id = ?",
                    (
                        json.dumps(mp_metadata, ensure_ascii=False),
                        datetime.now(),
                        project_id,
                    ),
                )
                artifacts_written.append('main_plot')

        # Step 4 写入 main_plot + sub_plot + character_card + seed_table
        elif step == 4:
            # main_conflict -> main_plot.arc_phrase + beats
            if mp_row and fields.get('main_conflict'):
                beats = json.loads(mp_row['beats_json']) if mp_row['beats_json'] else []
                # 加 1 个 beat
                beats.append({
                    "id": f"beat-{len(beats)+1}",
                    "sequence": len(beats) + 1,
                    "title": f"主线弧光",
                    "description": fields['main_conflict'][:80],
                    "status": "active",
                    "chapter_range": {"start": 1, "end": 5},
                })
                conn.execute(
                    "UPDATE main_plot SET arc_phrase = ?, beats_json = ?, updated_at = ? WHERE project_id = ?",
                    (
                        fields['main_conflict'],
                        json.dumps(beats, ensure_ascii=False),
                        datetime.now(),
                        project_id,
                    ),
                )
                artifacts_written.append('main_plot')

            # sub_plots -> sub_plot.threads (按行拆, 重建)
            if fields.get('sub_plots'):
                # 删旧
                conn.execute("DELETE FROM sub_plot WHERE project_id = ?", (project_id,))
                for i, line in enumerate(fields['sub_plots'].split('\n')):
                    line = line.strip()
                    if not line:
                        continue
                    sub_id = f"sub-{uuid.uuid4().hex[:8]}"
                    conn.execute(
                        "INSERT INTO sub_plot (id, project_id, title, description, parent_beat_id, status, priority, linked_seeds_json, linked_chars_json, beats_json, metadata_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            sub_id, project_id, line[:30], line, None, 'pending', 'side',
                            '[]', '[]', '[]', '{}', datetime.now(),
                        ),
                    )
                artifacts_written.append('sub_plot')

            # characters -> characters (按行拆 '名字-身份-背景')
            if fields.get('characters'):
                # 不删旧 (Step 3 可能已写), 增量
                for line in fields['characters'].split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split('-')
                    name = parts[0].strip() if parts else f"角色"
                    role = parts[1].strip() if len(parts) > 1 else "supporting"
                    background = parts[2].strip() if len(parts) > 2 else line
                    role_map = {
                        "主角": "protagonist", "妹妹": "supporting", "反派": "antagonist",
                        "次主角": "deuteragonist", "配角": "supporting", "路人": "minor",
                    }
                    mapped_role = role_map.get(role, "supporting")
                    char_id = f"char-{uuid.uuid4().hex[:8]}"
                    conn.execute(
                        "INSERT INTO characters (id, project_id, name, role, traits_json, speech_style, background, arc, internal_state, metadata_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            char_id, project_id, name, mapped_role, '[]', None, background, None, None, '{}', datetime.now(),
                        ),
                    )
                artifacts_written.append('character_card')

            # seeds -> seeds (按行拆)
            if fields.get('seeds'):
                for i, line in enumerate(fields['seeds'].split('\n')):
                    line = line.strip()
                    if not line:
                        continue
                    # 取 max id + 1
                    max_id_row = conn.execute(
                        "SELECT MAX(id) AS max_id FROM seeds WHERE project_id = ?", (project_id,)
                    ).fetchone()
                    next_id = (max_id_row['max_id'] or 0) + 1
                    conn.execute(
                        "INSERT INTO seeds (project_id, content, importance_primary, size, planned_interval, orientation, planted_at_chapter, planted_in_node, planted_context, last_seen_chapter, weight, status, linked_char_ids_json, linked_subplot_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            project_id, line, '小巧思', '中线', None, '氛围营造',
                            0, None, None, 0, 0.5, 'planted', '[]', None, datetime.now(),
                        ),
                    )
                artifacts_written.append('seed_table')

    return artifacts_written
