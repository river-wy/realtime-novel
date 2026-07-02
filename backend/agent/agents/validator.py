"""Validator — 校验 Agent

职责：
- 世界树基座一致性校验（WTM 落库后调）
- 章节内容合理性校验（文笔家生成后调）

设计：
- 走 ReAct loop（executor.execute）—— Validator 自己调工具读表
- 引入 session cache（按 project + kind 维度）
- 不支持 delegate_to_agent（避免元循环）
- 校验范围：全覆盖所有基座（7 大类）
- 不落库 / 不改基座 —— 职责是审判

链路：
- WTM.analyze_intervention 落库后调 Validator.validate_world_tree
- WTM.run_initial_baseline_react 落库后调 Validator.validate_world_tree
- novel_writer.delegate_chapter_generation 生成后调 Validator.validate_chapter
"""
from __future__ import annotations

import json
import logging
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# ============ 枚举 ============

class ValidationSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class ValidationStatus(str, Enum):
    """基座校验 status（4 档）"""
    PASS = "PASS"
    WARN = "WARN"
    BLOCKED = "BLOCKED"
    FATAL = "FATAL"


class ChapterValidationStatus(str, Enum):
    """章节校验 status（3 档）"""
    PASS = "PASS"
    WARN = "WARN"
    BLOCKED = "BLOCKED"


# ============ 数据模型 ============

class ValidationIssue(BaseModel):
    """校验问题"""
    severity: ValidationSeverity
    table: str = Field(..., description="哪张表")
    field: str = Field(..., description="哪个字段")
    description: str = Field(..., description="问题描述")
    evidence_old: str = Field(default="", description="旧数据引用")
    evidence_new: str = Field(default="", description="新数据引用")
    suggested_fix: Optional[str] = Field(default=None, description="建议怎么改")


class ValidationResult(BaseModel):
    """基座校验结果（4 档 status）"""
    status: ValidationStatus
    issues: List[ValidationIssue] = Field(default_factory=list)
    summary: str = Field(default="", description="一句话总结")


class ChapterValidationResult(BaseModel):
    """章节校验结果（3 档 status）"""
    status: ChapterValidationStatus
    issues: List[ValidationIssue] = Field(default_factory=list)
    blocked_paragraphs: List[int] = Field(
        default_factory=list,
        description="BLOCKED 时的问题段号",
    )


# ============ Validator 类 ============

class Validator:
    """校验 Agent
    
    走 ReAct loop + 自己的 session cache
    校验范围：全覆盖所有基座
    """
    
    def __init__(self, executor=None):
        from backend.agent.runtime.executor import get_agent_executor
        self.executor = executor or get_agent_executor()
        self.log = log
    
    def _session_key(self, project_id: str, kind: str) -> str:
        """构造 session_key（按 project + kind 维度）
        
        跟 WTM/文笔家对齐：f"{project_id}:{agent_name}:{kind}"
        Validator 的 agent_name 是 validator
        """
        return f"{project_id}:validator:{kind}"
    
    # ── 入口 1：基座校验 ─────────────────────────────────
    
    async def validate_world_tree(
        self,
        project_id: str,
        user_intent: str,         # intervention_text 或 steward_payload JSON
    ) -> ValidationResult:
        """校验 WTM 落库后的基座一致性
        
        流程：
        1. 构造 system_prompt（覆盖 7 大类基座）
        2. 构造 context_message（project_id + user_intent）
        3. executor.execute() 走 ReAct loop
        4. Validator LLM 自己调 load_project + read_chapter 读时间线/人物/世界观
        5. 解析 final_response 为 ValidationResult
        """
        from backend.agent.prompts.agent_prompt_factory import build_validator_system_prompt
        from backend.agent.runtime.executor import AgentConfig
        
        self.log.info(
            "Validator.validate_world_tree START: project_id=%s, user_intent_len=%d",
            project_id, len(user_intent),
        )
        
        # 1. 构造 system_prompt
        system_prompt = build_validator_system_prompt(kind="world_tree")
        
        # 2. 构造 context_message
        context_message = (
            f"【项目 ID】\n{project_id}\n\n"
            f"【用户原始意图】\n{user_intent}\n\n"
            f"【请你】通过 ReAct loop 自主调工具（load_project / read_chapter）"
            f"读取项目所有基座数据，按 system_prompt 教的全覆盖 7 大类规则校验，"
            f"输出 JSON 格式 ValidationResult。\n"
        )
        
        # 3. 构造 user_message
        user_message = (
            "请校验世界树基座一致性。你有 ReAct loop + session cache，"
            "可以自己调 load_project 读项目、调 read_chapter 读已有章节。"
            "校验完输出 JSON: {\"status\": \"PASS|WARN|BLOCKED|FATAL\", "
            "\"issues\": [...], \"summary\": \"...\"}"
        )
        
        cfg = AgentConfig(
            agent_name="validator_world_tree",
            system_prompt=system_prompt,
        )
        
        # 4. 走 ReAct loop
        try:
            executor_output = await self.executor.execute(
                agent=cfg,
                user_message=user_message,
                project_id=project_id,
                context_message=context_message,
                session_key=self._session_key(project_id, "world_tree"),
                max_iterations=15,
            )
        except Exception as e:
            self.log.exception("Validator.validate_world_tree executor FAILED: %s", e)
            return ValidationResult(
                status=ValidationStatus.WARN,
                issues=[],
                summary=f"Validator 执行失败: {e}",
            )
        
        self.log.info(
            "Validator.validate_world_tree EXECUTOR DONE: project_id=%s, "
            "iterations=%d, tool_calls=%d, error=%s",
            project_id, executor_output.iterations,
            len(executor_output.tool_calls_history),
            executor_output.error,
        )
        
        if executor_output.error:
            return ValidationResult(
                status=ValidationStatus.WARN,
                issues=[],
                summary=f"Validator executor 报错: {executor_output.error}",
            )
        
        # 5. 解析 final_response
        return self._parse_validation_response(executor_output.final_response)
    
    # ── 入口 2：章节校验 ─────────────────────────────────
    
    async def validate_chapter(
        self,
        project_id: str,
        chapter_content: str,
        chapter_num: int,
    ) -> ChapterValidationResult:
        """校验章节内容合理性
        
        流程同 validate_world_tree，但校验身份段不同
        """
        from backend.agent.prompts.agent_prompt_factory import build_validator_system_prompt
        from backend.agent.runtime.executor import AgentConfig
        
        self.log.info(
            "Validator.validate_chapter START: project_id=%s, chapter_num=%d, content_len=%d",
            project_id, chapter_num, len(chapter_content),
        )
        
        # 1. 构造 system_prompt
        system_prompt = build_validator_system_prompt(kind="chapter")
        
        # 2. 构造 context_message
        context_message = (
            f"【项目 ID】\n{project_id}\n\n"
            f"【章节号】{chapter_num}\n\n"
            f"【章节内容】\n{chapter_content}\n\n"
            f"【请你】通过 ReAct loop 自主调工具读取相关基座数据，"
            f"校验章节内容合理性。\n"
        )
        
        # 3. 构造 user_message
        user_message = (
            f"请校验第 {chapter_num} 章内容合理性。ReAct loop + session cache，"
            f"自己调 load_project 读基座、调 read_chapter 读已有章节。"
            f"输出 JSON: {{\"status\": \"PASS|WARN|BLOCKED\", "
            f"\"issues\": [...], \"blocked_paragraphs\": [段号]}}"
        )
        
        cfg = AgentConfig(
            agent_name="validator_chapter",
            system_prompt=system_prompt,
        )
        
        # 4. 走 ReAct loop
        try:
            executor_output = await self.executor.execute(
                agent=cfg,
                user_message=user_message,
                project_id=project_id,
                context_message=context_message,
                session_key=self._session_key(project_id, "chapter"),
                max_iterations=15,
            )
        except Exception as e:
            self.log.exception("Validator.validate_chapter executor FAILED: %s", e)
            return ChapterValidationResult(
                status=ChapterValidationStatus.WARN,
                issues=[],
                blocked_paragraphs=[],
            )
        
        self.log.info(
            "Validator.validate_chapter EXECUTOR DONE: project_id=%s, chapter=%d, "
            "iterations=%d, tool_calls=%d, error=%s",
            project_id, chapter_num, executor_output.iterations,
            len(executor_output.tool_calls_history),
            executor_output.error,
        )
        
        if executor_output.error:
            return ChapterValidationResult(
                status=ChapterValidationStatus.WARN,
                issues=[],
                blocked_paragraphs=[],
            )
        
        return self._parse_chapter_validation_response(executor_output.final_response)
    
    # ── 解析器 ──────────────────────────────────────────
    
    def _parse_validation_response(self, final: str) -> ValidationResult:
        """解析 LLM final_response 为 ValidationResult"""
        parsed = self._try_parse_json(final)
        if parsed is None:
            return ValidationResult(
                status=ValidationStatus.WARN,
                issues=[],
                summary=f"Validator LLM 输出无法解析: {final[:100]}",
            )
        
        # status
        try:
            status = ValidationStatus(parsed.get("status", "WARN"))
        except ValueError:
            status = ValidationStatus.WARN
        
        # issues
        issues = []
        for issue_data in parsed.get("issues", []):
            try:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity(issue_data.get("severity", "warning")),
                    table=issue_data.get("table", ""),
                    field=issue_data.get("field", ""),
                    description=issue_data.get("description", ""),
                    evidence_old=issue_data.get("evidence_old", ""),
                    evidence_new=issue_data.get("evidence_new", ""),
                    suggested_fix=issue_data.get("suggested_fix"),
                ))
            except Exception as e:
                self.log.warning(f"Validator 解析 issue 失败: {e}")
        
        return ValidationResult(
            status=status,
            issues=issues,
            summary=parsed.get("summary", ""),
        )
    
    def _parse_chapter_validation_response(self, final: str) -> ChapterValidationResult:
        """解析 LLM final_response 为 ChapterValidationResult"""
        parsed = self._try_parse_json(final)
        if parsed is None:
            return ChapterValidationResult(
                status=ChapterValidationStatus.WARN,
                issues=[],
                blocked_paragraphs=[],
            )
        
        # status
        try:
            status = ChapterValidationStatus(parsed.get("status", "WARN"))
        except ValueError:
            status = ChapterValidationStatus.WARN
        
        # issues
        issues = []
        for issue_data in parsed.get("issues", []):
            try:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity(issue_data.get("severity", "warning")),
                    table=issue_data.get("table", ""),
                    field=issue_data.get("field", ""),
                    description=issue_data.get("description", ""),
                    evidence_old=issue_data.get("evidence_old", ""),
                    evidence_new=issue_data.get("evidence_new", ""),
                    suggested_fix=issue_data.get("suggested_fix"),
                ))
            except Exception as e:
                self.log.warning(f"Validator 解析 issue 失败: {e}")
        
        # blocked_paragraphs
        blocked = parsed.get("blocked_paragraphs", [])
        if not isinstance(blocked, list):
            blocked = []
        blocked_ints = []
        for p in blocked:
            try:
                blocked_ints.append(int(p))
            except (ValueError, TypeError):
                pass
        
        return ChapterValidationResult(
            status=status,
            issues=issues,
            blocked_paragraphs=blocked_ints,
        )
    
    @staticmethod
    def _try_parse_json(text: str) -> Optional[Dict]:
        """尝试多种方式解析 JSON
        1. 直接 parse
        2. 去掉 markdown 包裹
        3. 提取 {...}
        """
        text = text.strip()
        # 1. 直接 parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 2. 去掉 markdown 包裹
        if text.startswith("```"):
            for chunk in text.split("```"):
                chunk = chunk.strip()
                if chunk.startswith("json"):
                    chunk = chunk[4:].strip()
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    continue
        # 3. 提取 {...}
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break
        return None


# ============ 单例 ============

_validator_instance: Optional[Validator] = None


def get_validator() -> Validator:
    """获取单例 Validator"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = Validator()
    return _validator_instance
