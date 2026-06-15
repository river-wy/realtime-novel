# Changelog

所有本工程有意义的变更都记录在此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Changed (2026-06-15)
- **生成产物随项目保存**: `generated-stories/` 合并入 `projects/demo-urban-romance/chapters/`（欧尼酱手动操作，git 自动检测为 rename，零数据丢失）
- **代码 / 文档同步更新**: `tests/m2/test_chapter.py` + `cli/main.py` + 4 份文档改用新路径
- **conventions.md §1.1 + §9 强约束** 同步：`generated-stories/` 从顶层白名单删除，新增强约束 #14
- **v0.3 重构** (上一个 commit a5f9701)：
  - 5 子包分层 (core/services/adapters/cli/utils)
  - LLM 客户端完全独立
  - 验收脚本迁入 `tests/m1/m2/`
  - `__main__.py` + `cli/main.py` argparse 4 子命令
  - `conventions.md` 13 条强约束
  - `realtime_novel` 包版本号: 0.2.0-beta → 0.3.0-alpha

### Technical Details
- `verify.py` → `tests/m1/test_skeleton.py`
- `verify_mb.py` → `tests/m2/test_chapter.py`
- `realtime_novel/schemas/*` → `realtime_novel/core/schemas/*`
- `realtime_novel/world_tree.py` → `realtime_novel/core/world_tree.py`
- `realtime_novel/project.py` → `realtime_novel/core/project.py`
- `realtime_novel/chapter_generator.py` → `realtime_novel/services/chapter_generator.py`
- `realtime_novel/llm.py` → `realtime_novel/adapters/llm.py`（重写，完全独立）
- `realtime_novel/three_layer_prompt.py` → `realtime_novel/adapters/prompt.py`
- `realtime_novel/seed_weight.py` → `realtime_novel/adapters/seed_weight.py`
- `realtime_novel/io.py` → `realtime_novel/adapters/io.py`
- `realtime_novel/_seed_demo.py` → `realtime_novel/utils/seed_demo.py`
- `realtime_novel.egg-info/` 删除（自动重生）

### Migration
- **零破坏性**: 所有 import 路径在 `realtime_novel/__init__.py` 保持兼容
- **新增**: `from realtime_novel.core.xxx` 路径可显式引用 5 子包
- **保险点**: `v0.2-pre-refactor` git tag 可随时回滚

---

## [0.2.0] - 2026-06-15

### M-α (2026-06-15) · 骨架 0.1
- Added: `realtime_novel/project.py` S1 ProjectManager (create/load/list_projects)
- Added: `realtime_novel/world_tree.py` S2 WorldTree (内存模型 + 序列化 + rollback)
- Added: `realtime_novel/schemas/` 7 件 Pydantic Schema + TreeNode
- Added: `realtime_novel/io.py` YAML/JSON 读写
- Added: `realtime_novel/_seed_demo.py` 从 v0.2 case 装载 demo
- Added: `pyproject.toml` 包元信息
- Added: `verify.py` M-α 验收脚本 (5/5 通过)
- Added: `.realtime-novel/conventions.md` 工程内规则初版 (7 条)
- Test: 加载 demo → 实例化 WorldTree → round-trip → rollback 硬 reset

### M-β (2026-06-15) · 骨架 0.2
- Added: `realtime_novel/llm.py` LLM 客户端 (复用 lunaris call_llm)
- Added: `realtime_novel/three_layer_prompt.py` 三层 prompt 组装
- Added: `realtime_novel/seed_weight.py` 4 维权重 + sigmoid
- Added: `realtime_novel/schemas/chapter.py` ChapterSummary schema
- Added: `realtime_novel/chapter_generator.py` S4 ChapterGenerator + GenerationResult
- Added: `verify_mb.py` M-β 验收脚本 (5/5 通过)
- Test: 加载 demo → 端到端生成 chapter-21 (2670 字, 55.5s)
- Result: 风格跟 v0.2 demo 完全一致，主角名字稳定

---

## [0.1.0] - 2026-06-12 (v0.2 评测收口)

### v0.2 真实 LLM 评测
- Added: 5 份产品设计文档 (00-overview, 01-world-tree, 02-consistency, 03-schemas, 04-evaluation)
- Added: `docs/eval-notes/code/v0.2/` 真 LLM 评测代码
- Added: `projects/demo-urban-romance/` 21 万字 demo (20 章，含 7 件 YAML)
- Result: 4/5 指标达标 (种子回收率/基座约束/具体性密度/importance 优先采纳率)
- Limitation: 0/0 overdue (planned_interval 偏长, M-γ 调参解决)

---

## 版本对照

| 工程版本 | v0.2 路线图里程碑 | 状态 |
|---------|------------------|------|
| 0.3.0-alpha | M-α + M-β | ✅ 已完成 (2026-06-15) |
| (未来) | M-γ | S3 启动链路 5 步 CLI |
| (未来) | M-δ | S5 干预 + 回档 |
| (未来) | M-ε | M4 UI 接入 |
