"""Onboarding 路由 + WS 处理器

聚合所有 Onboarding 场景的 API 逻辑：
- HTTP: POST /{project_id}/onboarding（5 步提交）
- WS handler: handle_onboarding_request_proposal（Agent 提议 Step3/4 字段）
- WS handler: handle_onboarding_confirm（用户确认 + 写 7 件）
- 内部工具: _write_onboarding_to_artifacts / format helpers
"""
from __future__ import annotations

import asyncio
import json
import time
from fastapi import APIRouter, HTTPException, WebSocket

from backend.api.schemas.onboarding import (
    OnboardingRequest,
    OnboardingResponse,
    validate_onboarding_payload,
)
from backend.persistence import ConversationRepository, MessageRole
from backend.services.onboarding_flow import OnboardingFlow
from backend.utils.logger import get_logger

router = APIRouter(prefix="/api/projects", tags=["onboarding"])
_onboarding = OnboardingFlow()

log = get_logger(__name__)


# ============ HTTP 端点 ============

@router.post("/{project_id}/onboarding", response_model=OnboardingResponse)
async def onboarding(project_id: str, req: OnboardingRequest):
    """5 步启动链路"""
    validated_payload = validate_onboarding_payload(req.step, req.payload)

    try:
        result = await _onboarding.step(project_id, req.step, validated_payload)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))

    conv_repo = ConversationRepository()
    conv = await conv_repo.get_or_create_active_conversation("default")
    await conv_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.TOOL,
        tool_results={
            "name": "onboarding_step",
            "args": {"step": req.step, "payload": req.payload},
            "result": result if isinstance(result, dict) else {"raw": str(result)},
        },
        project_id=project_id,
    )
    return OnboardingResponse(
        step=req.step,
        result=result if isinstance(result, dict) else {"raw": str(result)},
        next_step=result.get("next_step") if isinstance(result, dict) else None,
    )


# ============ WS 处理器 ============

def _format_user_message_with_current(user_input: str, current_fields: dict) -> str:
    """拼接 user message + current_fields 原值，让 LLM 知道改的是哪个字段

    示例: "主角改成女性\\n\\n[当前字段]\\n- story_core: 主角是男性...\\n- characters: 白云飞..."
    """
    if not current_fields:
        return user_input
    lines = [user_input, "", "[当前字段原值]"]
    for k, v in current_fields.items():
        if v:
            v_short = v[:200] + "..." if len(v) > 200 else v
            lines.append(f"- {k}: {v_short}")
    return "\n".join(lines)


def _format_fields_as_text(fields: dict, step: int) -> str:
    """把 fields dict 转成纯文本摘要，给 LLM 读 history 时用

    不存 JSON 字符串，存自然语言描述。
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
    """处理 onboarding_request_proposal: 调 OnboardingController 生成 4 字段

    v0.6.1: WS 路径统一走 OnboardingController (吸收原 OnboardingAgent 能力)

    Args:
        data: {
            type: "onboarding_request_proposal",
            project_id: str,
            step: 3 | 4,
            user_message?: str,  # 用户修改场景 (e.g. "改一下情感锚点")
            current_fields?: dict,  # 当前已有字段
        }
    """
    from backend.agent.onboarding_controller import get_onboarding_controller

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

    log.info(
        "onboarding_request_proposal START: project_id=%s, step=%d, user_msg_len=%d",
        project_id, step, len(user_input),
    )

    # 拿/建 conversation, 写 user 消息
    conv_repo = ConversationRepository()
    conversation = await conv_repo.get_or_create_active_conversation(user_id)
    current_fields = data.get("current_fields", {})
    if not user_input:
        user_input = f"请提议 Step {step} 字段"
    user_message_with_current = _format_user_message_with_current(user_input, current_fields)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=user_message_with_current,
        project_id=project_id,
    )

    # 推 thinking
    await ws.send_json({
        "type": "agent_thinking",
        "content": f"正在为 Step {step} 提议字段...",
    })

    # 调 OnboardingController (v0.6.1: 统一入口, 吸收原 OnboardingAgent 能力)
    controller = get_onboarding_controller()
    try:
        result = await controller.consult(
            project_id=project_id,
            step=step,
            user_message=user_message_with_current,
            current_fields=current_fields,
        )
    except Exception as e:
        log.error(
            "onboarding_request_proposal EXCEPTION: project_id=%s, step=%d, error=%s, elapsed=%.2fs",
            project_id, step, str(e), time.monotonic() - t0, exc_info=True,
        )
        await ws.send_json({
            "type": "error",
            "code": "AGENT_CONSULT_FAILED",
            "message": str(e),
        })
        return

    if result.error:
        log.error(
            "onboarding_request_proposal LLM ERROR: project_id=%s, step=%d, error=%s, elapsed=%.2fs",
            project_id, step, result.error, time.monotonic() - t0,
        )
        await ws.send_json({
            "type": "error",
            "code": "AGENT_CONSULT_ERROR",
            "message": result.error,
        })
        return

    # 写 agent 消息 (content 存纯文本, thinking 存 JSON 结构供调试/UI 用)
    fields = result.fields or {}
    fields_text = _format_fields_as_text(fields, step)
    fields_json = json.dumps(fields, ensure_ascii=False)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=fields_text,
        thinking={"raw": result.raw or "", "step": step, "fields_json": fields_json},
        project_id=project_id,
    )

    # 推 onboarding_proposal 事件
    await ws.send_json({
        "type": "onboarding_proposal",
        "step": step,
        "fields": result.fields,
    })

    log.info(
        "onboarding_request_proposal END: project_id=%s, step=%d, fields_keys=%s, raw_len=%d, elapsed=%.2fs",
        project_id, step,
        list(fields.keys()) if isinstance(fields, dict) else "N/A",
        len(result.raw or ""),
        time.monotonic() - t0,
    )


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
            "message": "Missing project_id/step/fields",
        })
        return

    # 拿/建 conversation, 写 user 消息
    conv_repo = ConversationRepository()
    conversation = await conv_repo.get_or_create_active_conversation(user_id)
    fields_json = json.dumps(fields, ensure_ascii=False)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=f"确认 Step {step} 字段: {fields_json}",
        project_id=project_id,
    )

    # 推 thinking
    await ws.send_json({
        "type": "agent_thinking",
        "content": f"正在写入 Step {step} 4 字段到 7 件...",
    })

    # 调工具写 7 件
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

    # 写 tool 消息 (artifact 写入记录为 tool)
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

    # 推 onboarding_confirmed + onboarding_step_done
    try:
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
    except Exception:
        pass  # WS 已断开，静默忽略

    # 写 agent 消息 (确认结果)
    await conv_repo.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=f"已写入 Step {step} 字段到 7 件 ({len(artifacts_written)} 件)",
        project_id=project_id,
    )

    # Step 4 完成 → 触发领域事件，后置逻辑在 onboarding_hooks.py 里处理
    # event_bus.emit 内部用 create_task，与 WS 生命周期完全解耦
    if step == 4:
        try:
            from backend.services.onboarding_artifacts import load_payload
            from backend.core.event_bus import event_bus

            payload = load_payload(project_id)
            await event_bus.emit(
                "onboarding.step4_confirmed",
                project_id=project_id,
                payload=payload,
                ws=ws,  # 传入 ws 供 handler 尝试推送，断开时推送失败会静默忽略
            )
        except Exception as e:
            log.warning("Step 4 post-confirm event emit failed: %s", str(e))


async def _write_onboarding_to_artifacts(
    project_id: str,
    step: int,
    fields: dict,
) -> list[str]:
    """调 onboarding_artifacts.assemble_7_artifacts 完整拼 7 件

    Args:
        project_id: 项目 ID
        step: 3 | 4
        fields: 用户确认的字段

    Returns:
        写入的 7 件列表, e.g. ["world_tree", "style_charter", ..., "seed_table"]
    """
    from backend.services.onboarding_artifacts import (
        assemble_7_artifacts, merge_payload_to_state, load_payload,
    )

    if step not in (3, 4):
        return []

    # 合并 fields 到 state_json.payload
    try:
        merge_payload_to_state(project_id, step, fields)
    except ValueError as e:
        import logging
        logging.warning(f"merge_payload_to_state failed: {e}")

    # 调 assemble_7_artifacts 完整拼 7 件
    payload_full = load_payload(project_id)
    artifacts_written = assemble_7_artifacts(project_id, payload_full)
    return artifacts_written

