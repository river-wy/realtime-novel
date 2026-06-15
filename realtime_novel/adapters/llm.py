"""adapters/llm_lunaris.py — LLM 客户端（完全独立，零外部依赖）

设计原则（2026-06-15 欧尼酱定调）:
1. 完全独立 — 不引用 lunaris 任何代码
2. 默认从本工程 ./config.private.json 读 llm 段
3. 环境变量 LLM_CONFIG_PATH 可覆盖路径
4. 默认模型: deepseek-v4-pro
5. 走 OpenAI 兼容协议 + certifi 绕过 macOS SSL

注意: 文件名 llm_lunaris.py 是历史命名（曾复用 lunaris call_llm 风格实现）。
实际已与 lunaris 零关系。改名建议暂缓以减少 diff。
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.request
from pathlib import Path
from typing import Optional

try:
    import certifi
except ImportError:
    certifi = None

from ..core.exceptions import (
    ConfigError,
    LLMError,
    LLMEmptyResponseError,
)


# === 配置加载 ===

_CONFIG_CACHE: dict = {}


def _find_config_path() -> Path:
    """查找 config.private.json — 优先级:
    1. 环境变量 LLM_CONFIG_PATH
    2. 工程根下的 config.private.json
    3. ./config.private.json（cwd）
    """
    env_path = os.environ.get("LLM_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if not p.exists():
            raise ConfigError(
                f"LLM_CONFIG_PATH={env_path} 不存在"
            )
        return p

    # 工程根（adapters/llm_lunaris.py → 往上 3 级到工程根）
    project_root = Path(__file__).resolve().parents[2]
    project_config = project_root / "config.private.json"
    if project_config.exists():
        return project_config

    # CWD 兜底
    cwd_config = Path("config.private.json").resolve()
    if cwd_config.exists():
        return cwd_config

    raise ConfigError(
        "找不到 config.private.json。请:\n"
        "  1. 在工程根放一份 config.private.json（含 llm 段）\n"
        "  2. 或设置环境变量 LLM_CONFIG_PATH 指向你的配置"
    )


def get_llm_config(reload: bool = False) -> dict:
    """读取 LLM 配置（config.private.json: llm 段）"""
    if _CONFIG_CACHE and not reload:
        return _CONFIG_CACHE

    config_path = _find_config_path()
    data = json.loads(config_path.read_text(encoding="utf-8"))

    if "llm" not in data:
        raise ConfigError(
            f"{config_path} 缺少 'llm' 段。需要 baseUrl / apiKey / default_model"
        )

    _CONFIG_CACHE.update(data)
    return data


# === SSL 上下文 ===

def _build_ssl_context() -> ssl.SSLContext:
    """macOS 系统 openssl 证书目录可能为空，强制用 certifi"""
    if certifi is None:
        raise ConfigError(
            "certifi 未安装, 请 pip install certifi"
        )
    return ssl.create_default_context(cafile=certifi.where())


# === Headers + Payload ===

def _build_headers(api_key: str, extra: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    headers.update(extra or {})
    return headers


def _build_payload(
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system_msg: Optional[str],
    use_json_format: bool,
) -> dict:
    """组装 OpenAI 兼容协议的 chat/completions 请求体"""
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if use_json_format:
        # OpenAI 兼容: response_format=json_object 强制 JSON 输出
        # 注: deepseek-v4-pro 兼容此协议
        payload["response_format"] = {"type": "json_object"}
    return payload


def _parse_response(raw: str) -> str:
    """从 OpenAI 兼容响应中抽 content"""
    data = json.loads(raw)
    if "choices" not in data or not data["choices"]:
        raise LLMError(f"LLM 响应无 choices: {raw[:500]}")
    return data["choices"][0].get("message", {}).get("content", "")


# === 主入口 ===

def call_llm(
    prompt: str,
    *,
    system_msg: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 6144,
    temperature: float = 0.7,
    use_json_format: bool = False,
    timeout: int = 180,
) -> str:
    """LLM 调用入口

    Args:
        prompt: user 消息
        system_msg: 选填，强约束 system 消息
        model: 选填，默认从 config.private.json 读 default_model (deepseek-v4-pro)
        max_tokens: 默认 6144
        temperature: 默认 0.7（章节生成需要一定随机性）
        use_json_format: 默认 False（章节是散文）。摘要提取时传 True。
        timeout: HTTP 超时秒数

    Returns:
        assistant content 字符串

    Raises:
        ConfigError: 配置缺失
        LLMError: 调用失败
        LLMEmptyResponseError: 返回空 content
    """
    cfg = get_llm_config()["llm"]

    # 默认模型
    actual_model = model or cfg.get("default_model", "deepseek-v4-pro")

    # JSON 模式预检（OpenAI 协议要求 prompt 中含 "json" 字眼）
    if use_json_format:
        combined = (system_msg or "") + "\n" + prompt
        if "json" not in combined.lower():
            raise LLMError(
                "use_json_format=True 但 prompt/system 中不含 'json' 字眼, "
                "请在 prompt 或 system_msg 中明确写 'JSON', "
                "或改用 use_json_format=False."
            )

    payload = _build_payload(
        prompt=prompt,
        model=actual_model,
        max_tokens=max_tokens,
        temperature=temperature,
        system_msg=system_msg,
        use_json_format=use_json_format,
    )
    headers = _build_headers(cfg["apiKey"], cfg.get("extra_headers", {}))
    ssl_ctx = _build_ssl_context()

    base_url = (cfg.get("baseUrl") or "").rstrip("/")
    url = f"{base_url}/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        raise LLMError(f"LLM 调用失败: {type(e).__name__}: {e}") from e

    content = _parse_response(raw)
    if not content:
        raise LLMEmptyResponseError(
            f"LLM 返回空 content (model={actual_model}, max_tokens={max_tokens}, "
            f"use_json_format={use_json_format}).\n"
            f"raw 前 500: {raw[:500]}"
        )
    return content


# === CLI 自检入口 ===

if __name__ == "__main__":
    print("=" * 60)
    print("  realtime_novel · LLM 客户端自检")
    print("=" * 60)

    try:
        cfg = get_llm_config()["llm"]
        print(f"  ✓ 配置加载成功")
        print(f"    · baseUrl: {cfg.get('baseUrl', '?')}")
        print(f"    · default_model: {cfg.get('default_model', '?')}")
        print(f"    · apiKey: {cfg.get('apiKey', '?')[:8]}...")
    except ConfigError as e:
        print(f"  ✗ 配置失败: {e}")
        raise SystemExit(1)

    print()
    print("  🚀 ping LLM ...")
    result = call_llm(
        "回复 OK 即可",
        system_msg="你是测试机器人",
        max_tokens=20,
        temperature=0.3,
        use_json_format=False,
        timeout=30,
    )
    print(f"  ✓ ping 成功，LLM 响应: {result.strip()!r}")
