"""novel_writer — 小说文笔家（v0.6.2 ReAct 化 + 委托入口）

v0.6.2 重构：
- 旧版：单次 LLM 调用 + 自己解析 final_response + 自己 fallback summary
- 新版：纯 ReAct loop, LLM 自主调工具（generate_chapter / summarize_chapter）落盘

职责（spec.md §3.2）：
1. 章节正文生成 + 落盘（generate_chapter 工具）
2. Summary 抽取（summarize_chapter 工具）
3. 文风控制（在 ReAct loop system_prompt 里约束）
4. 历史承接（build_messages_for_chapter_generator 注入 7 件 + chapter_summaries）

实现：文笔家所有能力都通过 ReAct loop 完成, LLM 自主决定调哪个 tool。
不直接调 specialist（specialists.py 已删除）。
外部入口（页面按钮 / Onboarding Step 5 / 管家 ReAct）通过
delegate_chapter_generation() 统一委托。

对应 spec.md §3.2
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
    # v0.6.2 新增: 落盘结果（从 generate_chapter 工具透传）
    chapter_num: Optional[int] = None
    title: Optional[str] = None
    word_count: Optional[int] = None


# ============ 系统提示 ============

NOVEL_WRITER_SYSTEM_PROMPT = """你是「小说文笔家」。

【职责】
在 7 件基座（world_tree / style_charter / genre_resonance / main_plot / sub_plots / character_card / seed_table）的约束下，生成下一章小说正文，并通过工具落盘。

【工作流】
1. system_prompt 已注入 7 件基座 + chapter_summaries 分级（20 章前 1 句，20 章内 detailed）+ history，不需要再调 load_project
2. 如有需要（如用户明确要求查某章详情），可调 search_memory / read_chapter 检索上下文
3. 写正文（3000-4500 字，遵守 style_charter 文风约束）
4. 调 generate_chapter(content=正文, project_id=xxx, intervention=?, actor_feedback=?, actor_character=?) 落盘
5. 调 summarize_chapter(content=正文, project_id=xxx) 抽 1 句话 summary（自动写入 DB）
6. final_response 是「已落盘第 N 章《XXX》, 摘要: ...」（不要把全文塞进 final_response）

【输出格式】
- 章节正文直接是小说文字（markdown 格式，包含 # 第 N 章标题）
- 章节正文里**不要**嵌入 ###SUMMARY### 块（summary 由 summarize_chapter 工具抽取，不靠 sentinel 解析）
- final_response 是一句话总结：「已落盘第 N 章《XXX》（X 字），摘要：...」

【关键约束】
- 严格遵守 7 件基座（角色设定、世界规则、文风约束）
- 修改基座前**不要直接调 edit_artifact/update_base** —— 这类操作属于架构师（world_tree_manager）职责，文笔家只读
- 不决定剧情走向（走向由世界树管理维护）
- 章节字数硬约束：3000-4500 字（按 style_charter 的 limits 调整 ±5%）

【上下文获取策略】
- 默认相信 system_prompt 注入的 7 件 + chapter_summaries，不要重复调 load_project
- 只在以下情况调 read_chapter：用户明确说「重读第 N 章」「参考第 N 章的风格」
- 只在以下情况调 search_memory：用户提到「之前写过类似的」「查询前几章埋的伏笔」
"""


# ============ NovelWriter 主类 ============

@logger_decorator
class NovelWriter:
    """小说文笔家（v0.6.2 ReAct 化）

    使用方式：
        writer = NovelWriter()
        output = await writer.generate_chapter(
            project_id="abc-123",
            user_message="继续写下一章",
        )

    v0.6.2 改造点：
    - 不再自己解析 final_response 中的正文 + summary
    - 让 LLM 在 ReAct loop 里调 generate_chapter / summarize_chapter 工具
    - 从 executor_output.structured_data 透传落盘结果
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        self.executor = executor or get_agent_executor()

    async def generate_chapter(
        self,
        project_id: str,
        user_message: str = "请生成下一章",
        max_iterations: int = 7,
    ) -> ChapterOutput:
        """生成下一章（v0.6.2 ReAct loop）

        Args:
            project_id: 项目 ID
            user_message: 用户提示（如「继续写下一章」「写主角遇到师父那一章」）
            max_iterations: ReAct loop 最大轮次（默认 7）

        Returns:
            ChapterOutput（含 chapter_content/summary/chapter_num/title/word_count/error）
        """
        self.log.info(
            "NovelWriter.generate_chapter START: project_id=%s, user_msg_len=%d, max_iterations=%d",
            project_id, len(user_message), max_iterations,
        )

        cfg = AgentConfig(
            agent_name="novel_writer",
            system_prompt=NOVEL_WRITER_SYSTEM_PROMPT,
        )

        executor_output = await self.executor.execute(
            agent=cfg,
            user_message=user_message,
            project_id=project_id,
            max_iterations=max_iterations,
        )

        # v0.6.2 改造: 不再自己解析 final_response
        # 落盘结果从 tool_calls_history 里找 generate_chapter 工具的结果
        # summary 从 tool_calls_history 里找 summarize_chapter 工具的结果
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

        # 兜底：如果 LLM 没调工具，final_response 也可能是章节正文（旧兼容路径）
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


# ============ 委托入口（统一给 3 个章节生成触发源用）============

@logger_decorator
async def delegate_chapter_generation(
    project_id: str,
    intervention: Optional[str] = None,
    actor_feedback: Optional[str] = None,
    actor_character: Optional[str] = None,
    source: str = "unknown",  # 标记来源：page_button / onboarding_step5 / steward_react / reactivation
    extra_context: Optional[str] = None,
) -> ChapterOutput:
    """章节生成委托入口（v0.6.2 统一入口）

    所有章节生成请求都通过这个入口走文笔家 ReAct loop，最终调 generate_chapter 工具落盘。

    Args:
        project_id: 项目 ID
        intervention: 用户对剧情的干预（可选）
        actor_feedback: 演员反馈（可选，未来用）
        actor_character: 演员扮演的角色（可选，未来用）
        source: 触发源标记（page_button / onboarding_step5 / steward_react / reactivation）
        extra_context: 额外上下文（可选）

    Returns:
        ChapterOutput（含 chapter_content/summary/chapter_num/title/word_count/error）

    调用方：
        - chapter_routes.py (POST /api/projects/{id}/chapters) → source="page_button"
        - services/onboarding_flow.py Step 5 → source="onboarding_step5"
        - delegation_tools.py _delegate_novel_writer → source="steward_react"
        - tools/onboarding_tools.py OnboardingGenerateChapterTool → source="onboarding_step5"
    """
    # 拼 user_message（context 是单一可信源）
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
        "delegate_chapter_generation DONE: project_id=%s, source=%s, "
        "chapter_num=%s, error=%s",
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