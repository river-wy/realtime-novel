"""OnboardingFlow — Onboarding 状态机

职责：5 步启动链路的状态管理（state 走 DB onboarding_state 表）。

Step 1-4 的 assemble_7_artifacts / emit 统一由管家 ReAct loop 通过
onboarding_user_confirm 工具触发，本文件只负责状态持久化。
Step 5 章节生成走 OnboardingGenerateChapterTool（onboarding_tools.py），
本文件保留 step("5") 路径作为 HTTP 路由兜底（action_routes 触发）。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.persistence import ProjectRepository, OnboardingRepository


def _step_to_num(step: str) -> int:
    """step 字符串 → 数字（1-5）"""
    return {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}.get(step, 0)


class OnboardingFlow:
    """onboarding 状态机 — state 走 DB（onboarding_state 表）"""

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def load_state(self, project_id: str) -> Optional[dict]:
        """加载项目当前 onboarding_state（含 payload）

        Returns:
            state_data dict（含 current_step, payload, updated_at），不存在返 None
        """
        repo = OnboardingRepository()
        return repo.get_state_json(project_id)

    async def step(self, project_id: str, step: str, payload: dict) -> dict:
        """执行 onboarding 单步，更新 onboarding_state 表

        副作用：
        - Step 2：把 palette 写入 projects.palette（UI 主题色）
        - Step 5：委托文笔家生成第 1 章（HTTP 路由兜底路径，管家 Agent 走 OnboardingGenerateChapterTool）
        """
        next_step_map = {"1": "2", "2": "3", "3": "4", "4": "5", "5": None}
        repo = OnboardingRepository()

        # 读现有 state，合并 payload（不覆盖前序 step 字段）
        state_data = repo.get_state_json(project_id) or {}
        state_data["current_step"] = step
        existing_payload = state_data.get("payload", {}) or {}
        state_data["payload"] = {**existing_payload, **payload}
        state_data["updated_at"] = datetime.now().isoformat()

        repo.upsert_step(project_id, _step_to_num(step), state_data)

        # Step 2：palette 写入 projects 表
        if step == "2":
            palette = payload.get("palette", "") or ""
            if palette:
                ProjectRepository().update_palette(project_id, palette)

        # Step 5：HTTP 路由兜底，生成第 1 章
        if step == "5":
            try:
                from backend.agent.agents.novel_writer import delegate_chapter_generation
                chapter_output = await delegate_chapter_generation(
                    project_id=project_id,
                    intervention=None,
                    source="onboarding_step5",
                )
                if chapter_output.error:
                    raise RuntimeError(f"第1章生成失败: {chapter_output.error}")
                chapter_result = {
                    "num": chapter_output.chapter_num,
                    "title": chapter_output.title,
                    "content": chapter_output.chapter_content,
                    "word_count": chapter_output.word_count,
                    "summary": chapter_output.chapter_summary,
                }
                return {
                    "step": step,
                    "next_step": None,
                    "payload": payload,
                    "chapter": chapter_result,
                }
            except Exception as e:
                import traceback
                print(f"Onboarding Step 5 失败: {e}\n{traceback.format_exc()}")
                raise RuntimeError(f"第1章生成失败: {str(e)}")

        return {
            "step": step,
            "next_step": next_step_map.get(step),
            "payload": payload,
        }

    def update_project_name_in_state(self, project_id: str, new_name: str) -> None:
        """将自动生成的项目名写入 onboarding_state.state_json.project_name

        由 onboarding_hooks（Step 4 完成）调用。
        """
        OnboardingRepository().update_project_name(project_id, new_name)

