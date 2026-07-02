"""探索度（exploration_level）相关工具函数（从 specialists.py 提取）

这些函数属于通用 Agent 工具，不是某个 Specialist 特有的逻辑：
- get_llm_params_for_project: 按项目 exploration_level 返回 LLM 调用参数
- get_style_directive:        按 exploration_level 返回 prompt 创作风格指导
- fill_chapter_prompt_placeholders: 填充 CHAPTER_GENERATOR_PROMPT 的探索度占位符
"""
from __future__ import annotations


def get_llm_params_for_project(project_id: str, role: str = "chapter") -> dict:
    """按项目的 exploration_level 返回 LLM 调用参数

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
        "frequency_penalty": cfg.get("frequency_penalty", 0.0),
    }


def get_style_directive(level: str) -> str:
    """按 exploration_level 返回 prompt 创作风格指导段

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


def get_chapter_word_count_range(level: str) -> str:
    """从 agents.json 读 chapter_word_count，生成 ±5% 浮动范围字符串

    例: chapter_word_count=5000 → "4750-5250"
    fallback: 未配置时默认 5000 字
    """
    from backend.config import get_exploration_level_config
    try:
        cfg = get_exploration_level_config(level)
        target = int(cfg.get("chapter_word_count", 5000))
    except Exception:
        target = 5000
    low = int(target * 0.95)
    high = int(target * 1.05)
    return f"{low}-{high}"


def fill_chapter_prompt_placeholders(template: str, project_id: str) -> str:
    """填充 CHAPTER_GENERATOR_PROMPT 的探索度占位符 (按项目动态注入)

    占位符 (用 $ 前缀避免冲突):
    - $word_count_range: 字数范围，由 chapter_word_count ± 5% 生成（如 "4750-5250"）
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

    word_count_range = get_chapter_word_count_range(level)
    style_directive = get_style_directive(level)

    # string.Template 要求 $-placeholder，先把模板里的 {} 占位符替换为 $ 格式
    template_for_subst = template.replace("{word_count_range}", "$word_count_range") \
                                    .replace("{style_directive}", "$style_directive")
    return Template(template_for_subst).safe_substitute(
        word_count_range=word_count_range,
        style_directive=style_directive,
    )



# ============ 三级覆盖 exploration_level ============

def _resolve_exploration_level(
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """三级覆盖:
    1. projects.exploration_level (项目级, 最高优先级)
    2. user_preferences.default_exploration_level (用户级, 中间)
    3. agents.json exploration_levels.standard (硬默认, 最低)

    Args:
        project_id: 项目 ID (可能 None)
        user_id: 用户 ID (可能 None)
    """
    level: Optional[str] = None

    # 1. 项目级
    if project_id:
        try:
            from backend.persistence.project_repository import ProjectRepository
            project = ProjectRepository().get(project_id)
            if project and project.exploration_level:
                level = project.exploration_level
        except Exception:
            pass

    # 2. 用户级
    if not level and user_id:
        try:
            from backend.persistence.user_preference_repository import UserPreferenceRepository
            user_level = UserPreferenceRepository().get(user_id, "default_exploration_level")
            if user_level:
                level = user_level
        except Exception:
            pass

    # 3. 硬默认
    if not level:
        level = "standard"

    return level


def get_llm_params_for_chat(
    user_id: str,
    project_id: Optional[str] = None,
    role: str = "chat",
) -> dict:
    """管家 CHAT/ReAct 路径获取 LLM 参数

    按三级覆盖解析 exploration_level, 调 LLM 时统一参数。

    Args:
        user_id: 用户 ID (必填, 用于查 user_preferences)
        project_id: 项目 ID (可选, 用于查项目级 exploration_level)
        role: "chat" (管家对话) | "chapter" (章节生成) | ...

    Returns:
        {"temperature", "max_tokens", "frequency_penalty"}
    """
    from backend.config import get_exploration_level_config
    level = _resolve_exploration_level(project_id=project_id, user_id=user_id)
    cfg = get_exploration_level_config(level)
    return {
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "frequency_penalty": cfg.get("frequency_penalty", 0.0),
    }
