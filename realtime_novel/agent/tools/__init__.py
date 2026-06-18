"""realtime_novel.agent.tools 包入口

14 个 LangGraph 工具（v0.6 拆分版）：
- 3 个 project: load_project / create_project / delete_project (project_tools.py)
- 2 个 chapter: generate_chapter / read_chapter (chapter_tools.py)
- 2 个 base_edit: update_base / rollback_base (base_edit_tools.py)
- 1 个 image: generate_image (image_tools.py)
- 1 个 memory: search_memory (memory_tools.py)
- 4 个 v0.4 新（v0.6 拆分）: adjust_style / switch_pov / introspect_character / weave_plot
  - adjust_style: style_tools.py
  - switch_pov: pov_tools.py
  - introspect_character: character_tools.py
  - weave_plot: plot_tools.py
- 1 个 v0.4.1 新: edit_artifact (edit_artifact_tool.py)

v0.6 变更：v0_4_new_tools.py 删除（命名带版本号不规范），4 个工具按功能拆成 4 文件
"""
# 触发工具注册（side-effect import）
from realtime_novel.agent.tools import (
    base, schemas, locks,
    project_tools, chapter_tools, base_edit_tools,
    image_tools, memory_tools,
    style_tools, pov_tools, character_tools, plot_tools,
    edit_artifact_tool,
)
from realtime_novel.agent.tools.base import (
    BaseTool, ToolError, register_tool, get_tool, list_tools, reset_tools,
)

__all__ = [
    "BaseTool", "ToolError", "register_tool", "get_tool", "list_tools", "reset_tools",
]
