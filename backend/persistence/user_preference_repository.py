"""UserPreferenceRepository: user_preferences 表的 CRUD

对应 spec.md §4.1
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.persistence.models import UserPreference
from backend.persistence.sqlite_store import get_store


class UserPreferenceRepository:
    """用户偏好 Repository（复合主键 user_id + key）"""

    async def set(self, user_id: str, key: str, value: Optional[str]) -> None:
        """设置偏好（upsert）"""
        with get_store().connection() as conn:
            conn.execute(
                """INSERT INTO user_preferences (user_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id, key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = excluded.updated_at""",
                (user_id, key, value, datetime.now()),
            )

    async def get(self, user_id: str, key: str) -> Optional[str]:
        """获取偏好，不存在返回 None"""
        with get_store().connection() as conn:
            row = conn.execute(
                "SELECT value FROM user_preferences WHERE user_id = ? AND key = ?",
                (user_id, key),
            ).fetchone()
        return row["value"] if row else None

    async def list_all(self, user_id: str) -> list[UserPreference]:
        """列出某用户所有偏好"""
        with get_store().connection() as conn:
            rows = conn.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return [
            UserPreference(
                user_id=r["user_id"], key=r["key"], value=r["value"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
