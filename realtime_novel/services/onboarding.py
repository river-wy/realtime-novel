"""services/onboarding.py — S3 启动链路 orchestrator

按 docs/design/01-world-tree.md §2 实现 5 步引导:

Step 1a · 必选标签      题材 / 风格 / 基调 (硬必填)
Step 1b · 可选标签      装饰性偏好 (可跳过)
Step 2   · 引导文本     6 类元素采集 (硬 ≥3 + 软 ≥1 门禁)
Step 3   · 大纲确认     主线 / 支线 / 人物 / 种子
Step 4   · 后台准备     ❌ 不可见 · 系统生成 7 件 YAML
Step 5   · 进入剧情     复用 S4 生成第 1 章

可中断 / 恢复:
- onboarding.state 写到 projects/{id}/.onboarding-state.json
- 启动时检查 → resume / restart 二选一
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..core.project import Project
from ..core.schemas import (
    WorldTreeSchema, StyleCharterSchema, GenreResonanceSchema,
    MainPlotSchema, SubPlotSchema, CharacterCardSchema, SeedTableSchema,
)
from ..core.exceptions import ProjectError
from ..adapters.io import write as io_write
from ..adapters.llm import call_llm
from ..cli.interactive import prompt, confirm, multi_select, single_select
from .chapter_generator import ChapterGenerator, GenerationResult
from ..core.world_tree import WorldTree


# === 标签字典（M-γ 阶段预设，后续可改成 YAML 配置文件）===

GENRE_OPTIONS = [
    "都市", "古风", "玄幻", "修仙", "校园", "职场", "家庭", "悬疑", "科幻",
]
STYLE_OPTIONS = [
    "言情", "治愈", "悬疑", "战斗", "成长", "日常", "群像", "单女主",
    "双女主", "慢热", "快节奏", "成人向",
]
TONE_OPTIONS = ["压抑", "温暖", "残酷", "治愈", "戏谑", "冷叙述", "史诗"]


@dataclass
class OnboardingState:
    """5 步引导的状态（可序列化/恢复）"""
    project_id: str
    current_step: int = 0  # 0-5
    started_at: str = ""
    updated_at: str = ""

    # Step 1a 必选
    genres: List[str] = field(default_factory=list)
    styles: List[str] = field(default_factory=list)
    tone: str = ""

    # Step 1b 可选
    palette: List[str] = field(default_factory=list)

    # Step 2 引导文本（6 类元素）
    core_relationship: str = ""          # 硬必填
    emotional_anchor: str = ""           # 软必填
    taboos: str = ""                     # 软必填
    ending_preference: str = ""          # 可选
    extra_notes: str = ""                # 自由补充

    # Step 3 大纲
    main_conflict: str = ""              # 硬必填（"故事核心矛盾 1 句话"）
    main_beats: List[Dict[str, str]] = field(default_factory=list)  # 5-7 个关键节点
    sub_plots: List[str] = field(default_factory=list)             # 1-2 条
    characters: List[Dict[str, str]] = field(default_factory=list) # 3-5 个
    seeds: List[Dict[str, str]] = field(default_factory=list)      # 2-3 颗种子

    # Step 4 产物（生成后填）
    artifacts_generated: bool = False

    # Step 5 章节
    chapter_1_generated: bool = False
    chapter_1_path: str = ""


# === 主类 ===

class OnboardingFlow:
    """S3 · 启动链路 orchestrator"""

    STATE_FILE = ".onboarding-state.json"

    def __init__(self, project: Project):
        self.project = project
        self.state = self._load_state() or OnboardingState(project_id=project.project_id)

    # === 状态持久化 ===

    def _state_path(self) -> Path:
        return self.project.project_dir / self.STATE_FILE

    def _load_state(self) -> Optional[OnboardingState]:
        p = self._state_path()
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return OnboardingState(**data)

    def _save_state(self) -> None:
        self.state.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not self.state.started_at:
            self.state.started_at = self.state.updated_at
        self._state_path().write_text(
            json.dumps(asdict(self.state), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # === 5 步 ===

    def run(self, *, force_restart: bool = False) -> None:
        """5 步引导主入口

        Args:
            force_restart: 强制从头开始（清空已存状态）
        """
        if self._state_path().exists() and not force_restart:
            self._handle_resume_or_restart()
        else:
            self._run_from_scratch()

    def _handle_resume_or_restart(self) -> None:
        print()
        print(f"📌 检测到项目 '{self.project.project_id}' 有未完成的引导（已到 Step {self.state.current_step}）")
        choice = single_select(
            "如何继续?",
            ["继续上次的进度 (resume)", "从头开始 (restart)"],
        )
        if "继续" in choice:
            self._run_resume()
        else:
            self.state = OnboardingState(project_id=self.project.project_id)
            self._state_path().unlink(missing_ok=True)
            self._run_from_scratch()

    def _run_from_scratch(self) -> None:
        print()
        print("=" * 60)
        print(f"  🪄 启动链路 5 步引导")
        print(f"  项目: {self.project.project_id}")
        print(f"  提示: 任何时候输入 q 退出，下次可用 'realtime-novel new' 继续")
        print("=" * 60)

        for step in range(1, 6):
            self.state.current_step = step
            self._save_state()
            if not self._run_step(step):
                return  # 退出引导（用户主动 q）

        # 全部完成
        print()
        print("=" * 60)
        print(f"  🎉 项目 '{self.project.project_id}' 启动完成！")
        print(f"  目录: {self.project.project_dir}")
        print(f"  继续: realtime-novel generate --project-id {self.project.project_id}")
        print("=" * 60)

    def _run_resume(self) -> None:
        """恢复引导"""
        if self.state.current_step >= 5:
            print("✅ 引导已完成，无需恢复")
            return
        print(f"📌 从 Step {self.state.current_step + 1} 继续...")
        for step in range(self.state.current_step + 1, 6):
            self.state.current_step = step
            self._save_state()
            if not self._run_step(step):
                return

    def _run_step(self, step: int) -> bool:
        """执行单步。返回 True 继续，False 退出引导"""
        handler = {
            1: self._step1_required_tags,
            2: self._step1_optional_palette,
            3: self._step2_guided_text,
            4: self._step3_outline,
            5: self._step4_backend_prep_and_chapter,
        }.get(step)
        if handler is None:
            raise ProjectError(f"未知 Step: {step}")
        return handler()

    # === Step 1a: 必选标签 ===

    def _step1_required_tags(self) -> bool:
        print()
        print("─" * 60)
        print("📌 Step 1a · 必选标签（题材 / 风格 / 基调）")
        print("─" * 60)

        # 题材
        if not self.state.genres:
            self.state.genres = multi_select("你想写什么题材?", GENRE_OPTIONS)
            if not self.state.genres:
                print("⚠️  至少选 1 个题材")
                return self._step1_required_tags()
        else:
            print(f"  ✓ 题材已选: {self.state.genres}")

        # 风格
        if not self.state.styles:
            self.state.styles = multi_select("你想要什么风格?", STYLE_OPTIONS)
            if not self.state.styles:
                print("⚠️  至少选 1 个风格")
                return self._step1_required_tags()
        else:
            print(f"  ✓ 风格已选: {self.state.styles}")

        # 基调（单选）
        if not self.state.tone:
            self.state.tone = single_select("你想要的基调?", TONE_OPTIONS)
        else:
            print(f"  ✓ 基调已选: {self.state.tone}")

        print()
        print(f"  📋 你的选择:")
        print(f"     题材: {self.state.genres}")
        print(f"     风格: {self.state.styles}")
        print(f"     基调: {self.state.tone}")
        if not confirm("确认?", default=True):
            self.state.genres = []
            self.state.styles = []
            self.state.tone = ""
            return self._step1_required_tags()

        self._save_state()
        return True

    # === Step 1b: 可选标签 ===

    def _step1_optional_palette(self) -> bool:
        print()
        print("─" * 60)
        print("📌 Step 1b · 可选标签（装饰性偏好，可跳过）")
        print("─" * 60)

        if not self.state.palette:
            self.state.palette = multi_select(
                "你还想强调哪些调性?",
                STYLE_OPTIONS,  # 复用风格列表
                allow_skip=True,
            )
        print(f"  调色板: {self.state.palette or '(空)'}")
        self._save_state()
        return True

    # === Step 2: 引导式自由文本 ===

    def _step2_guided_text(self) -> bool:
        print()
        print("─" * 60)
        print("📌 Step 2 · 引导式自由文本（采集 6 类元素）")
        print("─" * 60)

        # 核心关系（硬必填）
        if not self.state.core_relationship:
            print()
            print("💬 第 1 轮：核心关系（必填）")
            print("   问：你希望主角与谁有怎样的核心关系?")
            print("   例：师徒 / 敌对 / 暧昧 / 兄妹 / 夫妻 / 同事 / 敌友")
            self.state.core_relationship = prompt("→ ")
            if not self.state.core_relationship:
                print("⚠️  这项是硬必填，请描述一下")
                return self._step2_guided_text()
        else:
            print(f"  ✓ 核心关系: {self.state.core_relationship}")

        # 情感锚点（软必填 ≥1）
        if not self.state.emotional_anchor:
            print()
            print("💬 第 2 轮：情感锚点（建议填）")
            print("   问：你想看到什么情感表达? 一句话即可。")
            print("   例：「想看被压抑很久的情感爆发」「想看克制下的温柔」")
            self.state.emotional_anchor = prompt("→ ", default="")
        else:
            print(f"  ✓ 情感锚点: {self.state.emotional_anchor}")

        # 禁区（软必填 ≥1）
        if not self.state.taboos:
            print()
            print("💬 第 3 轮：禁区（建议填）")
            print("   问：你不想看到什么? 一句话即可。")
            print("   例：「不要后宫 / 不要种马 / 不要系统流」")
            self.state.taboos = prompt("→ ", default="")
        else:
            print(f"  ✓ 禁区: {self.state.taboos}")

        # 结局倾向（可选）
        if not self.state.ending_preference:
            print()
            print("💬 第 4 轮：结局倾向（可选）")
            print("   问：你希望故事走向什么结局?")
            print("   例：必好 / 必悲 / 开放 / 由系统决定")
            self.state.ending_preference = prompt("→ ", default="由系统决定")
        else:
            print(f"  ✓ 结局倾向: {self.state.ending_preference}")

        # 自由补充（可选）
        if not self.state.extra_notes:
            print()
            print("💬 第 5 轮：自由补充（可选）")
            print("   问：还有什么想强调的吗? 一句话即可。")
            self.state.extra_notes = prompt("→ ", default="")
        else:
            print(f"  ✓ 自由补充: {self.state.extra_notes}")

        self._save_state()
        return True

    # === Step 3: 大纲确认 ===

    def _step3_outline(self) -> bool:
        print()
        print("─" * 60)
        print("📌 Step 3 · 大纲确认（主线 / 支线 / 人物 / 种子）")
        print("─" * 60)

        # 主线核心矛盾
        if not self.state.main_conflict:
            print()
            print("📖 3a. 主线核心矛盾（1 句话）")
            print("   例：「主角发现父亲遗物，决定追寻父亲失踪的真相」")
            self.state.main_conflict = prompt("→ ")
            if not self.state.main_conflict:
                print("⚠️  必填")
                return self._step3_outline()
        else:
            print(f"  ✓ 主线核心矛盾: {self.state.main_conflict}")

        # 主线 5-7 个关键节点
        if not self.state.main_beats:
            print()
            print("📖 3b. 主线关键节点（5-7 个，每个一句话）")
            print("   每行一个，例如：「第 3 章：发现遗物 / 第 8 章：初遇关键人物」")
            print("   (空行结束)")
            while True:
                line = prompt(f"  节点 {len(self.state.main_beats) + 1} → ", default="")
                if not line:
                    if len(self.state.main_beats) >= 5:
                        break
                    else:
                        print(f"  ⚠️  至少 5 个节点（当前 {len(self.state.main_beats)}）")
                        continue
                self.state.main_beats.append({
                    "title": line,
                    "description": line,
                })
        else:
            print(f"  ✓ 主线节点: {len(self.state.main_beats)} 个")

        # 支线 1-2 条
        print()
        print("📖 3c. 支线（0-2 条，可跳过）")
        if not self.state.sub_plots:
            if confirm("需要定义支线吗?", default=False):
                while len(self.state.sub_plots) < 2:
                    line = prompt(f"  支线 {len(self.state.sub_plots) + 1}（一句话） → ")
                    if not line:
                        break
                    self.state.sub_plots.append(line)
        else:
            print(f"  ✓ 支线: {self.state.sub_plots}")

        # 人物 3-5 个
        if not self.state.characters:
            print()
            print("📖 3d. 主要人物（3-5 个，含主角）")
            print("   格式：名字 / 角色 / 一句话背景")
            print("   例：林远 / 主角 / 28 岁杭州程序员，妻子是高中语文老师")
            print("   (空行结束)")
            while True:
                line = prompt(f"  人物 {len(self.state.characters) + 1} → ", default="")
                if not line:
                    if len(self.state.characters) >= 3:
                        break
                    else:
                        print(f"  ⚠️  至少 3 个人物（当前 {len(self.state.characters)}）")
                        continue
                # 简单切分: "名字 / 角色 / 背景"
                parts = [p.strip() for p in line.split("/", 2)]
                if len(parts) < 3:
                    parts = parts + [""] * (3 - len(parts))
                self.state.characters.append({
                    "id": f"char-{len(self.state.characters) + 1:03d}",
                    "name": parts[0],
                    "role": parts[1] or "supporting",
                    "background": parts[2],
                })
        else:
            print(f"  ✓ 人物: {len(self.state.characters)} 个")

        # 种子 2-3 颗
        if not self.state.seeds:
            print()
            print("📖 3e. 种子（2-3 颗）")
            print("   种子=计划在后面复现的具体细节。例：'1987 年的收音机'")
            print("   (空行结束)")
            while True:
                line = prompt(f"  种子 {len(self.state.seeds) + 1} → ", default="")
                if not line:
                    if len(self.state.seeds) >= 2:
                        break
                    else:
                        print(f"  ⚠️  至少 2 颗种子（当前 {len(self.state.seeds)}）")
                        continue
                self.state.seeds.append({
                    "id": len(self.state.seeds) + 1,
                    "content": line,
                })
        else:
            print(f"  ✓ 种子: {len(self.state.seeds)} 颗")

        self._save_state()
        return True

    # === Step 4 + 5: 后台准备 + 第 1 章 ===

    def _step4_backend_prep_and_chapter(self) -> bool:
        print()
        print("─" * 60)
        print("📌 Step 4 · 后台准备（生成 7 件产物）")
        print("─" * 60)

        if not self.state.artifacts_generated:
            print()
            print("  🛠  调用 LLM 把你的设定 → 7 件 YAML ...")
            try:
                self._generate_7_artifacts()
            except Exception as e:
                print(f"  ❌ 生成失败: {e}")
                if confirm("重试?", default=True):
                    return self._step4_backend_prep_and_chapter()
                return False
            self.state.artifacts_generated = True
            self._save_state()
        else:
            print("  ✓ 7 件产物已生成")

        print()
        print("─" * 60)
        print("📌 Step 5 · 进入剧情（生成第 1 章）")
        print("─" * 60)

        if not self.state.chapter_1_generated:
            print()
            print("  🚀 复用 S4 ChapterGenerator 生成 chapter-01 ...")
            try:
                self._generate_chapter_1()
            except Exception as e:
                print(f"  ❌ 生成失败: {e}")
                if confirm("重试?", default=True):
                    return self._step4_backend_prep_and_chapter()
                return False
            self.state.chapter_1_generated = True
            self._save_state()
        else:
            print("  ✓ 第 1 章已生成")

        print()
        print("  📋 7 件产物:")
        from ..core.schemas import SCHEMA_REGISTRY
        for _, filename in SCHEMA_REGISTRY:
            fpath = self.project.file_path(filename)
            if fpath.exists():
                size = fpath.stat().st_size
                print(f"     · {filename} ({size} 字节)")
        print()
        print(f"  📖 第 1 章: {self.state.chapter_1_path}")
        print(f"     {self.project.chapter_path(1).read_text(encoding='utf-8')[:200]}...")

        return True

    # === Step 4 实现 ===

    def _generate_7_artifacts(self) -> None:
        """调 LLM 把设定生成 7 件 — v0.4.1 全部入 DB

        流程：
        1. 构造 prompt
        2. 调 7 次 LLM（或 1 次大调用解析）生成 7 件 dict
        3. Pydantic 校验 7 件
        4. 走 ProjectRepository.save_7_artifacts 落 DB
        """
        # 构造 prompt
        user_input = f"""题材: {self.state.genres}
风格: {self.state.styles}
基调: {self.state.tone}
调色板: {self.state.palette or '(无)'}
核心关系: {self.state.core_relationship}
情感锚点: {self.state.emotional_anchor or '(无)'}
禁区: {self.state.taboos or '(无)'}
结局倾向: {self.state.ending_preference}
自由补充: {self.state.extra_notes or '(无)'}

主线核心矛盾: {self.state.main_conflict}
主线节点: {[b['title'] for b in self.state.main_beats]}
支线: {self.state.sub_plots or '(无)'}
人物: {self.state.characters}
种子: {self.state.seeds}"""

        # === 7 次 LLM 生成（v0.4.1 暂保留，将来可改 1 次大调用）===
        print("    · 生成 world_tree ...")
        wt = self._gen_world_tree(user_input)

        print("    · 生成 style_charter ...")
        sc = self._gen_style_charter(user_input)

        print("    · 生成 genre_resonance ...")
        gr = self._gen_genre_resonance(user_input)

        print("    · 生成 main_plot ...")
        mp = self._gen_main_plot(user_input)

        print("    · 生成 character_card ...")
        cc = self._gen_character_card(user_input)

        print("    · 生成 sub_plot ...")
        sp = self._gen_sub_plot(user_input)

        print("    · 生成 seed_table ...")
        st = self._gen_seed_table(user_input)

        # Pydantic 校验 7 件（不落盘）
        loaded_validated = {}
        for schema_cls, filename, data in [
            (WorldTreeSchema, "01-world-tree.yaml", wt),
            (StyleCharterSchema, "02-style-charter.yaml", sc),
            (GenreResonanceSchema, "03-genre-resonance.yaml", gr),
            (MainPlotSchema, "04-main-plot.yaml", mp),
            (CharacterCardSchema, "06-character-card.yaml", cc),
            (SubPlotSchema, "05-sub-plot.yaml", sp),
            (SeedTableSchema, "07-seed-table.yaml", st),
        ]:
            loaded_validated[filename] = schema_cls.model_validate(data)

        # 入 DB（v0.4.1 走 ProjectRepository，不写 YAML 文件）
        from realtime_novel.persistence import ProjectRepository
        repo = ProjectRepository()
        repo.save_7_artifacts(
            project_id=self.project.project_id,
            world_tree=wt,
            style_charter=sc,
            genre_resonance=gr,
            main_plot=mp,
            sub_plot=sp,
            character_card=cc,
            seed_table=st,
        )
        print(f"  ✓ 7 件 Pydantic 校验通过 + 入 DB")

        # 保存状态
        self._save_state()

    def _llm_json(self, system: str, user: str) -> dict:
        """调 LLM 拿 JSON（带重试 + 容错）"""
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                raw = call_llm(
                    user,
                    system_msg=system,
                    use_json_format=True,
                    max_tokens=4096,
                    temperature=0.5,
                    timeout=120,
                )
                return json.loads(raw)
            except Exception as e:
                last_err = e
                time.sleep(1)
        raise RuntimeError(f"LLM JSON 解析 3 次都失败: {last_err}")

    # 7 件生成函数
    def _gen_world_tree(self, user_input: str) -> dict:
        data = self._llm_json(
            "你是世界树设计师。严格按 JSON 输出，无任何解释。",
            f"""根据用户的设定，生成 WorldTree (01-world-tree.yaml)。

## 用户设定
{user_input}

## 输出 JSON 格式
{{
  "schema_version": "1.0",
  "base": {{
    "timeline": {{
      "era": "现代 | 古代 | 未来 | 架空",
      "year_range": {{"start": 2019, "end": 2019}},
      "anchor_event": "..."
    }},
    "geography": {{
      "primary": "...",
      "secondary": ["..."],
      "spatial_rules": ["..."]
    }},
    "core_rules": [
      {{"id": "rule-001", "statement": "...", "enforcement": "hard", "applies_to": "all"}}
    ]
  }},
  "branches": [],
  "metadata": {{"created_at": "2026-06-15"}}
}}""",
        )
        # 兏底: LLM 偶而在 branches 里塞 LLM 魔改的 dict，与 TreeNode 不兼容
        # 强制 branches = []，让 WorldTreeSchema 校验一致
        data["branches"] = []
        return data

    def _gen_style_charter(self, user_input: str) -> dict:
        return self._llm_json(
            "你是风格宪法设计师。",
            f"""根据用户设定生成 StyleCharter。

## 用户设定
{user_input}

## 输出 JSON
{{
  "schema_version": "1.0",
  "prose_style": {{
    "primary": "散文式 | 对话驱动 | 意识流 | 传统小说",
    "sentence_length": "短句为主 | 长短交错 | 长句为主",
    "paragraph_style": "..."
  }},
  "tone": {{
    "primary": "冷叙述 | 温暖 | 疏离 | 戏谑 | ...",
    "secondary": "...",
    "psychological_per_paragraph": 3
  }},
  "density": {{
    "specificity": 0.7,
    "subjectivity": 0.6,
    "density": 0.5,
    "genre_resonance": 0.8,
    "max_specific_granules_per_kchars": 3
  }},
  "taboos": [
    {{"id": "taboo-001", "description": "不滥情", "severity": "forbidden"}}
  ],
  "limits": {{
    "psychological_per_paragraph": 3,
    "specific_granules_per_kchars": 3,
    "max_chapter_words": 3000,
    "min_chapter_words": 2500
  }},
  "metadata": {{"created_at": "2026-06-15"}}
}}""",
        )

    def _gen_genre_resonance(self, user_input: str) -> dict:
        return self._llm_json(
            "你是题材共鸣分析师。",
            f"""根据用户设定生成 GenreResonance。

## 用户设定
{user_input}

## 输出 JSON
{{
  "schema_version": "1.0",
  "accept": [
    {{"text": "日常细节", "weight": 0.8}}
  ],
  "reject": [
    {{"text": "爽文套路", "weight": 0.9}}
  ],
  "anchors": [
    {{"phrase": "我想看被压抑很久的情感爆发", "sentiment": "positive", "binding": "soft"}}
  ],
  "metadata": {{"created_at": "2026-06-15", "source": "user-input"}}
}}""",
        )

    def _gen_main_plot(self, user_input: str) -> dict:
        return self._llm_json(
            "你是主线大纲设计师。",
            f"""根据用户设定生成 MainPlot (04-main-plot.yaml)。

## 用户设定
{user_input}

## 输出 JSON
{{
  "schema_version": "1.0",
  "beats": [
    {{"id": "beat-001", "sequence": 1, "title": "...", "description": "...",
     "trigger": {{"type": "auto"}}, "status": "active",
     "chapter_range": {{"start": 1, "end": 5}},
     "linked_seeds": [], "linked_chars": [],
     "expected_arc": "..."}}
  ],
  "current_beat": 0,
  "arc_phrase": "...",
  "metadata": {{"created_at": "2026-06-15"}}
}}""",
        )

    def _gen_sub_plot(self, user_input: str) -> dict:
        return self._llm_json(
            "你是支线大纲设计师。",
            f"""根据用户设定生成 SubPlot (05-sub-plot.yaml)。

如果用户没指定支线，返回空 threads 数组。

## 用户设定
{user_input}

## 输出 JSON
{{
  "schema_version": "1.0",
  "threads": [
    {{"id": "subplot-001", "title": "...", "description": "...",
     "parent_beat_id": "beat-001", "status": "active",
     "priority": "side", "linked_seeds": [], "linked_chars": [],
     "beats": []}}
  ],
  "metadata": {{"created_at": "2026-06-15"}}
}}""",
        )

    def _gen_character_card(self, user_input: str) -> dict:
        return self._llm_json(
            "你是人物卡设计师。",
            f"""根据用户设定生成 CharacterCard (06-character-card.yaml)。

## 用户设定
{user_input}

## 输出 JSON
{{
  "schema_version": "1.0",
  "characters": [
    {{"id": "char-protagonist", "name": "...", "role": "protagonist",
     "traits": ["..."], "speech_style": "...",
     "background": "...",
     "arc": "...",
     "internal_state": "..."}}
  ],
  "relationships": [
    {{"id": "rel-001", "from_char": "char-001", "to_char": "char-002",
     "type": "夫妻", "description": "...",
     "evolution": []}}
  ],
  "metadata": {{"created_at": "2026-06-15"}}
}}""",
        )

    def _gen_seed_table(self, user_input: str) -> dict:
        return self._llm_json(
            "你是种子表设计师。",
            f"""根据用户设定生成 SeedTable (07-seed-table.yaml)。

## 用户设定
{user_input}

## 输出 JSON
{{
  "schema_version": "1.0",
  "seeds": [
    {{"id": 1, "content": "...",
     "importance": {{"primary": "主线推进 | 支线故事 | 小巧思"}},
     "size": "长线 | 中线 | 点状",
     "planned_interval": 10,
     "orientation": "剧情翻转 | 关键成员关系 | 主角成长 | 支线揭示 | 小巧思 | 氛围营造",
     "planted_at_segment": 0,
     "planted_at_chapter": 0,
     "planted_in_node": "node-001",
     "planted_context": "...",
     "last_seen_segment": 0,
     "last_seen_chapter": 0,
     "weight": 0.5,
     "status": "planted",
     "linked_char_ids": [],
     "linked_subplot_id": ""}}
  ],
  "metadata": {{"created_at": "2026-06-15"}}
}}""",
        )

    # === Step 5 实现 ===

    def _generate_chapter_1(self) -> None:
        """复用 S4 ChapterGenerator 生成第 1 章"""
        # 加载 7 件 → WorldTree
        from ..adapters.io import read
        data = {}
        from ..core.schemas import SCHEMA_REGISTRY
        for _, filename in SCHEMA_REGISTRY:
            data[filename] = read(self.project.file_path(filename))
        tree = WorldTree.from_dict(data)

        # 复用 S4
        generator = ChapterGenerator(tree, self.project)
        result = generator.generate_next(
            chapter_num=1,
            chapter_summaries=[],  # 新项目无历史摘要
            last_chapter_full=None,
            user_input=f"第 1 章\n主线核心矛盾: {self.state.main_conflict}",
        )
        self.state.chapter_1_path = str(self.project.chapter_path(1))
