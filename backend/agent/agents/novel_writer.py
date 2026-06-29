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


# ============ 委托入口 ============

@logger_decorator
async def delegate_chapter_generation(
    project_id: str,
    intervention: Optional[str] = None,
    actor_feedback: Optional[str] = None,
    actor_character: Optional[str] = None,
    source: str = "unknown",
    extra_context: Optional[str] = None,
) -> ChapterOutput:
    """章节生成委托入口

    所有章节生成请求都通过此入口，走文笔家 ReAct loop + generate_chapter 工具落盘。

    调用方：
        - chapter_routes.py (POST /api/projects/{id}/chapters) → source="page_button"
        - tools/onboarding_tools.py OnboardingGenerateChapterTool → source="onboarding_step5"
        - delegation_tools.py _delegate_novel_writer → source="steward_react"
    """
    user_message_parts = [f"请生成下一章（触发源: {source}）"]
    if intervention:
        user_message_parts.append(f"用户干预: {intervention}")
    if actor_feedback:
        user_message_parts.append(f"演员反馈: {actor_feedback}")
    if actor_character:
        user_message_parts.append(f"演员角色: {actor_character}")
    if extra_context:
        user_message_parts.append(f"额外上下文: {extra_context}")
    user_message = "\n".join(user_message_parts)

    delegate_chapter_generation.log.info(
        "delegate_chapter_generation START: project_id=%s, source=%s, "
        "intervention=%s, actor_feedback=%s, actor_character=%s",
        project_id, source,
        bool(intervention), bool(actor_feedback), bool(actor_character),
    )

    writer = get_novel_writer()
    result = await writer.generate_chapter(
        project_id=project_id,
        user_message=user_message,
    )

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