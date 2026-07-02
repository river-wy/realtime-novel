"""Tools 通用 Pydantic Schemas（工具的 Input/Output）"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal, Optional, Any, List


# ============ Project 工具 ============

class LoadProjectInput(BaseModel):
    project_id: str = Field(..., min_length=1)


class CreateProjectInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    exploration_level: Literal["conservative", "standard", "wild"] = Field(
        default="standard",
        description="探索度: conservative (严守) / standard (平衡) / wild (大胆)"
    )
    initial_prompt: Optional[str] = None
    style_pack_id: Optional[str] = Field(
        default=None,
        description="写作笔风 ID（如 yanhuo_shiyi / xianxia_ranhuo），不传则 onboarding 后再设置"
    )


class DeleteProjectInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    confirm: Literal[True]


class ProjectDetail(BaseModel):
    id: str
    name: str
    exploration_level: str = "standard"
    seven_artifacts: Optional[dict[str, Any]] = None
    world_tree: Optional[dict[str, Any]] = None
    chapters: Optional[list[dict]] = None


# ============ Chapter 工具 ============

class GenerateChapterInput(BaseModel):
    """LLM 在 ReAct loop 里写正文，工具只负责落盘

    - content: LLM 写的章节正文（3000-4500 字）
    - intervention: 用户干预信息（可选，写入 DB）

    v003：删 actor_feedback / actor_character
    """
    project_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=100, description="章节正文（3000-4500 字）")
    intervention: Optional[str] = None


class ReadChapterInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    chapter_num: int = Field(..., ge=1)


class ChapterContent(BaseModel):
    num: int
    title: str
    content: str
    word_count: int
    generated_at: Optional[str] = None
    summary: Optional[str] = None


# ============ 章节总结工具 ============

class SummarizeChapterInput(BaseModel):
    """章节总结工具输入
    
    - chapter_num: 章节号（日志用，可选）
    - content: 章节正文（>= 100 字）
    """
    project_id: str = Field(..., min_length=1)
    chapter_num: Optional[int] = Field(default=None, ge=1, description="章节号（日志用）")
    content: str = Field(..., min_length=100, description="章节正文")


class SummarizeChapterOutput(BaseModel):
    """章节总结工具输出
    
    - summary: 1 句话总结（~50-100 字）
    - method: 解析方式（sentinel / fallback_truncate / llm_fallback）
    """
    summary: str = Field(..., description="1 句话总结（~50-100 字）")
    method: str = Field(default="sentinel", description="sentinel / fallback_truncate / llm_fallback")


# ============ 卷总结工具 ============

class GenerateVolumeSummaryInput(BaseModel):
    """卷总结工具输入

    - 章节写完时，文笔家 LLM 调本工具生成卷的 1000 字总结
    - volume_id 必填（文笔家应从上下文拿）
    - auto_complete_volume=False：只生成 summary，保留 status=in_progress
    - auto_complete_volume=True：生成 summary + 改 status=completed（**双向走热路径**）
    """
    project_id: str = Field(..., min_length=1)
    volume_id: str = Field(..., min_length=1)
    auto_complete_volume: bool = Field(
        default=False,
        description="是否同时完结卷（仅在本卷所有章节都生成完时为 True）",
    )


class GenerateVolumeSummaryOutput(BaseModel):
    """卷总结工具输出"""
    volume_id: str = Field(..., description="卷 ID")
    summary: str = Field(..., description="1000 字总结（800-1200 字）")
    summary_len: int = Field(..., description="总结字数")
    auto_completed: bool = Field(default=False, description="是否同时完结了卷")
    status: str = Field(default="in_progress", description="卷最终状态")


# ============ Base Edit 工具（6 件基座）============

class UpdateBaseInput(BaseModel):
    """整段写入（兼容旧 API）"""
    project_id: str = Field(..., min_length=1)
    key: Literal["name", "world_tree", "main_plot", "style_pack", "seed_table", "genre_resonance", "character_card", "sub_plot"]
    new_value: str = Field(..., min_length=1)


class UpdateBaseResult(BaseModel):
    project_id: str
    key: str
    old_value_preview: str
    new_value_preview: str
    chapters_affected: list[int]


class EditArtifactInput(BaseModel):
    """结构化增量编辑 6 件基座

    管家 Agent 解析 user message → 调本工具（add/update/delete）。
    不传整段 JSON，传结构化 diff，工具内部做 Pydantic 校验 + DB 落盘。
    """
    project_id: str = Field(..., min_length=1)
    target: Literal[
        "project_name", "current_pov",
        "character", "relationship", "core_rule",
        "timeline_event", "geography_location", "world_entry",
        "seed", "subplot", "main_plot_node", "volume",
        "beat",                # _edit_beat 之前是死代码，现在加进 Literal
    ]
    operation: Literal["add", "update", "delete"]
    identifier: Optional[str] = None  # update/delete 用（ID）
    data: Optional[dict] = None       # add/update 用（完整字段或 diff）


class EditArtifactResult(BaseModel):
    project_id: str
    target: str
    operation: str
    identifier: Optional[str] = None
    success: bool
    affected: Optional[dict] = None
    error: Optional[str] = None


class EditArtifactItem(BaseModel):
    """批量编辑单项"""
    target: Literal[
        "project_name", "current_pov",
        "character", "relationship", "core_rule",
        "timeline_event", "geography_location", "world_entry",
        "seed", "subplot", "main_plot_node", "volume",
        "beat",                # _edit_beat 之前是死代码，现在加进 Literal
    ]
    operation: Literal["add", "update", "delete"]
    identifier: Optional[str] = None  # update/delete 用（ID）
    data: Optional[dict] = None       # add/update 用（完整字段或 diff）


class EditArtifactBatchInput(BaseModel):
    """批量结构化编辑 9 件基座

    优势：
    - 1 次 tool_call 落库 N 行（vs N 次 edit_artifact）
    - 事务：全部成功才 commit，任一失败全回滚
    - 性能：WTM ReAct 落库 9 张表从「N round-trip」→「1 round-trip」
    """
    project_id: str = Field(..., min_length=1)
    items: List[EditArtifactItem] = Field(..., min_length=1, max_length=50)
    atomic: bool = Field(
        default=True,
        description="事务模式：true=全部成功才 commit（任一失败全回滚）；false=逐项提交",
    )


class EditArtifactBatchResult(BaseModel):
    """批量编辑结果"""
    project_id: str
    total: int
    success_count: int
    failed_count: int
    results: List[EditArtifactResult] = Field(default_factory=list)
    # 失败项索引（atomic=False 时记录，atomic=True 时最多 1 个就全回滚）
    failed_indices: List[int] = Field(default_factory=list)
    # 失败时已回滚的所有 row_id（atomic=True 用，WTM 可用这些 row_id 二次清理）
    rolled_back_ids: List[dict] = Field(default_factory=list)


class RollbackBaseInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    to_chapter: int = Field(..., ge=1)
    confirm: Literal[True]


# ============ Image 工具 ============

class GenerateImageInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    style_hint: Optional[str] = None


class ImageResult(BaseModel):
    project_id: str
    image_url: str
    generated_at: str
    cache_hit: bool = False


# ============ Memory 工具 ============

class SearchMemoryInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class SearchMemoryResult(BaseModel):
    entries: list[dict[str, Any]]


# ============ Style / POV 工具 ============

class AdjustStyleInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    style_pack_id: str = Field(..., min_length=1, max_length=500)


class AdjustStyleResult(BaseModel):
    project_id: str
    style_pack_updated: bool


class SwitchPovInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    new_pov_char_id: str = Field(..., min_length=1, description="目标 POV 角色的 char_id（格式: char-xxxxxxxx）")


class SwitchPovResult(BaseModel):
    project_id: str
    previous_pov_char_id: str  # 前一个 POV char_id（空字符串=未设置）
    new_pov_char_id: str
    new_pov_name: str          # 方便 LLM 输出


class IntrospectCharacterInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    character_name: str = Field(..., min_length=1)


class IntrospectResult(BaseModel):
    character_name: str
    character_card: dict[str, Any]
    inner_monologue: Optional[str] = None


class WeavePlotInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    plot_seed: str = Field(..., min_length=1)


class WeavePlotResult(BaseModel):
    next_chapter_plan: dict[str, Any]



# ============ Onboarding 工具（v003 委托模式）============
# v003 变更（2026-07-01 完整删除旧 5 步工具）：
# - 旧 6 个 schema（OnboardingProposeStep/UserConfirm/GenerateChapter × 2）已删
# - 新 schema 集中在 onboarding_tools.py 顶部（DelegateToWTMInput/Output / VerifyWorldTreeBaselineInput/Output）

