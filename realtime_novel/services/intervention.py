"""services/intervention.py — S5 InterventionParser

按 docs/design/00-overview.md §2.2 干预语义:
- 第三视角（导演模式）: 用户读全知视角故事，干预方式: '我期望 xxx' → 引导式输入
- 第一沉浸视角（演员模式）: 用户代入角色，干预方式: '我 xxx' → 入戏式输入

职责:
- 解析用户输入 → 结构化 Intervention
- 提供两种模式 (director / actor) 的 system_msg / user_input 转换
- 纯字符串处理, 0 LLM 调用

设计原则 (M-δ 阶段最小实现):
- 模式前缀: '我期望' / '我希望' / '我期待' → director
- 模式前缀: '我' (不带'期望/希望/期待') → actor
- 自由文本: 无前缀 → 通用干预, 按当前 mode 注入
- 持久化: 干预存到 projects/{id}/.intervention-log.json (审计用, 不入仓)
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List


class InterventionMode(str, Enum):
    DIRECTOR = "director"  # 引导式 (第三视角)
    ACTOR = "actor"        # 入戏式 (第一沉浸视角)


# 导演模式触发词
DIRECTOR_TRIGGERS = ("我期望", "我希望", "我期待", "我想看到", "我倾向于")
# 演员模式触发词
ACTOR_TRIGGERS = ("我",)  # 单独的"我"开头


@dataclass
class Intervention:
    """单次干预的结构化表示"""
    mode: str  # "director" | "actor"
    chapter_num: int
    raw_text: str
    extracted_payload: str
    system_msg: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class InterventionParser:
    """S5 · 干预解析器"""

    LOG_FILE = ".intervention-log.json"

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)

    def parse(
        self,
        raw_text: str,
        chapter_num: int,
        mode: InterventionMode | str = InterventionMode.DIRECTOR,
    ) -> Intervention:
        """解析用户输入 → Intervention

        Args:
            raw_text: 用户原始输入
            chapter_num: 干预影响哪一章
            mode: 导演/演员（可被输入前缀自动覆盖）

        Returns:
            Intervention 实例（含 system_msg + extracted_payload）

        行为:
            - 自动检测模式: '我期望'/'我希望' → director, '我' → actor
            - 提取实际语义: 去掉前缀
            - 生成 system_msg 提示 LLM
        """
        if isinstance(mode, str):
            mode = InterventionMode(mode)

        text = raw_text.strip()
        detected_mode, payload = self._detect_and_extract(text, mode)

        system_msg = self._build_system_msg(detected_mode, payload)

        intervention = Intervention(
            mode=detected_mode.value,
            chapter_num=chapter_num,
            raw_text=text,
            extracted_payload=payload,
            system_msg=system_msg,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        # 持久化（不入仓）
        self._append_log(intervention)
        return intervention

    def _detect_and_extract(
        self, text: str, default_mode: InterventionMode,
    ) -> tuple[InterventionMode, str]:
        """检测模式 + 提取有效负载"""
        # 导演模式：先匹配
        for trigger in DIRECTOR_TRIGGERS:
            if text.startswith(trigger):
                payload = text[len(trigger):].lstrip("：: \t,，")
                return InterventionMode.DIRECTOR, payload

        # 演员模式：'我' 开头（但不是 '我期望/希望/...'）
        if text.startswith("我"):
            payload = text[1:].lstrip("：: \t,，")
            return InterventionMode.ACTOR, payload

        # 自由文本：按默认 mode
        return default_mode, text

    def _build_system_msg(self, mode: InterventionMode, payload: str) -> str:
        """构造给 LLM 的 system 提示"""
        if mode == InterventionMode.DIRECTOR:
            return (
                f"[导演干预] 读者期望本章包含以下要素: {payload}\n"
                f"请自然地融入叙事，不要生硬植入。如果与现有剧情冲突，"
                f"请在保持一致性的前提下选择最合适的呈现方式。"
            )
        else:  # actor
            return (
                f"[演员干预] 读者想以角色身份执行以下动作: {payload}\n"
                f"请把这个动作自然地编入本章叙事, "
                f"允许动作的结果与读者预期有合理偏差（基于剧情逻辑）。"
            )

    def _append_log(self, intervention: Intervention) -> None:
        """追加到 .intervention-log.json (审计用, 不入仓)"""
        log_path = self.project_dir / self.LOG_FILE
        # 读现有 log
        if log_path.exists():
            try:
                data = json.loads(log_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {"interventions": []}
        else:
            data = {"interventions": []}
        data["interventions"].append(intervention.to_dict())
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        log_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def list_recent(project_dir: Path, limit: int = 5) -> List[Intervention]:
        """读最近 N 条干预记录"""
        log_path = Path(project_dir) / InterventionParser.LOG_FILE
        if not log_path.exists():
            return []
        data = json.loads(log_path.read_text(encoding="utf-8"))
        items = data.get("interventions", [])[-limit:]
        return [Intervention(**i) for i in items]
