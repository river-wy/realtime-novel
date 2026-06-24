"""novel_steward — 小说管家（v0.6 顶层 Agent 之一）

职责（对应 spec.md §3.1）：
1. 唯一用户入口（所有 user_message 都先到管家）
2. 意图识别（IntentRecognizer.classify）
3. 路由分发（根据 intent 转发到 文笔家 / 世界树管理 / 内部处理）
4. 接管 Onboarding（5 步流程由管家自主驱动）
5. 结果聚合（组织对用户友好的回复）

关键设计：
- 不持久化 session（每次重新拼 messages）
- 不直接修改世界树基座（转发给世界树管理）
- 不直接生成章节正文（转发给文笔家）
- 管家只负责「听懂用户 → 找对人 → 回话」

对应 spec.md §3.1
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel

from backend.agent.intent_recognizer import (
    IntentRecognizer,
    IntentResult,
    get_intent_recognizer,
)
from backend.agent.novel_writer import NovelWriter, get_novel_writer
from backend.agent.world_tree_manager import WorldTreeManager, get_world_tree_manager
from backend.agent.state import Intent, AgentState

log = logging.getLogger(__name__)


# ============ 管家响应结构 ============

class StewardResponse(BaseModel):
    """管家响应结构（标准 schema）"""
    intent: str
    confidence: float
    response: str
    structured_data: dict = {}
    downstream_called: Optional[str] = None


# ============ NovelSteward 主类 ============

class NovelSteward:
    """小说管家（v0.6 顶层 Agent）

    使用方式：
        steward = NovelSteward()
        result = await steward.receive(
            user_message="我想写个赛博朋克爱情",
            project_id=None,  # 首页无 projectId
            user_id="wuyu49",
        )
        # result = {
        #   "intent": "create_project",
        #   "response": "听起来很棒！能详细说说...",
        #   "structured_data": {},
        #   "downstream_called": None,
        # }
    """

    def __init__(
        self,
        intent_recognizer: Optional[IntentRecognizer] = None,
        novel_writer: Optional[NovelWriter] = None,
        world_tree_manager: Optional[WorldTreeManager] = None,
    ):
        self.intent_recognizer = intent_recognizer or get_intent_recognizer()
        self.novel_writer = novel_writer or get_novel_writer()
        self.world_tree_manager = world_tree_manager or get_world_tree_manager()

    # ─── 入口方法 ──────────────────────────────────

    async def receive(
        self,
        user_message: str,
        project_id: Optional[str] = None,
        user_id: str = "default",
        in_onboarding: bool = False,
        conversation_id: Optional[str] = None,
    ) -> dict:
        """管家接收用户消息的主入口

        Args:
            user_message: 用户消息文本
            project_id: 项目 ID（None = 管家大厅模式）
            user_id: 用户 ID
            in_onboarding: 是否在 onboarding 流程中
            conversation_id: 对话 ID（用于 messages 表落库）

        Returns:
            {
                "intent": Intent,
                "confidence": float,
                "response": str,         # 对用户的最终回复
                "structured_data": dict,  # 结构化数据（项目列表/跳转 URL/确认卡片等）
                "downstream_called": str | None,  # 调用的下游 Agent
            }
        """
        # 1. 意图识别
        intent_result = await self.intent_recognizer.classify(
            user_message=user_message,
            has_project=project_id is not None,
            project_id=project_id,
            in_onboarding=in_onboarding,
        )

        log.info(
            f"novel_steward: intent={intent_result.intent.value} "
            f"confidence={intent_result.confidence:.2f} "
            f"project_id={project_id}"
        )

        # 2. 路由分发
        return await self._route(intent_result, project_id, user_id, user_message)

    async def _route(
        self,
        intent_result: IntentResult,
        project_id: Optional[str],
        user_id: str,
        user_message: str,
    ) -> dict:
        """根据 intent 路由到对应处理路径

        v0.6 s2 阶段：只搭骨架，返回固定文案。
        s3 阶段会实装真实逻辑（调下游 Agent / 写库等）。
        """
        intent = intent_result.intent

        # ─── 用户级 intent（管家大厅，无 project_id）──
        if intent == Intent.LIST_PROJECTS:
            return await self._handle_list_projects(user_id)
        elif intent == Intent.QUERY_PROJECTS:
            return await self._handle_query_projects(intent_result, user_id)
        elif intent == Intent.RECOMMEND_PROJECTS:
            return await self._handle_recommend_projects(intent_result, user_id)
        elif intent == Intent.CREATE_PROJECT:
            return await self._handle_create_project(intent_result, user_id)
        elif intent == Intent.OPEN_PROJECT:
            return await self._handle_open_project(intent_result, user_id)
        elif intent == Intent.ADJUST_GLOBAL_PREFERENCE:
            return await self._handle_adjust_global_pref(intent_result, user_id)

        # ─── 项目级 intent（项目管家，有 project_id）──
        elif intent == Intent.GENERATE:
            return await self._handle_generate(project_id, user_message, intent_result)
        elif intent == Intent.INTERVENE:
            return await self._handle_intervene(project_id, user_message, intent_result)
        elif intent == Intent.ADJUST_BASE:
            return await self._handle_adjust_base(project_id, user_message, intent_result)
        elif intent == Intent.ROLLBACK:
            return await self._handle_rollback(project_id)
        elif intent == Intent.ONBOARDING_CONTINUE:
            return await self._handle_onboarding_continue(project_id, user_message, intent_result)

        # ─── 兜底 ─────────────────────────────────
        else:  # CHAT
            return await self._handle_chat(user_message, project_id, user_id)

    # ─── 用户级 intent 处理方法（v0.6 s3 实装） ─────

    async def _handle_list_projects(self, user_id: str) -> dict:
        """LIST_PROJECTS: 查 projects 表"""
        # s3 实装：调 ProjectRepository.list_by_user(user_id)
        # s2 骨架：返回占位文案
        return {
            "intent": Intent.LIST_PROJECTS.value,
            "confidence": 1.0,
            "response": "📚 [s2 骨架] 查询项目列表功能待 s3 实装",
            "structured_data": {},
            "downstream_called": None,
        }

    async def _handle_query_projects(self, intent_result: IntentResult, user_id: str) -> dict:
        """QUERY_PROJECTS: 按类型/状态筛选"""
        return {
            "intent": Intent.QUERY_PROJECTS.value,
            "confidence": intent_result.confidence,
            "response": f"🔍 [s2 骨架] 筛选项目功能待 s3 实装 (args={intent_result.args.model_dump()})",
            "structured_data": {},
            "downstream_called": None,
        }

    async def _handle_recommend_projects(self, intent_result: IntentResult, user_id: str) -> dict:
        """RECOMMEND_PROJECTS: 推荐项目"""
        return {
            "intent": Intent.RECOMMEND_PROJECTS.value,
            "confidence": intent_result.confidence,
            "response": "✨ [s2 骨架] 推荐项目功能待 s3 实装",
            "structured_data": {},
            "downstream_called": None,
        }

    async def _handle_create_project(self, intent_result: IntentResult, user_id: str) -> dict:
        """CREATE_PROJECT: 启动 Onboarding"""
        initial_idea = intent_result.args.initial_idea or "（未提供初始想法）"
        return {
            "intent": Intent.CREATE_PROJECT.value,
            "confidence": intent_result.confidence,
            "response": f"🚀 [s2 骨架] 启动 Onboarding (initial_idea={initial_idea})，完整实装待 s3",
            "structured_data": {"initial_idea": initial_idea},
            "downstream_called": None,
        }

    async def _handle_open_project(self, intent_result: IntentResult, user_id: str) -> dict:
        """OPEN_PROJECT: LLM 模糊匹配 + 用户确认（06-24 17:09 拍板）"""
        hint = intent_result.args.project_name_hint or "（未提供）"
        return {
            "intent": Intent.OPEN_PROJECT.value,
            "confidence": intent_result.confidence,
            "response": f"📂 [s2 骨架] 匹配项目 '{hint}' 待 s3 实装（LLM 模糊匹配 + 用户确认）",
            "structured_data": {"project_name_hint": hint},
            "downstream_called": None,
        }

    async def _handle_adjust_global_pref(self, intent_result: IntentResult, user_id: str) -> dict:
        """ADJUST_GLOBAL_PREFERENCE: 调整全局偏好（最小可用集：default_exploration_level）"""
        key = intent_result.args.preference_key
        value = intent_result.args.preference_value
        return {
            "intent": Intent.ADJUST_GLOBAL_PREFERENCE.value,
            "confidence": intent_result.confidence,
            "response": f"⚙️ [s2 骨架] 全局偏好调整 ({key}={value}) 待 s3 实装",
            "structured_data": {"key": key, "value": value},
            "downstream_called": None,
        }

    # ─── 项目级 intent 处理方法（v0.6 s3/s4 实装） ─────

    async def _handle_generate(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """GENERATE: 转发到小说文笔家"""
        # s3 实装：调 self.novel_writer.generate_chapter(project_id, user_message)
        # s2 骨架：占位
        return {
            "intent": Intent.GENERATE.value,
            "confidence": intent_result.confidence,
            "response": "📖 [s2 骨架] 章节生成待 s3 实装（转 NovelWriter）",
            "structured_data": {"project_id": project_id},
            "downstream_called": "novel_writer",
        }

    async def _handle_intervene(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """INTERVENE: 转发到世界树管理"""
        intervention = intent_result.args.intervention_text or user_message
        return {
            "intent": Intent.INTERVENE.value,
            "confidence": intent_result.confidence,
            "response": f"🌿 [s2 骨架] 干预分析 '{intervention}' 待 s4 实装（转 WorldTreeManager）",
            "structured_data": {"intervention_text": intervention},
            "downstream_called": "world_tree_manager",
        }

    async def _handle_adjust_base(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """ADJUST_BASE: 转发到世界树管理"""
        return {
            "intent": Intent.ADJUST_BASE.value,
            "confidence": intent_result.confidence,
            "response": f"🌳 [s2 骨架] 基座调整待 s4 实装（转 WorldTreeManager）",
            "structured_data": {"project_id": project_id},
            "downstream_called": "world_tree_manager",
        }

    async def _handle_rollback(self, project_id: str) -> dict:
        """ROLLBACK: 回档（危险操作，管家直接处理 + 弹确认）"""
        return {
            "intent": Intent.ROLLBACK.value,
            "confidence": 1.0,
            "response": "⏪ [s2 骨架] 回档待 s3 实装（需用户二次确认）",
            "structured_data": {"project_id": project_id, "require_confirm": True},
            "downstream_called": None,
        }

    async def _handle_onboarding_continue(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """ONBOARDING_CONTINUE: Onboarding 多轮对话（管家内部处理）"""
        return {
            "intent": Intent.ONBOARDING_CONTINUE.value,
            "confidence": intent_result.confidence,
            "response": f"📝 [s2 骨架] Onboarding 继续对话待 s3 实装",
            "structured_data": {"project_id": project_id},
            "downstream_called": None,
        }

    async def _handle_chat(self, user_message: str, project_id: Optional[str], user_id: str) -> dict:
        """CHAT: 兜底闲聊（管家直接调 LLM）"""
        return {
            "intent": Intent.CHAT.value,
            "confidence": 1.0,
            "response": f"💬 [s2 骨架] 闲聊模式待 s3 实装（直接调 LLM）",
            "structured_data": {},
            "downstream_called": None,
        }


# ============ 工厂方法 ============

_steward_instance: Optional[NovelSteward] = None


def get_novel_steward() -> NovelSteward:
    """获取单例 NovelSteward"""
    global _steward_instance
    if _steward_instance is None:
        _steward_instance = NovelSteward()
    return _steward_instance