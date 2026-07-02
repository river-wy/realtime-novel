"""配置加载器

职责：
1. 读工程根目录的 .llm_api_key（gitignored），解析 api_key 真值
2. 加载 backend/config/agents.json（模型池 + agent→model 路由表）
3. 提供便捷查询接口

key 文件格式（只接受标准 JSON）：
{
  "FRIDAY_API_KEY": "21899390080843030554"
}

friday 前缀表示「提供方」(model namespace)，未来会接 deepseek/,minimax/ 原生
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# 工程根目录 = config_loader.py 上 4 级
# backend/config/config_loader.py → backend/config → backend → 工程根
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

AGENTS_CONFIG_PATH = Path(__file__).resolve().parent / "agents.json"
LLM_API_KEY_PATH = PROJECT_ROOT / ".llm_api_key"

# 缓存
_agents_config_cache: Optional[dict[str, Any]] = None
_llm_api_key_cache: Optional[str] = None


class ConfigError(RuntimeError):
    """配置错误（缺文件 / 解析失败 / 字段缺失）"""


def load_llm_api_key(path: Path = LLM_API_KEY_PATH) -> str:
    """从 .llm_api_key 文件读 api_key 真值

    只接受标准 JSON 格式：
    {
      "FRIDAY_API_KEY": "21899390080843030554"
    }
    """
    global _llm_api_key_cache
    if _llm_api_key_cache is not None:
        return _llm_api_key_cache

    if not path.exists():
        raise ConfigError(
            f".llm_api_key 文件不存在: {path}\n"
            f"  创建示例: echo '{{\"FRIDAY_API_KEY\":\"your_key\"}}' > {path} && chmod 600 {path}"
        )
    if path.stat().st_size == 0:
        raise ConfigError(f".llm_api_key 文件为空: {path}")

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise ConfigError(f".llm_api_key 文件内容为空: {path}")

    # 收紧：只接受标准 JSON 格式（外层必须是 {）
    if not raw.startswith("{"):
        raise ConfigError(
            f".llm_api_key 必须是标准 JSON 格式（以 {{ 开头）\n"
            f"  当前内容: {raw[:100]}\n"
            f"  正确格式: {{\"FRIDAY_API_KEY\": \"your_key\"}}"
        )

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(
            f".llm_api_key JSON 解析失败: {e}\n  原始内容: {raw[:200]}"
        ) from e

    if not isinstance(obj, dict):
        raise ConfigError(
            f".llm_api_key JSON 顶层必须是对象 (dict)，当前是 {type(obj).__name__}\n"
            f"  正确格式: {{\"FRIDAY_API_KEY\": \"your_key\"}}"
        )

    # 查找 key 字段（按优先级）
    api_key: Optional[str] = None
    for key in ("FRIDAY_API_KEY", "friday_api_key", "api_key", "key"):
        if key in obj:
            value = obj[key]
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ConfigError(
                    f".llm_api_key 字段 {key!r} 为空\n"
                    f"  请填入 friday API key 真值"
                )
            api_key = str(value).strip()
            break

    if api_key is None:
        raise ConfigError(
            f".llm_api_key 未找到 key 字段 (尝试: FRIDAY_API_KEY / friday_api_key / api_key / key)\n"
            f"  当前 keys: {list(obj.keys())}"
        )

    # 校验纯 ASCII (防止 '…' 之类字符炸 ascii codec)
    if not all(ord(c) < 128 for c in api_key):
        raise ConfigError(
            f".llm_api_key 包含非 ASCII 字符 (key 必须是纯 ASCII)\n"
            f"  当前 key: {api_key!r}"
        )

    _llm_api_key_cache = api_key
    return api_key


def load_agents_config(path: Path = AGENTS_CONFIG_PATH) -> dict[str, Any]:
    """加载 agents.json 配置（带缓存）"""
    global _agents_config_cache
    if _agents_config_cache is not None:
        return _agents_config_cache

    if not path.exists():
        raise ConfigError(f"agents.json 不存在: {path}")

    with path.open(encoding="utf-8") as f:
        cfg = json.load(f)

    if "models" not in cfg or "agents" not in cfg:
        raise ConfigError(
            f"agents.json 缺少 models / agents 字段: {path}\n  当前 keys: {list(cfg.keys())}"
        )

    _agents_config_cache = cfg
    return cfg


def reset_cache() -> None:
    """清缓存（测试用）"""
    global _agents_config_cache, _llm_api_key_cache
    _agents_config_cache = None
    _llm_api_key_cache = None


def get_model_config(model_name: str) -> dict[str, Any]:
    """根据 model 名查模型配置

    Args:
        model_name: 如 "friday/deepseek-v4-pro-tencent"

    Returns:
        models.<model_name> 字典
    """
    cfg = load_agents_config()
    models = cfg["models"]
    if model_name not in models:
        raise ConfigError(
            f"未在 agents.json 中找到 model={model_name!r}\n"
            f"  可用 models: {list(models.keys())}"
        )
    return models[model_name]


def get_agent_model(agent_name: str) -> str:
    """查 agent 配置的 model

    Args:
        agent_name: 如 "OnboardingAgent"

    Returns:
        model 名（如 "friday/deepseek-v4-pro-tencent"）
    """
    cfg = load_agents_config()
    agents = cfg["agents"]
    if agent_name not in agents:
        raise ConfigError(
            f"未在 agents.json 中找到 agent={agent_name!r}\n"
            f"  可用 agents: {list(agents.keys())}"
        )
    return agents[agent_name]["model"]


def get_exploration_level_config(level: str) -> dict[str, Any]:
    """查探索度档位配置 (conservative/standard/wild)

    Returns:
        {
          "temperature": 0.6 | 0.85 | 1.05,
          "max_tokens": 8192,
          "frequency_penalty": 0.1 | 0.3 | 0.5,
          "supplement_aggressiveness": "low" | "medium" | "high",
          "description": "..."
        }
    """
    cfg = load_agents_config()
    levels = cfg.get("exploration_levels")
    if not levels:
        raise ConfigError(
            "agents.json 缺少 exploration_levels 字段\n"
            f"  当前顶层 keys: {list(cfg.keys())}"
        )
    if level not in levels:
        raise ConfigError(
            f"未在 agents.json 中找到 exploration_level={level!r}\n"
            f"  可用 levels: {list(levels.keys())}"
        )
    return levels[level]
