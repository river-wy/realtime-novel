"""4 个专家 Agent（W1 stub）

对应 core.md §B.3
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SpecialistAgent(ABC):
    """专家 Agent 抽象"""

    name: str = ""

    @abstractmethod
    async def consult(self, context: dict) -> dict:
        """被 consult_experts_node 调用"""
        ...


class ChapterGeneratorStub(SpecialistAgent):
    """章节生成专家 stub"""

    name = "chapter_generator"

    async def consult(self, context: dict) -> dict:
        next_chapter = context.get("next_chapter_num", 1)
        return {
            "expert_name": self.name,
            "opinion": f"基于当前章节进度，建议下一步生成第{next_chapter}章",
            "confidence": 0.8,
            "suggested_actions": ["continue_plot", "develop_character"],
        }


class WorldTreeKeeperStub(SpecialistAgent):
    """世界书维护专家 stub"""

    name = "worldtree_keeper"

    async def consult(self, context: dict) -> dict:
        return {
            "expert_name": self.name,
            "opinion": "世界树暂无新增条目",
            "confidence": 0.9,
            "suggested_actions": [],
        }


class MemoryKeeperStub(SpecialistAgent):
    """记忆维护专家 stub"""

    name = "memory_keeper"

    async def consult(self, context: dict) -> dict:
        return {
            "expert_name": self.name,
            "opinion": "记忆系统中无相关历史",
            "confidence": 0.85,
            "suggested_actions": [],
        }


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
        """调 Gemini 文生图（v0.4 实际走 image_tool）"""
        from realtime_novel.adapters import get_llm_adapter
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
