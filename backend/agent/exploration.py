"""探索度（exploration_level）相关工具函数（从 specialists.py 提取）

这些函数属于通用 Agent 工具，不是某个 Specialist 特有的逻辑：
- get_llm_params_for_project: 按项目 exploration_level 返回 LLM 调用参数
- get_style_directive:        按 exploration_level 返回 prompt 创作风格指导
- fill_chapter_prompt_placeholders: 填充 CHAPTER_GENERATOR_PROMPT 的探索度占位符
"""
from __future__ import annotations


def get_llm_params_for_project(project_id: str, role: str = "chapter") -> dict:
    """v0.8: 按项目的 exploration_level 返回 LLM 调用参数

    Args:
        project_id: 项目 ID
        role: "chapter" (章节生成) | "worldtree" (世界树管理) | "memory" (记忆检索)
              不同 role 可有不同默认值 (暂统一用 exploration_level)

    Returns:
        {"temperature": float, "max_tokens": int, "frequency_penalty": float}
    """
    from backend.persistence.project_repository import ProjectRepository
    from backend.config import get_exploration_level_config

    repo = ProjectRepository()
    project = repo.get(project_id)
    level = project.exploration_level if project else "standard"
    cfg = get_exploration_level_config(level)
    return {
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        # v0.8.1: 透传 frequency_penalty (探索度 wild 档减少重复用词)
        "frequency_penalty": cfg.get("frequency_penalty", 0.0),
    }


def get_style_directive(level: str) -> str:
    """v0.8: 按 exploration_level 返回 prompt 创作风格指导段

    - conservative: 严守用户输入, 不自由发挥
    - standard:     合理补充
    - wild:         鼓励扩展篇幅, 添细节, 探索不同方向
    """
    directives = {
        "conservative": (
            "- 严守世界树基座, 不偏离用户设定\n"
            "- 字数严格控制, 不超不欠\n"
            "- AI 补充范围 限, 只在用户设定上微调"
        ),
        "standard": (
            "- 遵守世界树基座\n"
            "- 字数控制 + AI 可合理补充 1-2 处细节 (人物动作/环境描写)\n"
            "- 保持故事连贯性优先"
        ),
        "wild": (
            "- 大胆探索: 在世界树框架内鼓励不同表述/节奏/视角\n"
            "- 鼓励篇幅扩展: 字数可超上限 20%, 通过细腻描写/多场景/多角色心理展开\n"
            "- 添加 1-2 个用户没明说的细节 (如某个角色的小习惯/某个物件的来历/一段不重要的往事)\n"
            "- 探索性 > 准确性: 尝试不同的开篇/收尾/节奏, 给用户横向比较"
        ),
    }
    return directives.get(level, directives["standard"])


def fill_chapter_prompt_placeholders(template: str, project_id: str) -> str:
    """v0.8: 填充 CHAPTER_GENERATOR_PROMPT 的探索度占位符 (按项目动态注入)

    v0.8.1: 用 string.Template ($-placeholder) 避免和 {world_tree}/{chapter_summaries}
    等其他 {}-placeholder 冲突。

    占位符 (用 $ 前缀避免冲突):
    - $word_count_range: 字数范围 (conservative=2000-2500, standard=2000-3000, wild=2500-3500)
    - $style_directive:   创作风格指导 (按 level)

    如果 template 不含占位符 (用户自定义 system_prompt), 原样返回。
    """
    from string import Template
    from backend.persistence.project_repository import ProjectRepository

    if "{word_count_range}" not in template and "{style_directive}" not in template:
        return template

    repo = ProjectRepository()
    project = repo.get(project_id)
    level = project.exploration_level if project else "standard"

    word_count_map = {
        "conservative": "2000-2500",
        "standard": "2000-3000",
        "wild": "2500-3500",
    }
    word_count_range = word_count_map.get(level, "2000-3000")
    style_directive = get_style_directive(level)

    # string.Template 要求 $-placeholder，先把模板里的 {} 占位符替换为 $ 格式
    template_for_subst = template.replace("{word_count_range}", "$word_count_range") \
                                    .replace("{style_directive}", "$style_directive")
    return Template(template_for_subst).safe_substitute(
        word_count_range=word_count_range,
        style_directive=style_directive,
    )

