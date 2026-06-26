"""Tools 通用 Pydantic Schemas（13 个工具的 Input/Output）

对应 core.md §B.1.3
"""
from __future__ import annotations

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field


# ============ Project 工具 ============

class LoadProjectInput(BaseModel):
    project_id: str = Field(..., min_length=1)


class CreateProjectInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    # v0.7: palette 允许空（Onboarding Step 2 才会选）
    palette: str = Field(default="", min_length=0, max_length=500)
    # v0.8: 探索度旋钮 (conservative/standard/wild)
    exploration_level: Literal["conservative", "standard", "wild"] = Field(
        default="standard",
        description="探索度: conservative (严守) / standard (平衡) / wild (大胆)"
    )
    initial_prompt: Optional[str] = None


class DeleteProjectInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    confirm: Literal[True]  # 强制 True


class ProjectDetail(BaseModel):
    id: str
    name: str
    palette: str
    # v0.8: 探索度
    exploration_level: str = "standard"
    seven_artifacts: Optional[dict[str, Any]] = None
    world_tree: Optional[dict[str, Any]] = None
    chapters: Optional[list[dict]] = None


# ============ Chapter 工具 ============

class GenerateChapterInput(BaseModel):
    """v0.6.2 重构：LLM 在 ReAct loop 里写正文，工具只负责落盘
    
    - content: LLM 写的章节正文（3000-4500 字）
    - intervention/actor_feedback/actor_character: 用户干预信息（可选，写入 DB）
    """
    project_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=100, description="章节正文（LLM 写的 3000-4500 字）")
    intervention: Optional[str] = None
    actor_feedback: Optional[str] = None
    actor_character: Optional[str] = None


class ReadChapterInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    chapter_num: int = Field(..., ge=1)


class ChapterContent(BaseModel):
    num: int
    title: str
    content: str
    word_count: int
    generated_at: Optional[str] = None
    summary: Optional[str] = None  # v0.5 新增：1 句话 summary


# ============ v0.6.2: 章节总结工具（文笔家 ReAct 用）============

class SummarizeChapterInput(BaseModel):
    """章节总结工具输入
    
    - chapter_num: 章节号（写入日志用，可选）
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


# ============ Base Edit 工具（7 件基座）============

class UpdateBaseInput(BaseModel):
    """v0.4 兼容 API：整段写入

    v0.4.1 推荐改用 EditArtifactInput（结构化增删改）
    """
    project_id: str = Field(..., min_length=1)
    key: Literal["name", "palette", "world_tree", "main_plot", "style_charter", "seed_table", "genre_resonance", "character_card", "sub_plot"]
    new_value: str = Field(..., min_length=1)


class UpdateBaseResult(BaseModel):
    project_id: str
    key: str
    old_value_preview: str
    new_value_preview: str
    chapters_affected: list[int]


class EditArtifactInput(BaseModel):
    """v0.4.1 新增：结构化增量编辑（推荐使用）

    业务含义：
    - 管家 Agent 调 LLM 解析 user message → 调本工具
    - 不传整段 JSON，传结构化 diff（add/update/delete）
    - 工具内部做 Pydantic 校验 + DB 落盘

    优势：
    - 不会"忘了其他字段"（diff 友好）
    - LLM 不需要输出完整 YAML/JSON
    - 支持关系图操作（加关系、改弧光）
    """
    project_id: str = Field(..., min_length=1)
    target: Literal[
        "project_name", "project_palette", "current_pov",
        "character", "relationship", "core_rule",
        "timeline", "geography",
        "seed", "subplot", "beat",
    ]
    operation: Literal["add", "update", "delete"]
    identifier: Optional[str] = None  # update/delete 用（ID）
    data: Optional[dict] = None  # add/update 用（完整字段或 diff）


class EditArtifactResult(BaseModel):
    project_id: str
    target: str
    operation: str
    identifier: Optional[str] = None
    success: bool
    affected: Optional[dict] = None
    error: Optional[str] = None


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


# ============ Memory 工具（向量检索）============

class SearchMemoryInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class SearchMemoryResult(BaseModel):
    entries: list[dict[str, Any]]


# ============ v0.4 新工具（4 个）============

class AdjustStyleInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    style_directive: str = Field(..., min_length=1, max_length=500)


class AdjustStyleResult(BaseModel):
    project_id: str
    style_charter_updated: bool


class SwitchPovInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    new_pov_character: str = Field(..., min_length=1)


class SwitchPovResult(BaseModel):
    project_id: str
    previous_pov: str
    new_pov: str


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


# ============ v0.6.1: Onboarding 推进工具 (管家 ReAct 用) ============

class OnboardingProposeStepInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    step: int = Field(..., ge=1, le=5)
    user_response: Optional[str] = Field(default="")


class OnboardingProposeStepOutput(BaseModel):
    step: int
    proposed_fields: dict[str, Any] = Field(default_factory=dict)
    expected_user_input_hint: str = ""


class OnboardingUserConfirmInput(BaseModel):
    project_id: str = Field(..., min_length=1)
    step: int = Field(..., ge=1, le=5)
    user_response: str = Field(..., min_length=1)


class OnboardingUserConfirmOutput(BaseModel):
    step: int
    recorded: bool
    next_step: Optional[int] = None


class OnboardingGenerateChapterInput(BaseModel):
    project_id: str = Field(..., min_length=1)


class OnboardingGenerateChapterOutput(BaseModel):
    chapter_num: int
    title: str
    word_count: int
    summary: str = ""
    project_name: str = ""
