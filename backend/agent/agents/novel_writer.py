"""novel_writer — 小说文笔家

职责：
1. 章节正文生成 + 落盘（generate_chapter 工具）
2. Summary 抽取（summarize_chapter 工具）
3. 文风控制（system_prompt 由 agent_prompt_factory 注入笔风+法则）
4. 历史承接（build_project_context_message 注入 7 件 + chapter_summaries）

实现：文笔家走纯 ReAct loop，LLM 自主调工具。
外部入口统一通过 delegate_chapter_generation() 委托。
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List

from backend.agent.runtime.executor import AgentExecutor, AgentConfig, get_agent_executor
from backend.utils.logger import logger as logger_decorator


# ============ Writer 响应结构 ============

class ChapterOutput(BaseModel):
    """文笔家生成章节的输出"""
    chapter_content: str = ""
    chapter_summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    opinion: str = ""
    iterations: int = 0
    tool_calls_count: int = 0
    error: Optional[str] = None
    chapter_num: Optional[int] = None
    title: Optional[str] = None
    word_count: Optional[int] = None
    # v003: consistency_checker 两阶段校验结果（arch-plan §5.4）
    consistency_hard_rules: Optional[dict] = None
    consistency_world_entries: Optional[dict] = None


# ============ NovelWriter 主类 ============

@logger_decorator
class NovelWriter:
    """小说文笔家

    system_prompt 由 build_writer_system_prompt 动态组装（身份+笔风+法则+基座摘要）。
    完整 7 件基座 + 章节摘要通过 context_message 注入，不进 system_prompt。
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        self.executor = executor or get_agent_executor()

    async def generate_chapter(
        self,
        project_id: str,
        user_message: str = "请生成下一章",
        max_iterations: int = 15,
    ) -> ChapterOutput:
        """生成下一章（ReAct loop）

        Args:
            project_id: 项目 ID
            user_message: 用户提示
            max_iterations: ReAct loop 最大轮次（默认 15）

        Returns:
            ChapterOutput（含 chapter_num/title/word_count/chapter_content/chapter_summary/error）
        """
        self.log.info(
            "NovelWriter.generate_chapter START: project_id=%s, user_msg_len=%d, max_iterations=%d",
            project_id, len(user_message), max_iterations,
        )

        from backend.agent.prompts.agent_prompt_factory import (
            build_writer_system_prompt,
            build_project_context_message,
        )

        # session_key 按 project 维度隔离（不跨 project）
        # 文笔家需要跨调用记住已写章节的上下文，避免章节衔接断裂
        session_key = f"{project_id}:novel_writer"

        # 每次都传入完整的 system_prompt，HIT/MISS 判断由 executor 内部決定
        # （避免调用方预检查和 executor 内部检查间的极小概率时序竞争）
        system_prompt = build_writer_system_prompt(project_id)
        # context_message（7 件基座快照）每次都刷新，确保 LLM 看到最新基座状态
        context_message = build_project_context_message(project_id, "novel_writer")

        cfg = AgentConfig(
            agent_name="novel_writer",
            system_prompt=system_prompt,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=user_message,
            project_id=project_id,
            context_message=context_message,
            session_key=session_key,
            max_iterations=max_iterations,
        )

        # 从 tool_calls_history 里找落盘结果
        chapter_content = ""
        chapter_summary = ""
        chapter_num = None
        title = None
        word_count = None

        for tc_record in executor_output.tool_calls_history:
            tool_name = tc_record.get("tool_name", "")
            tool_result = tc_record.get("result", {}) or {}
            if tool_name == "generate_chapter" and tc_record.get("status") == "success":
                chapter_num = tool_result.get("num")
                title = tool_result.get("title")
                word_count = tool_result.get("word_count")
                chapter_content = tool_result.get("content", "")
            elif tool_name == "summarize_chapter" and tc_record.get("status") == "success":
                chapter_summary = tool_result.get("summary", "")

        # 兜底：LLM 未调工具时用 final_response
        if not chapter_content and executor_output.final_response:
            chapter_content = executor_output.final_response

        if executor_output.error:
            self.log.error(
                "NovelWriter.generate_chapter ERROR: project_id=%s, error=%s, iterations=%d",
                project_id, executor_output.error, executor_output.iterations,
            )
        else:
            self.log.info(
                "NovelWriter.generate_chapter DONE: project_id=%s, num=%s, title=%s, "
                "content_len=%d, summary_len=%d, iterations=%d, tool_calls=%d",
                project_id, chapter_num, title,
                len(chapter_content), len(chapter_summary),
                executor_output.iterations, len(executor_output.tool_calls_history),
            )

        return ChapterOutput(
            chapter_content=chapter_content,
            chapter_summary=chapter_summary,
            confidence=0.85 if not executor_output.error else 0.0,
            opinion=executor_output.final_response[:200] if executor_output.final_response else "",
            iterations=executor_output.iterations,
            tool_calls_count=len(executor_output.tool_calls_history),
            error=executor_output.error,
            chapter_num=chapter_num,
            title=title,
            word_count=word_count,
        )


# ============ 世界树基座完整性校验 ============

def _validate_world_tree_completeness(project_id: str) -> Optional[str]:
    """章节生成前的世界树基座完整性校验（含笔风）

    v003 重构（spec §5.6）：
    - world_tree: story_core / genre_tags_json / core_rules_json 非空
    - characters: 至少 1 个 protagonist
    - main_plot: 至少 1 个 pending 节点
    - volumes: 至少 1 个卷
    - style_pack_id: projects.style_pack_id 非空

    Returns:
        None     — 校验通过
        str      — 校验失败原因（供 ChapterOutput.error 使用）
    """
    try:
        from backend.persistence import ProjectRepository

        repo = ProjectRepository()
        missing: list[str] = []

        # 1. world_tree 5 字段最终态
        wt = repo.get_world_tree(project_id)
        if not wt:
            missing.append("world_tree（世界树）")
        else:
            if not wt.story_core:
                missing.append("world_tree.story_core（故事核心）")
            if not wt.genre_tags_json:
                missing.append("world_tree.genre_tags_json（题材标签）")
            if not wt.core_rules_json:
                missing.append("world_tree.core_rules_json（世界核心规则）")

        # 2. characters 至少 1 个 protagonist
        characters = repo.list_characters(project_id)
        if not characters:
            missing.append("characters（成员列表）")
        elif not any(c.role == "protagonist" for c in characters):
            missing.append("characters（至少 1 个 protagonist）")

        # 3. main_plot 至少 1 个 pending 节点
        main_plot_nodes = repo.list_main_plot_nodes(project_id)
        if not main_plot_nodes:
            missing.append("main_plot（主线节点）")
        elif not any(n.status == "pending" for n in main_plot_nodes):
            missing.append("main_plot（至少 1 个 pending 节点）")

        # 4. volumes 至少 1 个
        volumes = repo.list_volumes(project_id)
        if not volumes:
            missing.append("volumes（卷规划）")

        # 5. style_pack_id（笔风）
        if not repo.get_style_pack_id(project_id):
            missing.append("style_pack_id（写作笔风，请通过 adjust_style 工具设置）")

        if missing:
            return f"以下世界树基座缺失或为空：{', '.join(missing)}"
        return None

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "_validate_world_tree_completeness: 校验异常（非阻断）project_id=%s: %s",
            project_id, e,
        )
        return None


# ============ 委托入口 ============

@logger_decorator
async def delegate_chapter_generation(
    project_id: str,
    intervention: Optional[str] = None,
    source: str = "unknown",
    extra_context: Optional[str] = None,
) -> ChapterOutput:
    """章节生成委托入口

    v003：删 actor_feedback / actor_character 入参
    """
    user_message_parts = [f"请生成下一章（触发源: {source}）"]
    if intervention:
        user_message_parts.append(f"用户干预: {intervention}")
    if extra_context:
        user_message_parts.append(f"额外上下文: {extra_context}")
    user_message = "\n".join(user_message_parts)

    delegate_chapter_generation.log.info(
        "delegate_chapter_generation START: project_id=%s, source=%s, intervention=%s",
        project_id, source, bool(intervention),
    )

    # ── 7 件基座完整性校验（含笔风），任一缺失直接熔断，不让 LLM 用空占位符生成 ──
    validation_error = _validate_world_tree_completeness(project_id)
    if validation_error:
        delegate_chapter_generation.log.error(
            "delegate_chapter_generation BLOCKED by completeness check: project_id=%s, reason=%s",
            project_id, validation_error,
        )
        return ChapterOutput(error=f"基座完整性校验失败，无法生成章节：{validation_error}")

    writer = get_novel_writer()
    result = await writer.generate_chapter(
        project_id=project_id,
        user_message=user_message,
    )

    # ── 一致性两阶段校验（arch-plan §5.4：spec §5.4 要求）─────────────────
    # 阶段 1: 硬约束违例扫描（致命可阻断）
    # 阶段 2: 知识库矛盾检测（警告不阻断）
    # v003 bugfix: 之前漏掉了这两步
    if not result.error and result.chapter_content:
        try:
            from backend.services.consistency_checker import ConsistencyChecker
            checker = ConsistencyChecker(project_id)

            # 阶段 1: 硬约束违例
            hr_result = checker.check_hard_rules(
                chapter_text=result.chapter_content,
                character_actions=None,
            )
            result.consistency_hard_rules = hr_result.model_dump()

            delegate_chapter_generation.log.info(
                "consistency check_hard_rules: project_id=%s, violations=%d, has_fatal=%s",
                project_id, len(hr_result.violations), hr_result.has_fatal,
            )

            # 阶段 2: 知识库矛盾
            we_result = checker.check_world_entries(
                chapter_text=result.chapter_content,
                category=None,
            )
            result.consistency_world_entries = we_result.model_dump()

            delegate_chapter_generation.log.info(
                "consistency check_world_entries: project_id=%s, conflicts=%d, has_warnings=%s",
                project_id, len(we_result.conflicts), we_result.has_warnings,
            )

            # 默认不阻断（欧尼酱拍板：只检测不阻断，避免误伤）
            # 若后续需求变更需要硬阻断，返 ChapterOutput(error=...)
        except Exception as e:
            delegate_chapter_generation.log.warning(
                "consistency check failed: project_id=%s, error=%s",
                project_id, e,
            )
            # 一致性检查失败不影响章节落盘

    delegate_chapter_generation.log.info(
        "delegate_chapter_generation DONE: project_id=%s, source=%s, chapter_num=%s, error=%s",
        project_id, source, result.chapter_num, result.error,
    )

    return result


# ============ 工厂方法 ============

_writer_instance: Optional[NovelWriter] = None


def get_novel_writer() -> NovelWriter:
    """获取单例 NovelWriter"""
    global _writer_instance
    if _writer_instance is None:
        _writer_instance = NovelWriter()
    return _writer_instance