"""context.onboarding_builders — Onboarding 阶段 messages 拼装

v0.6.1 P4: 从 context_builder.py 拆出

- build_messages_for_onboarding_step3: Step 3 故事核心设定
- build_messages_for_onboarding_step4: Step 4 主线大纲
- _load_project_history: 按 project_id 取历史 (per-project 维度)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.agent.context._helpers import (
    _load_project_history,
)


# ============ Onboard 阶段 messages 拼装 ============

def build_messages_for_onboarding_step3(
    project_id: str,
    current_user_message: str,
    system_prompt: str,
    current_fields: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """ 故事引擎 Agent (Step 3) 的 messages

    与 reading 阶段不同: 不需要 7 件全件 (Step 3 还没完成),
    只拼: world_tree + genre_resonance (Step 1 已有)
         + Step 1-2 已有数据 (genres/styles/tone/palette)

    结构:
    1. system: ONBOARDING_STEP3_PROMPT (v0.7 prompt 模板)
    2. data:   Step 1-2 已有 payload
    3. history: 用户与管家之前的对话
    4. current: user message
    """

    current_fields = current_fields or {}
    messages = []
    # 1. system
    messages.append({"role": "system", "content": system_prompt})

    # 2. data: 读 onboarding_state.state_json.payload (Step 1-2 已有数据)
    # v0.8.2 重要修正: Step 3 时 7 件还未写入 (Step 4 才调 assemble_7_artifacts),
    # 不能读 7 件. 只能读 state_json.payload + current_fields.
    try:
        payload = OnboardingRepository().get_payload(project_id)
        data_block = f"""## Step 1-2 已有数据
- 题材: {payload.get("genres", [])}
- 风格: {payload.get("styles", [])}
- 基调: {payload.get("tone", [])}
"""
        messages.append({"role": "system", "content": data_block})
    except Exception:
        pass  # 推断失败不阻断 onboarding

    # 3. history (Step 3/4 多轮对话, 拿最近 10 轮 = 5 轮 user + 5 轮 assistant)
    history = _load_project_history(project_id, max_history=10)
    messages.extend(history)

    # 4. current
    messages.append({"role": "user", "content": current_user_message or "请提议 3 个故事引擎字段"})
    return messages


def build_messages_for_onboarding_step4(
    project_id: str,
    current_user_message: str,
    system_prompt: str,
    current_fields: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """故事路径 Agent (Step 4) 的 messages

    与 Step 3 不同: 此时 Step 3 已确认, 需要拼:
    - Step 1-2 已有数据
    - Step 3 已写入的基座 (main_plot / character_card 等) — 从 DB 读
    - Step 4 当前 user 输入
    - Step 3/4 多轮对话 history
    """
    from backend.persistence.project_repository import ProjectRepository

    current_fields = current_fields or {}
    messages = []
    # 1. system
    messages.append({"role": "system", "content": system_prompt})

    # 2. data: Step 1-2 + Step 3 已写入的 7 件 (读 DB)
    # Step 4 走完 Step 3 后, 7 件已入库, 从 DB load_all_artifacts 读
    try:
        # 2a. Step 1-2 payload
        payload = OnboardingRepository().get_payload(project_id)

        # 2b. 7 件 (从 DB 读, Step 3 确认后已写入)
        artifacts = {}
        try:
            repo = ProjectRepository()
            artifacts = repo.load_all_artifacts(project_id)
        except Exception:
            pass  # 7 件未写入不阻断

        data_block = f"""## Step 1-2 已有数据
- 题材: {payload.get("genres", [])}
- 风格: {payload.get("styles", [])}
- 基调: {payload.get("tone", [])}

## Step 3 已写入的 7 件 (Step 3 确认后落库)
- story_core: {artifacts.get("world_tree", {}).get("core_premise", "") or artifacts.get("world_tree", {}).get("story_core", "") or "（未填）"}
- main_plot 主线: {artifacts.get("main_plot", {}).get("arc_phrase", "") or "（未填）"}
- 人物 ({len(artifacts.get("character_card", {}).get("characters", []))} 个): {[c.get("name", "") for c in artifacts.get("character_card", {}).get("characters", [])][:5]}
"""
        messages.append({"role": "system", "content": data_block})
    except Exception:
        pass  # 推断失败不阻断 onboarding

    # 3. history (Step 3/4 多轮, 拿最近 10 轮)
    history = _load_project_history(project_id, max_history=10)
    messages.extend(history)

    # 4. current
    messages.append({"role": "user", "content": current_user_message or "请提议 4 个故事路径字段"})
    return messages
