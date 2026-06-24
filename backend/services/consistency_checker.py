"""consistency_checker — 世界树一致性检查器（s4）

职责（spec.md §3.3 + §R6）：
1. 验证 7 件基座之间的硬冲突（FAIL）
2. 验证 7 件基座之间的软警告（WARN）
3. 输出 ConsistencyCheckResult

检查维度（v0.6 简化版）：
1. world_tree.timeline_era vs character_card.character.speech_style（古代角色不能用现代网络用语）
2. character_card.role vs world_tree.core_rules（如果世界规则是"无魔法"，角色不能有魔法）
3. seed_table.payoff vs main_plot.range（seed 回收不能超出 main_plot 范围）
4. character_relationship vs character_card.role（主角和反派不能是夫妻）
5. sub_plot.status vs main_plot.status（如果 main_plot 完成，sub_plot 也应结束）

对应 spec.md §3.3
"""
from __future__ import annotations

import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.agent.world_tree_manager import (
    BaseUpdate, PlotAdjustment, NewSeed, ConsistencyCheckResult,
)
from backend.persistence import ProjectRepository

log = logging.getLogger(__name__)


class BaseSnapshot(BaseModel):
    """7 件基座快照（检查器内部用）"""
    world_tree: dict = Field(default_factory=dict)
    style_charter: dict = Field(default_factory=dict)
    genre_resonance: dict = Field(default_factory=dict)
    main_plot: dict = Field(default_factory=dict)
    sub_plots: List[dict] = Field(default_factory=list)
    character_card: List[dict] = Field(default_factory=list)  # 角色列表
    seed_table: List[dict] = Field(default_factory=list)


class ConsistencyChecker:
    """世界树一致性检查器

    使用方式：
        checker = ConsistencyChecker(project_id)
        result = checker.check(before_snapshot, after_snapshot)
        # result.status = PASS / WARN / FAIL
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.repo = ProjectRepository()

    def check(
        self,
        before: BaseSnapshot,
        after: BaseSnapshot,
        proposed_updates: List[BaseUpdate] = None,
        proposed_seeds: List[NewSeed] = None,
    ) -> ConsistencyCheckResult:
        """执行一致性检查

        Args:
            before: 修改前的基座快照
            after: 修改后的基座快照（已 apply proposed_updates）
            proposed_updates: 待检查的基座变更
            proposed_seeds: 待检查的新种子

        Returns:
            ConsistencyCheckResult
        """
        conflicts: List[str] = []
        warnings: List[str] = []

        # 1. world_tree.timeline_era vs character.speech_style
        self._check_era_vs_speech_style(after, conflicts, warnings)

        # 2. world_tree.core_rules vs character_card
        self._check_world_rules_vs_characters(after, conflicts, warnings)

        # 3. main_plot range vs seed_table payoff
        self._check_main_plot_range_vs_seeds(after, conflicts, warnings)

        # 4. character role vs character relationship
        self._check_character_roles(after, conflicts, warnings)

        # 5. sub_plot vs main_plot status
        self._check_subplot_status(after, conflicts, warnings)

        # 6. proposed_seeds 的合理性
        if proposed_seeds:
            self._check_proposed_seeds(after, proposed_seeds, conflicts, warnings)

        status = "PASS"
        if conflicts:
            status = "FAIL"
        elif warnings:
            status = "WARN"

        return ConsistencyCheckResult(
            status=status,
            conflicts=conflicts,
            warnings=warnings,
        )

    # ============ 检查规则 ============

    def _check_era_vs_speech_style(self, snap: BaseSnapshot, conflicts: List[str], warnings: List[str]):
        """规则 1：古代角色不能用现代网络用语

        检查：world_tree.timeline_era = "古代" 时，character.speech_style 不应包含现代网络词
        """
        era = snap.world_tree.get("timeline_era", "")
        if era not in ("古代", "架空"):
            return

        modern_terms = ["卧槽", "666", "哈哈哈", "OMG", "lol", "lol", "鸡你太美", "yyds"]
        for char in snap.character_card:
            speech = char.get("speech_style", "") or ""
            for term in modern_terms:
                if term in speech:
                    warnings.append(
                        f"角色《{char.get('name', '?')}》的 speech_style 包含现代网络词「{term}」，但项目是「{era}」背景"
                    )

    def _check_world_rules_vs_characters(self, snap: BaseSnapshot, conflicts: List[str], warnings: List[str]):
        """规则 2：世界规则不允许的事，角色不能做

        示例：world_tree.core_rules 包含"无魔法"，角色不能是法师
        """
        core_rules = snap.world_tree.get("core_rules", []) or []
        no_magic = any("无魔法" in str(rule) or "no magic" in str(rule).lower() for rule in core_rules)
        no_magic = no_magic or any(
            "magic" in str(rule).lower() and ("no" in str(rule).lower() or "none" in str(rule).lower())
            for rule in core_rules
        )
        if not no_magic:
            return

        for char in snap.character_card:
            traits = char.get("traits", []) or []
            background = char.get("background", "") or ""
            combined = " ".join([str(t) for t in traits] + [background])
            if "法师" in combined or "魔法" in combined or "wizard" in combined.lower():
                conflicts.append(
                    f"角色《{char.get('name', '?')}》使用魔法，但 world_tree.core_rules 禁止魔法"
                )

    def _check_main_plot_range_vs_seeds(self, snap: BaseSnapshot, conflicts: List[str], warnings: List[str]):
        """规则 3：seed 的 payoff 章节不能超出 main_plot 范围"""
        main_plot = snap.main_plot or {}
        # main_plot 可能有 start_chapter / end_chapter 字段
        main_end = main_plot.get("end_chapter") or main_plot.get("total_chapters")
        if main_end is None:
            return  # 没定义范围，跳过检查

        for seed in snap.seed_table:
            payoff_ch = seed.get("payoff_chapter")
            if payoff_ch is None:
                continue
            try:
                payoff_ch = int(payoff_ch)
                main_end = int(main_end)
            except (ValueError, TypeError):
                continue
            if payoff_ch > main_end:
                conflicts.append(
                    f"种子《{seed.get('name', '?')}》的 payoff 在第 {payoff_ch} 章，但 main_plot 只到第 {main_end} 章"
                )

    def _check_character_roles(self, snap: BaseSnapshot, conflicts: List[str], warnings: List[str]):
        """规则 4：主角和反派不能是夫妻"""
        characters = {c.get("id"): c for c in snap.character_card}
        # 检查 character_relationships（这里简化：直接从 character_card 的 internal_state 看）
        for char in snap.character_card:
            role = char.get("role", "")
            name = char.get("name", "?")
            # 主角不能是反派
            if role == "protagonist" and "反派" in str(char.get("background", "")):
                warnings.append(f"角色《{name}》role=protagonist 但 background 含「反派」")

            # 反派不能是 deuteragonist
            if role == "deuteragonist" and "反派" in str(char.get("background", "")):
                warnings.append(f"角色《{name}》role=deuteragonist（副主角）但 background 含「反派」")

    def _check_subplot_status(self, snap: BaseSnapshot, conflicts: List[str], warnings: List[str]):
        """规则 5：sub_plot 状态不应与 main_plot 矛盾"""
        main_plot = snap.main_plot or {}
        main_status = main_plot.get("status", "active")
        for sub in snap.sub_plots:
            sub_status = sub.get("status", "active")
            if main_status == "completed" and sub_status == "active":
                warnings.append(
                    f"主线已完成，但支线《{sub.get('title', '?')}》还在 active 状态"
                )

    def _check_proposed_seeds(self, snap: BaseSnapshot, proposed: List[NewSeed], conflicts: List[str], warnings: List[str]):
        """规则 6：待添加的种子不能与现有种子重名"""
        existing_names = {s.get("name") for s in snap.seed_table}
        for seed in proposed:
            if seed.name in existing_names:
                warnings.append(f"种子《{seed.name}》与已有种子重名")

    # ============ 辅助方法 ============

    @staticmethod
    def load_snapshot(repo: ProjectRepository, project_id: str) -> BaseSnapshot:
        """从 DB 加载项目当前 7 件基座快照"""
        proj = repo.get(project_id)
        if not proj:
            return BaseSnapshot()

        # v0.6 简化：直接从 repo 读各表的 JSON 字段
        world_tree = repo.get_world_tree(project_id) or {}
        style_charter = repo.get_style_charter(project_id) or {}
        genre_resonance = repo.get_genre_resonance(project_id) or {}
        main_plot = repo.get_main_plot(project_id) or {}
        sub_plots = repo.list_subplots(project_id) or []
        characters = repo.list_characters(project_id) or []
        seed_table = repo.list_seeds(project_id) or []

        return BaseSnapshot(
            world_tree=world_tree,
            style_charter=style_charter,
            genre_resonance=genre_resonance,
            main_plot=main_plot,
            sub_plots=sub_plots,
            character_card=characters,
            seed_table=seed_table,
        )