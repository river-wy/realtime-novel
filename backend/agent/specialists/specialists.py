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
import logging
from abc import ABC, abstractmethod

from backend.adapters.llm_adapter import get_llm_adapter
from backend.adapters.types import ModelRole
from backend.agent.specialists.chapter_summarizer import (
    extract_summary_from_llm_output,
    parse_chapter_summary,
)
from backend.agent.context import (
    build_messages_for_worldtree_keeper,
    build_messages_for_chapter_generator,
)
# 探索度工具函数：职责分离后统一在 agent.exploration
from backend.agent.specialists.exploration import (
    get_llm_params_for_project,
    fill_chapter_prompt_placeholders,
)
from backend.agent.prompts import (
    WORLDTREE_KEEPER_PROMPT,
    CHAPTER_GENERATOR_PROMPT,
    MEMORY_KEEPER_PROMPT,
)


# v0.6.1 P5: logger 在顶部定义 (state_graph_stub 原本有, 搬入时漏)
logger = logging.getLogger(__name__)


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


# ============ v0.6.1: chapter_via_specialist 包装（合并自 state_graph_stub）============

async def _generate_summary_via_llm(chapter_content: str, project_id: str) -> str | None:
    """当 sentinel 解析失败时，调 LLM 单独生成 2 句话概括

    v0.6.1: 从 state_graph_stub.py 移入 specialists.py
    """
    try:
        from backend.adapters import get_llm_adapter
        from backend.adapters.types import ModelRole

        adapter = get_llm_adapter()
        content_snippet = chapter_content[:3000]

        prompt = f"""请用两句话概括以下小说章节的核心故事发展（不是描述开头，而是概括整章的情节推进和关键事件）：

{content_snippet}

要求：
- 恰好两句话
- 概括整章最重要的情节推进，不是复述开头
- 简洁，~50-100 字
- 直接输出两句话，不要加任何前缀或解释"""

        response = await adapter.complete_with_messages(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="你是一个专业的小说内容编辑，擅长用简洁语言概括章节核心情节。",
            max_tokens=400,
            temperature=0.3,
            role=ModelRole.TEXT,
            enable_thinking=False,
        )
        summary = response.content.strip()
        if summary:
            logger.info(f"[{project_id}] sentinel 解析失败，LLM 补生成 summary 成功")
            return summary
    except Exception as e:
        logger.warning(f"[{project_id}] LLM fallback summary 生成失败: {e}")
    return None


async def generate_chapter_via_specialist(
    project_id: str,
    intervention: str | None = None,
    actor_feedback: str | None = None,
    actor_character: str | None = None,
) -> dict:
    """v0.6.1: 从 state_graph_stub.generate_chapter_via_state_graph 搬入

    完整流程（保留原 state_graph_stub 全部能力）:
    1. 拿当前章节数 → next_num
    2. 调 ChapterGeneratorSpecialist 生成章节 + summary
    3. sentinel 解析失败 → LLM 补 summary → 最后才截正文
    4. 写文件 + 入 DB
    5. 提取章节标题
    6. 返回完整结果
    """
    from backend.persistence import ChapterRepository
    from backend.persistence.project_repository import ProjectRepository

    _proj_repo = ProjectRepository()
    project_row = _proj_repo.get(project_id)
    if project_row is None:
        raise FileNotFoundError(f"Project not found: {project_id}")
    project = {"id": project_row.id, "name": project_row.name}

    chap_repo = ChapterRepository()
    existing_count = chap_repo.count_chapters(project_id)
    next_num = existing_count + 1

    # 1. 调 LLM（用 ChapterGeneratorSpecialist）
    specialist = ChapterGeneratorSpecialist()

    # 拼 user_message
    user_message_parts = [f"请生成第 {next_num} 章"]
    if intervention:
        user_message_parts.append(f"用户干预: {intervention}")
    if actor_feedback:
        user_message_parts.append(f"演员反馈: {actor_feedback}")
    if actor_character:
        user_message_parts.append(f"演员角色: {actor_character}")
    user_message = "\n".join(user_message_parts)

    result = await specialist.consult({
        "project_id": project_id,
        "user_message": user_message,
        "max_history": 5,
    })

    chapter_content = result.get("chapter_content", "")
    chapter_summary = result.get("chapter_summary")

    # 2. fallback: sentinel 解析失败 → 调 LLM 单独生成 → 最后才截正文
    if not chapter_summary and chapter_content:
        chapter_summary = await _generate_summary_via_llm(chapter_content, project_id)
    if not chapter_summary:
        chapter_summary = fallback_summary(chapter_content, max_chars=100)
    if not chapter_content:
        chapter_content = f"# 第 {next_num} 章\n\n（章节生成失败：{result.get('opinion', '未知错误')}）\n"

    # 3. 写文件
    from backend.config.config_loader import PROJECT_ROOT
    chapters_dir = PROJECT_ROOT / f"data/projects/{project_id}/chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    chapter_path = chapters_dir / f"chapter_{next_num:03d}.md"
    chapter_path.write_text(chapter_content, encoding="utf-8")

    # 3.5 提取章节标题
    chapter_title = f"第 {next_num} 章"
    for line in chapter_content.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            chapter_title = line[2:].strip()
            break

    # 4. 入 DB
    chap_repo.create(
        project_id=project_id,
        chapter_num=next_num,
        file_path=str(chapter_path),
        title=chapter_title,
        content_text=None,
        word_count=len(chapter_content),
        intervention=intervention,
        actor_feedback=actor_feedback,
        actor_character=actor_character,
        summary=chapter_summary,
    )

    return {
        "num": next_num,
        "title": chapter_title,
        "content": chapter_content,
        "file_path": str(chapter_path),
        "word_count": len(chapter_content),
        "summary": chapter_summary,
    }
