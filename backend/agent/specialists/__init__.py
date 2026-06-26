"""specialists — 内部专家工具（v0.6.2 重塑，删除旧 specialists.py）

v0.6.2 重构：
- 删除旧的 ChapterGeneratorSpecialist / WorldTreeKeeperSpecialist / MemoryKeeperSpecialist
- 删除 SpecialistAgent ABC + 3 个 Stub 别名 + ImageGeneratorStub
- 删除 generate_chapter_via_specialist() 函数
- 所有能力迁移到 Agent 工具：
  - 章节生成：tools.chapter_tools.GenerateChapterTool（落盘） + tools.summarize_chapter_tool.SummarizeChapterTool
  - 世界树管理：agents.world_tree_manager.WorldTreeManager（ReAct loop）
  - 记忆检索：tools.memory_tools.SearchMemoryTool
  - 章节生成上下文：agents.novel_writer.NovelWriter（ReAct loop）
- 委托入口：agents.novel_writer.delegate_chapter_generation()（统一 3 个触发源）

保留的工具/能力：
- chapter_summarizer: 章节 summary 抽取（sentinel 解析 + fallback）
- exploration: 探索度参数（conservative/standard/wild）+ 三级覆盖

注: style_inference.py 在 context/ 下（不属于本模块）。
"""