"""v0.7 配置层

- config_loader.py: 读 .llm_api_key + 解析 agents.json
- agents.json:      模型池 + agent→model 路由表
"""
from realtime_novel.config.config_loader import (
    load_llm_api_key,
    load_agents_config,
    get_model_config,
    get_agent_model,
    get_exploration_level_config,
)

__all__ = [
    "load_llm_api_key",
    "load_agents_config",
    "get_model_config",
    "get_agent_model",
    "get_exploration_level_config",
]
