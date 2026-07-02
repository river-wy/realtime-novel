"""backend.agent.tools 包入口

工具清单（按文件分组）：
- project_tools:      load_project / create_project / delete_project
- chapter_tools:      generate_chapter / read_chapter
- base_edit_tools:    update_base / rollback_base
- image_tools:        generate_image
- style_tools:        list_style_packs / adjust_style
- pov_tools:          switch_pov
- character_tools:    introspect_character
- plot_tools:         weave_plot
- edit_artifact_tool: edit_artifact
- onboarding_tools:   verify_world_tree_baseline
- delegation_tools:   delegate_to_agent / dispatch_background_task
- summarize_chapter_tool: summarize_chapter
- exploration_tools:  update_exploration_level
- volume_tools:       generate_volume_summary
"""
# 触发工具注册（side-effect import）—— 顺序不重要，注册到全局 _tools dict
from backend.agent.tools import (
    base, schemas, locks,
    project_tools, chapter_tools, base_edit_tools,
    image_tools,
    style_tools, pov_tools, character_tools, plot_tools,
    edit_artifact_tool,
    onboarding_tools,
    delegation_tools,
    summarize_chapter_tool,
    exploration_tools,
    volume_tools,
)
from backend.agent.tools.base import (
    BaseTool, ToolError, register_tool, get_tool, list_tools, reset_tools,
)

__all__ = [
    "BaseTool", "ToolError", "register_tool", "get_tool", "list_tools", "reset_tools",
]
