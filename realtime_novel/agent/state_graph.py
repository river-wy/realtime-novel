"""build_graph() — 6 节点 LangGraph StateGraph

对应 core.md §B.2.3

v0.4 简化版：
- 不依赖真实 langgraph 包（langgraph 0.2.0 安装复杂）
- 手写一个 StateGraph-like 的顺序执行器
- 支持 condition edge（should_retry / should_interrupt）
"""
from __future__ import annotations

import asyncio
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

from realtime_novel.agent.state import AgentState
from realtime_novel.agent.nodes import (
    intake_node, consult_experts_node, plan_node, act_node,
    reflect_node, respond_node, should_retry, should_interrupt,
)


# ============ 简化 StateGraph ============

class SimpleStateGraph:
    """v0.4 简化版 StateGraph：顺序 + 条件边

    完整版用 langgraph.StateGraph；v0.4 简化为手写版本（避免 langgraph 依赖复杂性）
    """

    def __init__(self, initial_state: AgentState):
        self.state = initial_state
        self.checkpoint_path: Path | None = None

    def with_checkpoint(self, db_path: Path | str):
        """启用 checkpoint 持久化（agent_state 表）"""
        self.checkpoint_path = Path(db_path)
        return self

    async def ainvoke(self, input_state: AgentState, progress_callback=None) -> AgentState:
        """异步执行 6 节点 + 条件边 (v0.4 P1-1: 传 progress_callback)"""
        self.state = input_state
        # 顺序：intake → consult_experts → plan → act → reflect → respond
        steps = [
            ("intake", intake_node),
            ("consult_experts", consult_experts_node),
            ("plan", plan_node),
            ("act", act_node),
            ("reflect", reflect_node),
            ("respond", respond_node),
        ]
        for step_name, step_func in steps:
            # 检查打断
            if self.state.interrupt_requested and step_name in ("plan", "act", "reflect", "respond"):
                self.state.final_response = "已打断"
                return self.state
            # act_node 透传 progress_callback；其他节点不传
            if step_name == "act" and progress_callback is not None:
                update = await step_func(self.state, progress_callback=progress_callback)
            else:
                update = await step_func(self.state)
            # 合并 update 到 state
            for k, v in update.items():
                setattr(self.state, k, v)
            # 条件边：reflect → plan（重试）或 respond
            if step_name == "reflect":
                next_step = should_retry(self.state)
                if next_step == "plan":
                    self.state.retry_count += 1
                    # 跳回 plan
                    plan_update = await plan_node(self.state)
                    for k, v in plan_update.items():
                        setattr(self.state, k, v)
                    # 跳回 act
                    act_update = await act_node(self.state)
                    for k, v in act_update.items():
                        setattr(self.state, k, v)
                    # 跳回 reflect
                    reflect_update = await reflect_node(self.state)
                    for k, v in reflect_update.items():
                        setattr(self.state, k, v)
                    # 继续到 respond
            # 持久化 checkpoint（每步）
            if self.checkpoint_path:
                self._save_checkpoint()
        return self.state

    def _save_checkpoint(self):
        """保存 checkpoint 到 SQLite agent_state 表"""
        if not self.checkpoint_path:
            return
        from realtime_novel.persistence import get_store
        try:
            with get_store().connection() as conn:
                conn.execute(
                    """INSERT INTO agent_state (thread_id, checkpoint_data, updated_at)
                       VALUES (?, ?, ?)
                       ON CONFLICT(thread_id) DO UPDATE SET
                         checkpoint_data = excluded.checkpoint_data,
                         updated_at = excluded.updated_at""",
                    (
                        self.state.conversation_id or "default",
                        json.dumps(self.state.model_dump(), default=str),
                        datetime.now(),
                    ),
                )
        except Exception:
            pass  # 不影响主流程


# 全局单例
_graph: SimpleStateGraph | None = None


def build_graph() -> SimpleStateGraph:
    """构建 v0.4 简化 StateGraph

    v0.4 简化版不依赖 langgraph（Phase 3+ 替换为真实 langgraph）
    """
    global _graph
    if _graph is None:
        from realtime_novel.persistence import get_store
        initial = AgentState(user_message="", conversation_id="default")
        _graph = SimpleStateGraph(initial).with_checkpoint(get_store().db_path)
    return _graph


def reset_graph() -> None:
    """重置（测试用）"""
    global _graph
    _graph = None
