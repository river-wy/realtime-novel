"""AsyncOnboardingFlow — 异步 Onboarding 状态机

职责：5 步启动链路的状态管理（state 走 DB onboarding_state 表）
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.persistence import get_store


def _step_to_num(step: str) -> int:
    """step 名 → 数字 (1-5 顺序递增)"""
    mapping = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5}
    return mapping.get(step, 0)


class AsyncOnboardingFlow:
    """v0.4.1 onboarding 状态机 — state 走 DB（onboarding_state 表）"""

    def __init__(self, workspace_root: Path | str = "data"):
        self.workspace_root = Path(workspace_root)

    async def step(self, project_id: str, step: str, payload: dict) -> dict:
        """执行 onboarding 单步（onboarding_state 表）"""
        import json
        next_step_map = {
            "1": "2", "2": "3", "3": "4", "4": "5", "5": None,
        }
        now = datetime.now()
        with get_store().connection() as conn:
            # upsert state
            existing = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            state_data = json.loads(existing["state_json"]) if existing else {}
            state_data["current_step"] = step
            # 合并 payload（不覆盖前 step 的字段）
            # 例: step 1 存 {genres, styles, tone}, step 2 存 {palette}
            # 合并后: {genres, styles, tone, palette}
            existing_payload = state_data.get("payload", {}) or {}
            state_data["payload"] = {**existing_payload, **payload}
            state_data["updated_at"] = now.isoformat()
            if existing:
                conn.execute(
                    "UPDATE onboarding_state SET current_step = ?, state_json = ?, updated_at = ? "
                    "WHERE project_id = ?",
                    (_step_to_num(step), json.dumps(state_data, ensure_ascii=False), now, project_id),
                )
            else:
                conn.execute(
                    "INSERT INTO onboarding_state (project_id, current_step, started_at, updated_at, state_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (project_id, _step_to_num(step), now, now, json.dumps(state_data, ensure_ascii=False)),
                )

        # Step 2 palette 只存 projects.palette (UI 主题色), **不**写 7 件
        if step == "2":
            palette = payload.get("palette", "") or ""
            if palette:
                with get_store().connection() as conn:
                    conn.execute(
                        "UPDATE projects SET palette = ? WHERE id = ?",
                        (palette, project_id),
                    )

        # v0.7: Step 4 HTTP 兜底, 调 onboarding_artifacts.assemble_7_artifacts
        if step == "4":
            try:
                from backend.services.onboarding_artifacts import (
                    assemble_7_artifacts, load_payload,
                )
                payload_full = load_payload(project_id)
                assemble_7_artifacts(project_id, payload_full)
            except Exception as e:
                import traceback
                print(f"Onboarding Step 4 失败: {e}\n{traceback.format_exc()}")
                # 前端 catch 收到 e.message (含错误详情) 能正确显示
                raise RuntimeError(f"7件生成失败: {str(e)}")

        # Step 5 触发生成第 1 章
        if step == "5":
            try:
                from backend.agent.state_graph_stub import generate_chapter_via_state_graph
                # 调 LLM 生成第 1 章（state_graph_stub 会从 DB 读 7 件）
                chapter_result = await generate_chapter_via_state_graph(
                    project_id=project_id,
                    intervention=None,  # 第一章无需干预
                )
                return {
                    "step": step,
                    "next_step": None,
                    "payload": payload,
                    "chapter": chapter_result,
                }
            except Exception as e:
                import traceback
                print(f"Onboarding Step 5 失败: {e}\n{traceback.format_exc()}")
                # v0.6: 不再吞异常, 让 action_routes 统一返 HTTPException(500)
                raise RuntimeError(f"第1章生成失败: {str(e)}")
        return {
            "step": step,
            "next_step": next_step_map.get(step),
            "payload": payload,
        }

    def update_project_name_in_state(self, project_id: str, new_name: str) -> None:
        """将自动生成的项目名写入 onboarding_state.state_json.project_name

        由 ws_manager handle_onboarding_confirm (Step 4 完成) 调用。
        只负责 state_json 里的 project_name 字段；projects.name 由 ProjectRepository.update_name 处理。
        """
        import json
        from datetime import datetime as _dt
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if row:
                sd = json.loads(row["state_json"])
                sd["project_name"] = new_name
                sd["updated_at"] = _dt.now().isoformat()
                conn.execute(
                    "UPDATE onboarding_state SET state_json = ?, updated_at = ? WHERE project_id = ?",
                    (json.dumps(sd, ensure_ascii=False), _dt.now(), project_id),
                )

