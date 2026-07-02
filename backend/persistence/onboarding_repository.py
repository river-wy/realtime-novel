"""OnboardingRepository：onboarding_state 表 CRUD

v003 重构（spec §5.8.6）：
- 新增字段：info_state (collecting / wtm_pending / ready), payload_json, last_activity_at
- 旧字段：current_step, state_json 保留（向后兼容，但不依赖）
- 新增方法：set_info_state, get_info_state, upsert_info_state
"""
from __future__ import annotations

import json
import logging
log = logging.getLogger(__name__)

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

    def get_payload(self, project_id: str) -> Dict[str, Any]:
        """读 payload_json（管家调工具暂存的信息），不存在返回空 dict"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None or not row["payload_json"]:
            return {}
        try:
            return json.loads(row["payload_json"])
        except Exception as e:
            log.warning("onboarding_repo.get_payload 解析失败, 返空: project_id=%s, error=%s", project_id, e, exc_info=True)
            return {}

    def get_info_state(self, project_id: str) -> str:
        """读 info_state（spec §5.8.5）"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT info_state FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return "collecting"
        return row["info_state"]

    def get_state_json(self, project_id: str) -> Optional[Dict[str, Any]]:
        """兼容旧方法：从 state_json 读（v003 优先读 payload_json）"""
        # 优先返回 payload_json
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT payload_json, state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        if row["payload_json"]:
            try:
                return json.loads(row["payload_json"])
            except Exception as e:
                log.warning("onboarding_repo 读 state_json 失败: project_id=%s, error=%s", project_id, e, exc_info=True)
                pass
        if row["state_json"]:
            try:
                return json.loads(row["state_json"])
            except Exception as e:
                log.warning("onboarding_repo JSON 解析失败, 返 None: project_id=%s, error=%s", project_id, e, exc_info=True)
                pass
        return None

    # ------------------------------------------------------------------ #
    # 写
    # ------------------------------------------------------------------ #

    def upsert_info_state(
        self,
        project_id: str,
        info_state: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """upsert onboarding_state 行（v003 主入口）

        Args:
            project_id: 项目 ID
            info_state: collecting / wtm_pending / ready
            payload: 管家调工具暂存的信息（可选）
        """
        if info_state not in ("collecting", "wtm_pending", "ready"):
            raise ValueError(f"info_state 必须是 collecting/wtm_pending/ready, 收到: {info_state!r}")

        now = _now()
        payload_str = json.dumps(payload or {}, ensure_ascii=False) if payload is not None else None

        with get_store().connection() as conn:
            existing = conn.execute(
                "SELECT payload_json, current_step, state_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()

            if existing:
                # 增量 UPDATE
                fields = ["info_state = ?", "last_activity_at = ?", "updated_at = ?"]
                values: list = [info_state, now, now]
                if payload_str is not None:
                    fields.append("payload_json = ?")
                    values.append(payload_str)
                values.append(project_id)
                conn.execute(
                    f"UPDATE onboarding_state SET {', '.join(fields)} WHERE project_id = ?",
                    values,
                )
            else:
                conn.execute(
                    """
                    INSERT INTO onboarding_state (
                        project_id, info_state, payload_json,
                        last_activity_at, created_at, updated_at,
                        current_step, state_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id, info_state, payload_str,
                        now, now, now,
                        0, None,
                    ),
                )

    def set_info_state(self, project_id: str, info_state: str) -> None:
        """仅设置 info_state（保留 payload 不变）"""
        self.upsert_info_state(project_id, info_state, payload=None)

    def merge_payload(
        self,
        project_id: str,
        step_num: int,
        fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        """将 fields 合并到 payload_json（已有字段保留，新字段追加/覆盖）

        v003：state_json 不再使用，改为 payload_json
        """
        now = _now()
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT payload_json FROM onboarding_state WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            existing_payload: Dict[str, Any] = {}
            if row and row["payload_json"]:
                try:
                    existing_payload = json.loads(row["payload_json"]) or {}
                except Exception as e:
                    log.warning("onboarding_repo 读 existing_payload 失败: project_id=%s, error=%s", project_id, e, exc_info=True)
                    existing_payload = {}
            merged = {**existing_payload, **fields}

            if row:
                conn.execute(
                    """
                    UPDATE onboarding_state
                    SET payload_json = ?, current_step = ?, last_activity_at = ?, updated_at = ?
                    WHERE project_id = ?
                    """,
                    (
                        json.dumps(merged, ensure_ascii=False),
                        step_num, now, now,
                        project_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO onboarding_state (
                        project_id, info_state, payload_json,
                        last_activity_at, created_at, updated_at,
                        current_step, state_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id, "collecting",
                        json.dumps(merged, ensure_ascii=False),
                        now, now, now,
                        step_num, None,
                    ),
                )
        return merged
