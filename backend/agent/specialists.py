"""3 个专家 Agent W2 真实实现（v0.5）

对应 core.md §B.3

v0.4: 4 个 stub（chapter_generator / worldtree_keeper / memory_keeper / image_generator）
v0.5: 3 个真实实现 + image_generator 仍 stub
- ChapterGeneratorSpecialist: 调 LLM 生成章节正文 + 同步抽 1 句 summary
- WorldTreeKeeperSpecialist: 调 LLM 管理世界树（返回结构化 diff）
- MemoryKeeperSpecialist: 调 LLM 检索历史记忆

3 个都是 stateless —— 每次 consult 重新拼 messages（不持久化专家 session）
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List

from backend.adapters.llm_adapter import get_llm_adapter
from backend.adapters.types import ModelRole
from backend.agent.prompts import (
    WORLDTREE_KEEPER_PROMPT,
    CHAPTER_GENERATOR_PROMPT,
    MEMORY_KEEPER_PROMPT,
    CHAPTER_SUMMARY_PROMPT,
    CHAPTER_DETAILED_SUMMARY_PROMPT,
    CONVERSATION_SUMMARY_PROMPT,
)


def get_llm_params_for_project(project_id: str, role: str = "chapter") -> dict:
    """v0.8: 按项目的 exploration_level 返回 LLM 调用参数

    Args:
        project_id: 项目 ID
        role: "chapter" (章节生成) | "worldtree" (世界树管理) | "memory" (记忆检索)
              不同 role 可有不同默认值 (暂统一用 exploration_level)

    Returns:
        {"temperature": float, "max_tokens": int} (暂不返 frequency_penalty,
        等 llm_adapter.complete_with_messages 扩展后再加 — TODO v0.8.1)
    """
    # 导入在函数内避免循环
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

    # string.Template 要求 $-placeholder, 先把 $word_count_range / $style_directive
    # 在原模板里出现的位置识别出来, 然后做 safe_substitute
    # 因为原模板里现在写的是 {word_count_range} 不是 $word_count_range, 临时改一下
    template_for_subst = template.replace("{word_count_range}", "$word_count_range") \
                                    .replace("{style_directive}", "$style_directive")
    return Template(template_for_subst).safe_substitute(
        word_count_range=word_count_range,
        style_directive=style_directive,
    )
from backend.agent.context_builder import (
    build_messages_for_worldtree_keeper,
    build_messages_for_chapter_generator,
)
from backend.agent.chapter_summarizer import (
    extract_summary_from_llm_output,
    parse_chapter_summary,
)


class SpecialistAgent(ABC):
    """专家 Agent 抽象"""
    name: str = ""

    @abstractmethod
    async def consult(self, context: dict) -> dict:
        ...


class ChapterGeneratorSpecialist(SpecialistAgent):
    """文笔家：调 LLM 生成章节正文 + 同步抽 1 句 summary

    接收 context:
    - project_id: 必填
    - user_message: 用户的章节要求
    - system_prompt: 可选 override（默认 CHAPTER_GENERATOR_PROMPT）

    返回:
    - expert_name
    - chapter_content: 正文（剥离 sentinel 块后）
    - chapter_summary: 1 句话 summary
    - opinion: 给管家的简短总结
    - suggested_actions
    """
    name = "chapter_generator"

    async def consult(self, context: dict) -> dict:
        project_id = context.get("project_id")
        if not project_id:
            return {
                "expert_name": self.name,
                "opinion": "缺少 project_id",
                "confidence": 0.0,
                "suggested_actions": [],
            }

        user_message = context.get("user_message", "请生成下一章")
        base_system_prompt = context.get("system_prompt") or CHAPTER_GENERATOR_PROMPT
        # v0.8: 按项目探索度填充 prompt 占位符
        system_prompt = fill_chapter_prompt_placeholders(base_system_prompt, project_id)

        # 拼 messages（按角色裁剪）
        messages = build_messages_for_chapter_generator(
            project_id=project_id,
            current_user_message=user_message,
            system_prompt=system_prompt,
            max_history=context.get("max_history", 5),
        )

        try:
            adapter = get_llm_adapter()
            # v0.8: 按项目 exploration_level 决定 LLM 参数 (conservative/standard/wild)
            llm_params = get_llm_params_for_project(project_id, role="chapter")
            # 把 system + data blocks 抽出来作为 system（节省 user 消息 token）
            response = await adapter.complete_with_messages(
                messages=[m for m in messages if m["role"] != "system"],
                system_prompt="\n\n".join([
                    m["content"] for m in messages if m["role"] == "system"
                ]),
                **llm_params,
                role=ModelRole.TEXT,
            )
            llm_output = response.content

            # 解析 sentinel 抽 summary
            chapter_summary = extract_summary_from_llm_output(llm_output)
            chapter_content = parse_chapter_summary(llm_output)

            return {
                "expert_name": self.name,
                "opinion": f"已生成下一章，summary: {chapter_summary[:50] if chapter_summary else '无'}",
                "confidence": 0.85,
                "suggested_actions": ["chapter_generated"],
                "chapter_content": chapter_content or llm_output,
                "chapter_summary": chapter_summary,
            }
        except Exception as e:
            return {
                "expert_name": self.name,
                "opinion": f"LLM 调用失败: {str(e)}",
                "confidence": 0.0,
                "suggested_actions": [],
            }


class WorldTreeKeeperSpecialist(SpecialistAgent):
    """架构师：调 LLM 管理世界树（返回结构化 diff）"""
    name = "worldtree_keeper"

    async def consult(self, context: dict) -> dict:
        project_id = context.get("project_id")
        if not project_id:
            return {
                "expert_name": self.name,
                "opinion": "缺少 project_id",
                "confidence": 0.0,
                "suggested_actions": [],
            }

        user_message = context.get("user_message", "请检查世界树")
        system_prompt = context.get("system_prompt") or WORLDTREE_KEEPER_PROMPT

        # 拼 messages
        messages = build_messages_for_worldtree_keeper(
            project_id=project_id,
            current_user_message=user_message,
            system_prompt=system_prompt,
            max_history=context.get("max_history", 5),
        )

        try:
            adapter = get_llm_adapter()
            # v0.8: 按项目 exploration_level 决定 LLM 参数
            llm_params = get_llm_params_for_project(project_id, role="worldtree")
            response = await adapter.complete_with_messages(
                messages=[m for m in messages if m["role"] != "system"],
                system_prompt="\n\n".join([
                    m["content"] for m in messages if m["role"] == "system"
                ]),
                **llm_params,
                role=ModelRole.TEXT,
            )
            llm_output = response.content

            # 尝试解析 JSON（LLM 可能返回 JSON 格式的 diff）
            parsed = None
            try:
                # 找 ```json ... ``` 块
                import re
                json_match = re.search(r"```json\s*\n?(.*?)\n?```", llm_output, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(1))
                else:
                    parsed = json.loads(llm_output)
            except Exception:
                parsed = {"action": "view", "response": llm_output[:500]}

            return {
                "expert_name": self.name,
                "opinion": parsed.get("response", llm_output[:200]),
                "confidence": 0.8,
                "suggested_actions": ["worldtree_analyzed"],
                "diff": parsed.get("diff", []),
                "action": parsed.get("action", "view"),
            }
        except Exception as e:
            return {
                "expert_name": self.name,
                "opinion": f"LLM 调用失败: {str(e)}",
                "confidence": 0.0,
                "suggested_actions": [],
            }


class MemoryKeeperSpecialist(SpecialistAgent):
    """记忆维护者：调 LLM 检索历史记忆"""
    name = "memory_keeper"

    async def consult(self, context: dict) -> dict:
        user_message = context.get("user_message", "")
        keywords = context.get("keywords", [])
        history = context.get("history_messages", [])

        # 拼 messages
        sys_prompt = MEMORY_KEEPER_PROMPT.format(
            user_message=user_message,
            keywords=", ".join(keywords) if keywords else "(无)",
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            *history,
        ]

        try:
            adapter = get_llm_adapter()
            # v0.8: MemoryKeeper 跨项目检索, 不绑 exploration_level (保持稳定)
            response = await adapter.complete_with_messages(
                messages=[m for m in messages if m["role"] != "system"],
                system_prompt=sys_prompt,
                max_tokens=1000,
                temperature=0.3,
                role=ModelRole.TEXT,
            )
            return {
                "expert_name": self.name,
                "opinion": response.content[:200],
                "confidence": 0.75,
                "suggested_actions": ["memory_retrieved"],
                "relevant_memories": [],
                "summary": response.content,
            }
        except Exception as e:
            return {
                "expert_name": self.name,
                "opinion": f"LLM 调用失败: {str(e)}",
                "confidence": 0.0,
                "suggested_actions": [],
            }


# ============ 兼容旧 stub 名（v0.4 → v0.5 过渡）============

# 别名：让旧 import 仍可用
ChapterGeneratorStub = ChapterGeneratorSpecialist
WorldTreeKeeperStub = WorldTreeKeeperSpecialist
MemoryKeeperStub = MemoryKeeperSpecialist


# ============ Image Generator 仍 stub（v0.5 不变）============

class ImageGeneratorStub(SpecialistAgent):
    """立绘生成专家 stub（实际调 Gemini）"""
    name = "image_generator"

    async def consult(self, context: dict) -> dict:
        return {
            "expert_name": self.name,
            "opinion": "image generation handled by generate_image tool",
            "confidence": 1.0,
            "suggested_actions": [],
        }

    async def generate_image(self, project_id: str, style_hint: str | None = None) -> dict:
        from backend.adapters import get_llm_adapter
        adapter = get_llm_adapter()
        prompt = f"为小说项目 {project_id} 生成主立绘"
        if style_hint:
            prompt += f"，风格：{style_hint}"
        try:
            result = await adapter.generate_image(prompt=prompt)
            return {
                "image_urls": result.get("image_urls", []),
                "description": result.get("description", ""),
            }
        except Exception as e:
            return {"error": str(e), "image_urls": []}
