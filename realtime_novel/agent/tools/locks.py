"""ProjectLockManager: per-project_id 锁（防止同项目并发生成/回档）

对应 core.md §B.1.4
"""
from __future__ import annotations

import asyncio
from typing import Dict


class ProjectLockManager:
    """per-project_id asyncio.Lock 池"""

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}

    def get_lock(self, project_id: str) -> asyncio.Lock:
        """获取/创建项目锁（同一 project_id 永远返回同一锁）"""
        if project_id not in self._locks:
            self._locks[project_id] = asyncio.Lock()
        return self._locks[project_id]

    def has_lock(self, project_id: str) -> bool:
        return project_id in self._locks

    def remove_lock(self, project_id: str) -> None:
        """清理锁（项目删除时调用）"""
        self._locks.pop(project_id, None)


# 全局单例
_locks = ProjectLockManager()


def get_project_lock(project_id: str) -> asyncio.Lock:
    """获取全局锁管理器的项目锁"""
    return _locks.get_lock(project_id)
