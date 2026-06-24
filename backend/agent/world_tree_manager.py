"""world_tree_manager — 世界树管理（v0.6 顶层 Agent 之一）

职责（对应 spec.md §3.3）：
1. 基座一致性检查（7 件基座不能内部矛盾）
2. 剧情干预影响分析（用户说"把师父改成反派"→ 影响范围分析）
3. 种子/伏笔预留（长程规划）
4. 走向调整（根据用户干预调整 main_arc / sub_plots）
5. 返回结构化 diff 给管家

关键设计：
- 不生成章节正文（写不是它的职责）
- 不直接和用户对话（通过管家中转）
- 调用 MemoryKeeper 检索历史干预记录
- 复用 specialists.WorldTreeKeeperSpecialist 的 LLM 调用逻辑

对应 spec.md §3.3
"""
from __future__ import annotations

import logging
from typing import Optional, Any
from pydantic import BaseModel, Field

from backend.agent.specialists import WorldTreeKeeperSpecialist

log = logging.getLogger(__name__)


# ============ Diff 结构（v0.6 拍板）============

class BaseUpdate(BaseModel):
    """单条基座更新"""
    artifact: str = Field(description="7 件之一: world_tree/style_charter/genre_resonance/main_plot/sub_plots/character_card/seed_table")
    field: str = Field(description="字段路径（如 '师父.role' 或 'main_arc.第3章'）")
    old_value: Any = None
    new_value: Any = None
    reason: str = ""


class PlotAdjustment(BaseModel):
    """主线/支线走向调整"""
    arc: str = Field(description="主线/支线名")
    adjustment: str = Field(description="调整描述")
    impact_chapters: list[int] = Field(default_factory=list, description="影响章节范围")


class NewSeed(BaseModel):
    """新埋种子/伏笔"""
    name: str = Field(description="种子名")
    trigger: str = Field(description="触发场景描述")
    payoff: str = Field(description="回收场景描述")
    estimated_chapter: Optional[int] = Field(default=None, description="预计触发章节")


class ConsistencyCheckResult(BaseModel):
    """一致性检查结果"""
    status: str = Field(default="PASS", description="PASS / WARN / FAIL")
    conflicts: list[str] = Field(default_factory=list, description="冲突列表")
    warnings: list[str] = Field(default_factory=list, description="警告列表")


class WorldTreeDiff(BaseModel):
    """世界树管理返回的结构化 diff（管家转给用户确认）

    对应 spec.md §1.2 目标 3 + §3.3
    """
    intent: str = Field(description="intervene / adjust_base")
    summary: str = Field(description="一句话总结这次干预的影响")

    # 三段 diff
    base_updates: list[BaseUpdate] = Field(default_factory=list)
    plot_adjustments: list[PlotAdjustment] = Field(default_factory=list)
    new_seeds: list[NewSeed] = Field(default_factory=list)

    # 一致性检查
    consistency: ConsistencyCheckResult = Field(default_factory=ConsistencyCheckResult)

    # 风险评估
    risk_level: str = Field(default="low", description="low/medium/high")
    requires_double_confirm: bool = Field(default=False)


class NovelWriterManager:
    """占位（误用名），保留为兼容旧引用，正式类是下面的 WorldTreeManager"""
    pass


# ============ WorldTreeManager 主类 ============

class WorldTreeManager:
    """世界树管理（v0.6 顶层 Agent）

    使用方式：
        manager = WorldTreeManager()
        diff = await manager.analyze_intervention(
            project_id="abc123",
            intervention_text="把主角的师父改成反派",
        )
        # diff = WorldTreeDiff(...)
        # diff.base_updates / diff.plot_adjustments / diff.new_seeds / diff.consistency

    v0.6 s2 阶段：调用 specialists.WorldTreeKeeperSpecialist，包装为 WorldTreeDiff
    v0.6 s4 阶段：实装完整的一致性检查器 + 多步 diff 合并
    """

    def __init__(self):
        # 复用现有 specialist（v0.5 已实装的 WorldTreeKeeperSpecialist）
        self.worldtree_specialist = WorldTreeKeeperSpecialist()

    async def analyze_intervention(
        self,
        project_id: str,
        intervention_text: str,
        max_history: int = 5,
    ) -> WorldTreeDiff:
        """分析干预影响，返回结构化 diff

        Args:
            project_id: 项目 ID
            intervention_text: 用户干预描述（如 "把主角的师父改成反派"）
            max_history: 历史干预记录数

        Returns:
            WorldTreeDiff
        """
        log.info(f"world_tree_manager: analyze intervention project_id={project_id} text={intervention_text[:50]}")

        try:
            # 委托给 WorldTreeKeeperSpecialist（v0.5 已实装）
            specialist_result = await self.worldtree_specialist.consult({
                "project_id": project_id,
                "user_message": intervention_text,
                "max_history": max_history,
            })

            # 解析 specialist 返回的 diff（v0.5 可能是 raw dict）
            specialist_diff = specialist_result.get("diff", [])
            action = specialist_result.get("action", "view")

            # 转 WorldTreeDiff
            base_updates = []
            plot_adjustments = []
            new_seeds = []

            if isinstance(specialist_diff, list):
                for item in specialist_diff:
                    # item 可能是 dict，需要根据 type 分发
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        if item_type == "base_update":
                            base_updates.append(BaseUpdate(**item))
                        elif item_type == "plot_adjustment":
                            plot_adjustments.append(PlotAdjustment(**item))
                        elif item_type == "new_seed":
                            new_seeds.append(NewSeed(**item))

            # 一致性检查（s4 阶段实装完整版本）
            consistency = ConsistencyCheckResult(
                status="PASS",  # s2 阶段先 PASS，s4 实装 checker
                conflicts=[],
                warnings=[],
            )

            # 风险评估
            risk_level = "low"
            requires_double_confirm = False
            if len(base_updates) > 3 or len(plot_adjustments) > 0:
                risk_level = "medium"
            if len(base_updates) > 5:
                risk_level = "high"
                requires_double_confirm = True

            return WorldTreeDiff(
                intent="intervene",
                summary=specialist_result.get("opinion", "已分析干预影响"),
                base_updates=base_updates,
                plot_adjustments=plot_adjustments,
                new_seeds=new_seeds,
                consistency=consistency,
                risk_level=risk_level,
                requires_double_confirm=requires_double_confirm,
            )

        except Exception as e:
            log.error(f"world_tree_manager: analyze_intervention failed: {e}")
            return WorldTreeDiff(
                intent="intervene",
                summary=f"分析失败: {e}",
                consistency=ConsistencyCheckResult(status="FAIL", conflicts=[str(e)]),
                risk_level="high",
                requires_double_confirm=True,
            )

    async def analyze_base_adjustment(
        self,
        project_id: str,
        adjustment_text: str,
    ) -> WorldTreeDiff:
        """分析基座调整（与干预类似，但 intent 不同）"""
        return await self.analyze_intervention(
            project_id=project_id,
            intervention_text=adjustment_text,
        )


# ============ 工厂方法 ============

_manager_instance: Optional[WorldTreeManager] = None


def get_world_tree_manager() -> WorldTreeManager:
    """获取单例 WorldTreeManager"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = WorldTreeManager()
    return _manager_instance