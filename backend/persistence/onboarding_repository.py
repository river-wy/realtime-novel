"""OnboardingRepository — onboarding_state 表 CRUD

负责 onboarding_state 表的全部读写，杜绝 services 层直接写 SQL。

表结构 (v002_artifacts_to_db.sql):
    project_id       TEXT PRIMARY KEY
    current_step     INTEGER
    started_at       DATETIME
    updated_at       DATETIME
    state_json       TEXT    — JSON 大 blob, 含 payload + project_name + updated_at
    artifacts_generated BOOLEAN
    chapter_1_generated BOOLEAN
    chapter_1_path   TEXT
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from backend.persistence.models import OnboardingStateRow
from backend.persistence.sqlite_store import get_store


def _now() -> datetime:
    return datetime.now()


class OnboardingRepository:
    """onboarding_state 表 CRUD"""

    # ------------------------------------------------------------------ #
    # 读
    # ------------------------------------------------------------------ #

    def get(self, project_id: str) -> Optional[OnboardingStateRow]:
        """读单行，不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT * FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return OnboardingStateRow(**dict(row))

    def get_state_json(self, project_id: str) -> Optional[Dict[str, Any]]:
        """读 state_json blob，不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["state_json"])

    def get_payload(self, project_id: str) -> Dict[str, Any]:
        """读 state_json.payload（Step 1-4 合并后的全部字段），不存在返回空 dict"""
        state_data = self.get_state_json(project_id)
        if state_data is None:
            return {}
        return state_data.get("payload", {}) or {}

    def list_current_steps(self) -> Dict[str, int]:
        """批量读所有项目的 current_step（N+1 查询优化，list_projects 用）

        Returns:
            {project_id: current_step} dict
        """
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT project_id, current_step FROM onboarding_state"
            ).fetchall()
        result: Dict[str, int] = {}
        for r in rows:
            try:
                result[r["project_id"]] = int(r["current_step"])
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------ #
    # 写
    # ------------------------------------------------------------------ #

    def upsert_step(
        self,
        project_id: str,
        step_num: int,
        state_data: Dict[str, Any],
    ) -> None:
        """upsert onboarding_state 行（step 推进）

        Args:
            project_id: 项目 ID
            step_num:   步骤编号（1-5）
            state_data: 完整的 state_json dict（由调用方构造，避免 Repository 承载业务逻辑）
        """
        now = _now()
        state_json_str = json.dumps(state_data, ensure_ascii=False)
        with get_store().connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE onboarding_state "
                    "SET current_step = ?, state_json = ?, updated_at = ? "
                    "WHERE project_id = ?",
                    (step_num, state_json_str, now, project_id),
                )
            else:
                conn.execute(
                    "INSERT INTO onboarding_state "
                    "(project_id, current_step, started_at, updated_at, state_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (project_id, step_num, now, now, state_json_str),
                )

    def merge_payload(
        self,
        project_id: str,
        step_num: int,
        fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将 fields 合并到 state_json.payload（已有字段保留，新字段追加/覆盖）

        Args:
            project_id: 项目 ID
            step_num:   完成的步骤编号，同步写入 current_step 列
            fields:     本次新增/修改的字段

        Returns:
            merged_payload: 合并后的完整 payload
        """
        now = _now()
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"onboarding state not found for project: {project_id}")
            state_data = json.loads(row["state_json"])
            existing_payload = state_data.get("payload", {}) or {}
            merged = {**existing_payload, **fields}
            state_data["payload"] = merged
            state_data["updated_at"] = now.isoformat()
            conn.execute(
                "UPDATE onboarding_state "
                "SET current_step = ?, state_json = ?, updated_at = ? "
                "WHERE project_id = ?",
                (step_num, json.dumps(state_data, ensure_ascii=False), now, project_id),
            )
        return merged

    def update_project_name(self, project_id: str, new_name: str) -> None:
        """将自动生成的项目名写入 state_json.project_name

        注意：projects.name 由 ProjectRepository.update_name() 负责，这里只写 state_json。
        """
        now = _now()
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if not row:
                return  # 不存在则静默跳过（幂等）
            state_data = json.loads(row["state_json"])
            state_data["project_name"] = new_name
            state_data["updated_at"] = now.isoformat()
            conn.execute(
                "UPDATE onboarding_state "
                "SET state_json = ?, updated_at = ? "
                "WHERE project_id = ?",
                (json.dumps(state_data, ensure_ascii=False), now, project_id),
            )

    def mark_artifacts_generated(self, project_id: str) -> None:
        """标记 7 件产物已生成"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE onboarding_state "
                "SET artifacts_generated = 1, updated_at = ? "
                "WHERE project_id = ?",
                (_now(), project_id),
            )

    def mark_chapter1_generated(self, project_id: str, chapter_path: str) -> None:
        """标记第 1 章已生成"""
        with get_store().connection() as conn:
            conn.execute(
                "UPDATE onboarding_state "
                "SET chapter_1_generated = 1, chapter_1_path = ?, updated_at = ? "
                "WHERE project_id = ?",
                (chapter_path, _now(), project_id),
            )

