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
        """LIST_PROJECTS: 查 projects 表（s3.7 实装）"""
        from backend.persistence import ProjectRepository
        repo = ProjectRepository()
        projects = repo.list_all(limit=50)  # v0.6 简化：列所有（未删）
        if not projects:
            return {
                "intent": Intent.LIST_PROJECTS.value,
                "confidence": 1.0,
                "response": "📚 你还没有创建任何小说项目。\n\n试试在首页聊天框告诉我你想写什么，比如：“我想写个赛博朋克爱情故事”。",
                "structured_data": {"projects": []},
                "downstream_called": None,
            }
        # 按 updated_at 倒序
        projects.sort(key=lambda p: p.updated_at, reverse=True)
        project_cards = [
            {
                "id": p.id,
                "name": p.name,
                "palette": p.palette,
                "exploration_level": p.exploration_level,
                "current_pov": p.current_pov,
                "cover_image_url": p.cover_image_url,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in projects
            if not p.deleted_at
        ]
        names = "、".join(p["name"] for p in project_cards[:5])
        response = f"📚 你共有 {len(project_cards)} 个小说项目：\n\n" + "\n".join(
            f"  • 《{p['name']}》 (ID: {p['id'][:8]}...)"
            for p in project_cards[:10]
        )
        return {
            "intent": Intent.LIST_PROJECTS.value,
            "confidence": 1.0,
            "response": response,
            "structured_data": {"projects": project_cards},
            "downstream_called": None,
        }

    async def _handle_query_projects(self, intent_result: IntentResult, user_id: str) -> dict:
        """QUERY_PROJECTS: 按类型/状态筛选（s3.7 实装）

        v0.6 简化：从 style_charter / genre_resonance 表查询 genre/styles/tone
        """
        from backend.persistence import ProjectRepository
        repo = ProjectRepository()
        all_projects = repo.list_all(limit=50)
        all_projects = [p for p in all_projects if not p.deleted_at]

        # 筛选逻辑（v0.6 简化：用项目名模糊匹配 + 后续可接 genre_resonance 表）
        filter_genre = intent_result.args.filter_genre
        filter_style = intent_result.args.filter_style
        filter_status = intent_result.args.filter_status

        matched = []
        if filter_genre or filter_style:
            # v0.6 简化：匹配项目名（后续可查 genre_resonance 表）
            keyword = filter_genre or filter_style or ""
            for p in all_projects:
                if keyword.lower() in p.name.lower():
                    matched.append({
                        "id": p.id,
                        "name": p.name,
                        "palette": p.palette,
                        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                    })
        else:
            matched = [{"id": p.id, "name": p.name} for p in all_projects]

        if not matched:
            response = f"🔍 没找到匹配的项目。" + (f"（按 {filter_genre or filter_style} 筛选）" if (filter_genre or filter_style) else "")
        else:
            response = f"🔍 找到 {len(matched)} 个项目：\n\n" + "\n".join(
                f"  • 《{p['name']}》 (ID: {p.get('id', '?')[:8]}...)"
                for p in matched[:10]
            )
        return {
            "intent": Intent.QUERY_PROJECTS.value,
            "confidence": intent_result.confidence,
            "response": response,
            "structured_data": {"projects": matched, "filter": {
                "genre": filter_genre, "style": filter_style, "status": filter_status,
            }},
            "downstream_called": None,
        }

    async def _handle_recommend_projects(self, intent_result: IntentResult, user_id: str) -> dict:
        """RECOMMEND_PROJECTS: 推荐项目（s3.7 实装）

        v0.6 简化：按 updated_at 倒序列最近的项目，让管家 LLM 拼推荐语
        """
        from backend.persistence import ProjectRepository
        repo = ProjectRepository()
        projects = [p for p in repo.list_all(limit=10) if not p.deleted_at]
        projects.sort(key=lambda p: p.updated_at, reverse=True)

        if not projects:
            return {
                "intent": Intent.RECOMMEND_PROJECTS.value,
                "confidence": 1.0,
                "response": "✨ 你还没有项目可推荐。试试创建一个吧！",
                "structured_data": {"projects": []},
                "downstream_called": None,
            }

        # v0.6 简化：直接列最近的项目（后续可让 LLM 拼推荐理由）
        response = "✨ 根据你最近的创作，推荐以下项目：\n\n" + "\n".join(
            f"  • 《{p.name}》 — 最后更新 {p.updated_at.strftime('%Y-%m-%d') if p.updated_at else '?'}"
            for p in projects[:5]
        )
        return {
            "intent": Intent.RECOMMEND_PROJECTS.value,
            "confidence": 1.0,
            "response": response,
            "structured_data": {"projects": [
                {"id": p.id, "name": p.name, "updated_at": p.updated_at.isoformat() if p.updated_at else None}
                for p in projects[:5]
            ]},
            "downstream_called": None,
        }

    async def _handle_create_project(self, intent_result: IntentResult, user_id: str) -> dict:
        """CREATE_PROJECT: 启动 Onboarding（s3 实装）"""
        initial_idea = intent_result.args.initial_idea or "（未提供初始想法）"
        # 启动 Onboarding Step 3（Step 1-2 走按钮式入口）
        from backend.agent.onboarding_controller import (
            get_onboarding_controller, OnboardingState, OnboardingStep,
        )
        controller = get_onboarding_controller()
        state = OnboardingState(
            project_id=None,
            current_step=OnboardingStep.STEP_3,
        )
        result = await controller.run_step_3_or_4(
            user_message=initial_idea,
            state=state,
        )
        return {
            "intent": Intent.CREATE_PROJECT.value,
            "confidence": intent_result.confidence,
            "response": result.assistant_response or f"好的！'{initial_idea}' 听起来很有意思～ 我们开始一步步搭建这个世界吧。",
            "structured_data": {
                "initial_idea": initial_idea,
                "onboarding_step": result.new_state.current_step.value,
                "onboarding_history": result.new_state.history,
            },
            "downstream_called": "onboarding_controller",
        }

    async def _handle_open_project(self, intent_result: IntentResult, user_id: str) -> dict:
        """OPEN_PROJECT: LLM 模糊匹配 + 用户确认（06-24 17:09 拍板，s3.7 实装）

        规则（spec.md §4.4）：
        - 1 个匹配 → 展示跳转卡片，用户点确认
        - 多个匹配 → 列候选清单，用户选择
        - 0 个匹配 → 推荐创建
        - 不直接跳转（必须用户主动点确认）
        """
        from backend.persistence import ProjectRepository
        repo = ProjectRepository()
        hint = intent_result.args.project_name_hint or ""

        if not hint:
            return {
                "intent": Intent.OPEN_PROJECT.value,
                "confidence": intent_result.confidence,
                "response": "📂 请告诉我你想打开哪个项目？",
                "structured_data": {"candidates": [], "require_confirm": True},
                "downstream_called": None,
            }

        # 查所有未删项目，做模糊匹配
        all_projects = [p for p in repo.list_all(limit=100) if not p.deleted_at]
        candidates = []
        hint_lower = hint.lower()
        for p in all_projects:
            if hint_lower in p.name.lower() or hint_lower in p.id.lower():
                candidates.append({
                    "id": p.id,
                    "name": p.name,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                })

        if len(candidates) == 1:
            p = candidates[0]
            response = f"📂 找到 1 个项目：\n\n  • 《{p['name']}》\n\n点击确认跳转。"
            return {
                "intent": Intent.OPEN_PROJECT.value,
                "confidence": intent_result.confidence,
                "response": response,
                "structured_data": {
                    "candidates": candidates,
                    "require_confirm": True,  # 即使 1 个也要确认
                    "jump_url": f"/reader/{p['id']}",
                },
                "downstream_called": None,
            }
        elif len(candidates) > 1:
            response = f"📂 找到 {len(candidates)} 个匹配项目：\n\n" + "\n".join(
                f"  {i+1}. 《{c['name']}》 (ID: {c['id'][:8]}...)"
                for i, c in enumerate(candidates[:10])
            ) + "\n\n请告诉我你想打开哪一个。"
            return {
                "intent": Intent.OPEN_PROJECT.value,
                "confidence": intent_result.confidence,
                "response": response,
                "structured_data": {"candidates": candidates, "require_confirm": True},
                "downstream_called": None,
            }
        else:
            response = f"📂 没找到叫《{hint}》的项目。\n\n要不要创建一个？试试说“我想写个 {hint}”"
            return {
                "intent": Intent.OPEN_PROJECT.value,
                "confidence": intent_result.confidence,
                "response": response,
                "structured_data": {"candidates": [], "suggest_create": True, "hint": hint},
                "downstream_called": None,
            }

    async def _handle_adjust_global_pref(self, intent_result: IntentResult, user_id: str) -> dict:
        """ADJUST_GLOBAL_PREFERENCE: 调整全局偏好（s3.7 实装，最小可用集）

        支持的偏好（v0.6 最小可用集）：
        - default_exploration_level: conservative / standard / wild
        """
        from backend.persistence import UserPreferenceRepository

        key = intent_result.args.preference_key
        value = intent_result.args.preference_value

        if not key or not value:
            return {
                "intent": Intent.ADJUST_GLOBAL_PREFERENCE.value,
                "confidence": intent_result.confidence,
                "response": "⚙️ 没能识别你的偏好名和值。试试说：“以后默认探索度用 standard”",
                "structured_data": {},
                "downstream_called": None,
            }

        # 最小可用集校验
        SUPPORTED_KEYS = {"default_exploration_level"}
        SUPPORTED_VALUES = {
            "default_exploration_level": {"conservative", "standard", "wild"},
        }

        if key not in SUPPORTED_KEYS:
            return {
                "intent": Intent.ADJUST_GLOBAL_PREFERENCE.value,
                "confidence": intent_result.confidence,
                "response": f"⚙️ 偏好 '{key}' 暂未支持。\n\n目前支持：{', '.join(SUPPORTED_KEYS)}",
                "structured_data": {"supported": list(SUPPORTED_KEYS)},
                "downstream_called": None,
            }

        if value not in SUPPORTED_VALUES[key]:
            valid = "/".join(SUPPORTED_VALUES[key])
            return {
                "intent": Intent.ADJUST_GLOBAL_PREFERENCE.value,
                "confidence": intent_result.confidence,
                "response": f"⚙️ 值 '{value}' 无效。'{key}' 需是: {valid}",
                "structured_data": {},
                "downstream_called": None,
            }

        # 写 user_preferences 表
        repo = UserPreferenceRepository()
        await repo.set(user_id=user_id, key=key, value=value)

        return {
            "intent": Intent.ADJUST_GLOBAL_PREFERENCE.value,
            "confidence": intent_result.confidence,
            "response": f"✅ 已设置全局偏好：{key} = {value}\n\n以后创建项目默认使用该值。",
            "structured_data": {"key": key, "value": value, "updated": True},
            "downstream_called": None,
        }

    # ─── 项目级 intent 处理方法（v0.6 s3/s4 实装） ─────

    async def _handle_generate(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """GENERATE: 转发到小说文笔家（s3 实装）"""
        chapter_output = await self.novel_writer.generate_chapter(
            project_id=project_id,
            user_message=user_message,
        )
        if chapter_output.error:
            return {
                "intent": Intent.GENERATE.value,
                "confidence": intent_result.confidence,
                "response": f"❌ 章节生成失败：{chapter_output.error}",
                "structured_data": {"project_id": project_id, "error": chapter_output.error},
                "downstream_called": "novel_writer",
            }
        return {
            "intent": Intent.GENERATE.value,
            "confidence": intent_result.confidence,
            "response": f"📖 已生成下一章（{chapter_output.iterations} 轮推演、{chapter_output.tool_calls_count} 个 tool）\n\n{chapter_output.chapter_content[:500]}...",
            "structured_data": {
                "project_id": project_id,
                "chapter_content": chapter_output.chapter_content,
                "chapter_summary": chapter_output.chapter_summary,
                "iterations": chapter_output.iterations,
            },
            "downstream_called": "novel_writer",
        }

    async def _handle_intervene(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """INTERVENE: 转发到世界树管理（s3 实装）"""
        intervention = intent_result.args.intervention_text or user_message
        diff = await self.world_tree_manager.analyze_intervention(
            project_id=project_id,
            intervention_text=intervention,
        )
        # 转成对话文本
        response_text = self._format_diff_response(diff)
        return {
            "intent": Intent.INTERVENE.value,
            "confidence": intent_result.confidence,
            "response": response_text,
            "structured_data": {
                "project_id": project_id,
                "intervention_text": intervention,
                "diff": diff.model_dump(),
                "require_confirm": diff.requires_double_confirm,
            },
            "downstream_called": "world_tree_manager",
        }

    async def _handle_adjust_base(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """ADJUST_BASE: 转发到世界树管理（s3 实装）"""
        adjustment = intent_result.args.intervention_text or user_message
        diff = await self.world_tree_manager.analyze_base_adjustment(
            project_id=project_id,
            adjustment_text=adjustment,
        )
        response_text = self._format_diff_response(diff)
        return {
            "intent": Intent.ADJUST_BASE.value,
            "confidence": intent_result.confidence,
            "response": response_text,
            "structured_data": {
                "project_id": project_id,
                "adjustment_text": adjustment,
                "diff": diff.model_dump(),
                "require_confirm": diff.requires_double_confirm,
            },
            "downstream_called": "world_tree_manager",
        }

    async def _handle_rollback(self, project_id: str) -> dict:
        """ROLLBACK: 回档（危险操作，管家直接处理 + 弹确认）"""
        return {
            "intent": Intent.ROLLBACK.value,
            "confidence": 1.0,
            "response": "⏪ [s3 骨架] 回档待后续实装（需用户二次确认）",
            "structured_data": {"project_id": project_id, "require_confirm": True},
            "downstream_called": None,
        }

    async def _handle_onboarding_continue(self, project_id: str, user_message: str, intent_result: IntentResult) -> dict:
        """ONBOARDING_CONTINUE: 启动 OnboardingController（s3.5 实装）"""
        from backend.agent.onboarding_controller import (
            get_onboarding_controller, OnboardingState, OnboardingStep,
        )
        controller = get_onboarding_controller()
        state = OnboardingState(
            project_id=project_id,
            current_step=OnboardingStep.STEP_3,
        )
        result = await controller.run_step_3_or_4(
            user_message=user_message,
            state=state,
        )
        # 如果触发 Step 5，调 NovelWriter 生成
        if result.should_generate_chapter:
            if project_id:
                chapter_result = await controller.run_step_5_generate_chapter(project_id=project_id)
                if chapter_result.chapter_content:
                    return {
                        "intent": Intent.ONBOARDING_CONTINUE.value,
                        "confidence": intent_result.confidence,
                        "response": f"✅ Onboarding 完成！第 1 章已生成（{chapter_result.iterations} 轮推演）\n\n{chapter_result.chapter_content[:300]}...",
                        "structured_data": {
                            "project_id": project_id,
                            "chapter_content": chapter_result.chapter_content,
                            "chapter_summary": chapter_result.chapter_summary,
                            "step": "step_5_done",
                        },
                        "downstream_called": "novel_writer",
                    }
        return {
            "intent": Intent.ONBOARDING_CONTINUE.value,
            "confidence": intent_result.confidence,
            "response": result.assistant_response,
            "structured_data": {
                "project_id": project_id,
                "step": result.new_state.current_step.value,
                "should_generate_chapter": result.should_generate_chapter,
            },
            "downstream_called": None,
        }

    def _format_diff_response(self, diff) -> str:
        """把 WorldTreeDiff 转成对话文本"""
        lines = [
            f"🌿 {diff.summary}",
            f"\n风险等级：{diff.risk_level}" + ("（需二次确认）" if diff.requires_double_confirm else ""),
        ]
        if diff.base_updates:
            lines.append(f"\n基座变更：{len(diff.base_updates)} 条")
            for u in diff.base_updates[:3]:
                lines.append(f"  • {u.artifact}.{u.field}: {u.old_value} → {u.new_value}")
        if diff.plot_adjustments:
            lines.append(f"\n走向调整：{len(diff.plot_adjustments)} 条")
        if diff.new_seeds:
            lines.append(f"\n新埋伏笔：{len(diff.new_seeds)} 条")
        if diff.consistency.status != "PASS":
            lines.append(f"\n一致性：{diff.consistency.status} - {diff.consistency.conflicts[:1]}")
        lines.append(f"\n（经过 {diff.iterations} 轮推演、{diff.tool_calls_count} 个 tool 调用）")
        return "\n".join(lines)

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