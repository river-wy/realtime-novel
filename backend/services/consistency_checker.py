"""consistency_checker — 一致性检查器（v003 重构为两阶段）

v003 重构（spec: .spec/db-refactor/spec.md §5.5）：
- 删 check() 旧方法（依赖已删除的 7 件基座快照）
- 新增 check_hard_rules() 阶段 1：硬约束违例扫描（致命可阻断）
- 新增 check_world_entries() 阶段 2：知识矛盾扫描（警告不阻断）

调用顺序：先 check_hard_rules 后 check_world_entries
"""
from __future__ import annotations

import logging
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from backend.persistence import ProjectRepository

log = logging.getLogger(__name__)


class HardRuleViolation(BaseModel):
    """硬约束违例（致命）"""
    rule_id: str
    rule_statement: str
    violation_type: str
    message: str
    related_char_id: Optional[str] = None
    related_text: Optional[str] = None


class WorldEntryConflict(BaseModel):
    """知识矛盾（警告）"""
    entry_id: str
    entry_title: str
    entry_content: str
    conflict_type: str
    message: str
    chapter_text_snippet: Optional[str] = None


class HardRuleViolationResult(BaseModel):
    """阶段 1 结果：硬约束违例"""
    violations: List[HardRuleViolation] = Field(default_factory=list)
    has_fatal: bool = False  # 是否有 fatal 违例（应阻断）


class WorldEntryConflictResult(BaseModel):
    """阶段 2 结果：知识矛盾"""
    conflicts: List[WorldEntryConflict] = Field(default_factory=list)
    has_warnings: bool = False


class ConsistencyChecker:
    """一致性检查器（v003 两阶段）

    阶段 1：check_hard_rules（致命可阻断）
    阶段 2：check_world_entries（警告不阻断）
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.repo = ProjectRepository()

    def check_hard_rules(
        self,
        chapter_text: str = "",
        character_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> HardRuleViolationResult:
        """阶段 1：硬约束违例扫描

        扫描 world_tree.core_rules_json 中 enforcement='hard' 的规则，
        对照章节文本和角色动作，输出违例列表。

        当前实现规则（占位）：
        - "无魔法" / "no magic" 硬约束 → 检测角色动作含魔法
        - "古代" / "架空" 时代硬约束 → 检测 speech_style 含现代网络词
        - "禁止穿越" / "no time travel" → 检测章节文本含穿越元素

        Args:
            chapter_text: 待检查的章节正文
            character_actions: 角色动作列表 [{"name": ..., "action": ...}]

        Returns:
            HardRuleViolationResult
        """
        violations: List[HardRuleViolation] = []
        core_rules = self.repo.get_core_rules(self.project_id) or []

        hard_rules = [r for r in core_rules if r.get("enforcement") == "hard"]
        if not hard_rules:
            return HardRuleViolationResult(violations=[], has_fatal=False)

        # 规则 1：no magic
        no_magic_rules = [r for r in hard_rules if "无魔法" in r.get("statement", "") or "no magic" in r.get("statement", "").lower()]
        if no_magic_rules:
            rule = no_magic_rules[0]
            for char_action in (character_actions or []):
                action = char_action.get("action", "")
                if "魔法" in action or "wizard" in action.lower() or "spell" in action.lower():
                    violations.append(HardRuleViolation(
                        rule_id=rule.get("id", ""),
                        rule_statement=rule.get("statement", ""),
                        violation_type="character_action_magic",
                        message=f"角色《{char_action.get('name', '?')}》使用魔法，但硬约束禁止魔法",
                        related_char_id=char_action.get("char_id"),
                        related_text=action,
                    ))
            # 章节文本扫描
            if chapter_text and ("魔法" in chapter_text or "spell" in chapter_text.lower()):
                violations.append(HardRuleViolation(
                    rule_id=rule.get("id", ""),
                    rule_statement=rule.get("statement", ""),
                    violation_type="chapter_contains_magic",
                    message="章节正文含魔法描写，但硬约束禁止魔法",
                    related_text=chapter_text[:100],
                ))

        # 规则 2：时代硬约束（古代/架空 → 禁止现代网络词）
        era_rules = [r for r in hard_rules if any(t in r.get("statement", "") for t in ["古代", "架空", "ancient", "fantasy"])]
        if era_rules:
            modern_terms = ["卧槽", "666", "哈哈哈", "OMG", "lol", "yyds"]
            for term in modern_terms:
                if term in chapter_text:
                    violations.append(HardRuleViolation(
                        rule_id=era_rules[0].get("id", ""),
                        rule_statement=era_rules[0].get("statement", ""),
                        violation_type="chapter_contains_modern_term",
                        message=f"章节正文含现代网络词「{term}」，与时代背景冲突",
                        related_text=chapter_text[:100],
                    ))
                    break  # 每个时代规则只报一次

        # 规则 3：禁止穿越
        no_tt_rules = [r for r in hard_rules if "禁止穿越" in r.get("statement", "") or "no time travel" in r.get("statement", "").lower()]
        if no_tt_rules and chapter_text and ("穿越" in chapter_text or "time travel" in chapter_text.lower()):
            violations.append(HardRuleViolation(
                rule_id=no_tt_rules[0].get("id", ""),
                rule_statement=no_tt_rules[0].get("statement", ""),
                violation_type="chapter_contains_time_travel",
                message="章节正文含穿越元素，但硬约束禁止穿越",
                related_text=chapter_text[:100],
            ))

        return HardRuleViolationResult(
            violations=violations,
            has_fatal=len(violations) > 0,
        )

    def check_world_entries(
        self,
        chapter_text: str = "",
        category: Optional[str] = None,
    ) -> WorldEntryConflictResult:
        """阶段 2：知识一致性扫描

        扫描 world_entries 表（按 category 可选过滤），
        检测章节文本与已知知识条目的矛盾（轻量字符串匹配）。

        Args:
            chapter_text: 待检查的章节正文
            category: 限定检查的 category（None = 全部）

        Returns:
            WorldEntryConflictResult
        """
        if not chapter_text:
            return WorldEntryConflictResult(conflicts=[], has_warnings=False)

        conflicts: List[WorldEntryConflict] = []
        world_entries = self.repo.list_world_entries(self.project_id, category=category)

        # 简化策略：对每条 world_entry.content 做关键词匹配
        # 实际 LLM-based 检查可后续扩展
        for entry in world_entries:
            content = entry.content
            if not content:
                continue

            # 检测"1 金 = 10 银" 这类数字关系
            if "=" in content and any(unit in content for unit in ["金", "银", "铜", "元", "币"]):
                # 提取数字关系
                import re
                match = re.search(r"(\d+)\s*([\u4e00-\u9fa5]+)\s*=\s*(\d+)\s*([\u4e00-\u9fa5]+)", content)
                if match:
                    num1, unit1, num2, unit2 = match.groups()
                    # 在 chapter_text 中查找相反关系
                    opposite = f"{num2}{unit2} = {num1}{unit1}"
                    if opposite in chapter_text:
                        conflicts.append(WorldEntryConflict(
                            entry_id=entry.id,
                            entry_title=entry.title,
                            entry_content=content,
                            conflict_type="currency_ratio_inverted",
                            message=f"章节描述「{opposite}」与知识条目《{entry.title}》矛盾",
                            chapter_text_snippet=chapter_text[:100],
                        ))

        return WorldEntryConflictResult(
            conflicts=conflicts,
            has_warnings=len(conflicts) > 0,
        )
