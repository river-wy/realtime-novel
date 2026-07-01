"""session_cache — Agent 会话上下文缓存

为管家和两个专家 Agent 维护跨调用的 messages 缓存。

Cache 内 messages 布局：
    index 0  → {"role":"system", "content": sys_prompt + tools}  ← 固定头，可原地替换
    index 1  → {"role":"system", "content": "[上下文] ..."}       ← 可选，项目上下文段
    index 2+ → 历史对话轮次 (user/assistant/tool)

关键行为：
- sys_prompt 变化（project 切换等）→ 只替换 index 0，保留对话历史
- 上下文（context_msg）变化       → 只替换 index 1，不动其他
- 每轮结束后 append delta（user + tool chain + final_assistant）
- used_tokens 超过 context_window * COMPRESS_THRESHOLD → 异步触发 summary 压缩
- TTL 超时（24h）                                      → 整体 rebuild
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# ── 配置常量 ──────────────────────────────────────────────────────────────────

# cache TTL（秒）：超过此时间没有活动则视为过期
CACHE_TTL_SECONDS = 86400           # 24 小时

# 压缩触发阈值：used_tokens 超过 context_window 的该比例时触发 summary 压缩
COMPRESS_THRESHOLD = 0.70

# 默认 context_window（没有配置时的 fallback）
DEFAULT_CONTEXT_WINDOW = 128000

# summary 压缩后保留的最新轮数
KEEP_RECENT_ROUNDS = 10     # v0.9.3 欧尼酱拍板：20 → 10（更激进压缩，节省 token）

# tool 返回内容最大字节数；超过时截断
TOOL_RESULT_MAX_BYTES = 10 * 1024   # 10 KB


# ── Cache 数据结构 ─────────────────────────────────────────────────────────────

@dataclass
class AgentSessionCache:
    """单个 Agent 会话的 messages 缓存

    messages[0]  → sys_prompt 段（必有）
    messages[1]  → context 段（可选，role=system，content 以 "[上下文]" 开头）
    messages[2+] → 对话历史
    """
    key: str
    agent_name: str
    user_id: str
    conversation_id: str
    messages: List[dict] = field(default_factory=list)
    sys_prompt_hash: str = ""          # 用于检测 sys_prompt 是否变化
    has_context_segment: bool = False  # messages[1] 是否是 context 段
    context_window: int = DEFAULT_CONTEXT_WINDOW  # 模型最大 token 数（从 agents.json 读取）
    used_tokens: int = 0               # 本会话已累计使用的 token 数
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)

    # ── 基础操作 ──

    def is_expired(self, ttl: float = CACHE_TTL_SECONDS) -> bool:
        return (time.time() - self.last_used_at) > ttl

    def touch(self) -> None:
        self.last_used_at = time.time()

    def add_tokens(self, tokens: int) -> None:
        """当前轮 LLM 返回后累加 token 用量"""
        self.used_tokens += tokens
        self.touch()

    def needs_summary(self) -> bool:
        """used_tokens 超过 context_window 的 70% 时触发压缩"""
        return self.used_tokens >= self.context_window * COMPRESS_THRESHOLD

    def append_delta(self, delta: List[dict]) -> None:
        """追加本轮新增 messages delta（本轮 user + tool chain + final_assistant）"""
        self.messages.extend(delta)
        self.touch()

    # ── sys_prompt 原地更新 ──

    def patch_sys_prompt(self, new_sys_prompt: str) -> None:
        """sys_prompt 变化时原地替换 messages[0]，保留对话历史"""
        if self.messages:
            self.messages[0] = {"role": "system", "content": new_sys_prompt}
            self.sys_prompt_hash = _hash_str(new_sys_prompt)
            log.info("SessionCache: patch sys_prompt，key=%s", self.key)
        self.touch()

    # ── context 段管理（messages[1]）──

    def _context_index(self) -> int:
        """context 段的 index（1 或不存在）"""
        return 1 if self.has_context_segment else -1

    def patch_context(self, context_content: str) -> None:
        """更新 context 段（messages[1]）；不存在时插入"""
        ctx_msg = {"role": "system", "content": f"[上下文]\n{context_content}"}
        if self.has_context_segment and len(self.messages) > 1:
            self.messages[1] = ctx_msg
            log.debug("SessionCache: patch context 段，key=%s", self.key)
        else:
            # 插入到 messages[0] 之后
            self.messages.insert(1, ctx_msg)
            self.has_context_segment = True
            log.info("SessionCache: 插入 context 段，key=%s", self.key)
        self.touch()

    def dialogue_start_index(self) -> int:
        """对话历史起始 index（跳过所有 system 段）"""
        return 2 if self.has_context_segment else 1

    def get_dialogue_messages(self) -> List[dict]:
        """返回对话历史部分（不含 sys/context 段）"""
        return self.messages[self.dialogue_start_index():]


# ── Cache Manager ──────────────────────────────────────────────────────────────

class SessionCacheManager:
    """进程内 Agent 会话缓存管理器（单例）

    线程安全：asyncio 单线程，无需锁。
    """

    def __init__(self):
        self._store: Dict[str, AgentSessionCache] = {}

    @staticmethod
    def make_key(user_id: str, conversation_id: str, agent_name: str) -> str:
        return f"{user_id}:{conversation_id}:{agent_name}"

    def get(
        self,
        user_id: str,
        conversation_id: str,
        agent_name: str,
        sys_prompt: str,
    ) -> Optional[AgentSessionCache]:
        """获取 cache。

        - TTL 过期 → 返回 None（触发全量 rebuild）
        - sys_prompt 变化 → 原地 patch，返回 cache（保留对话历史）
        - 命中 → 返回 cache
        """
        key = self.make_key(user_id, conversation_id, agent_name)
        cache = self._store.get(key)
        if cache is None:
            return None

        if cache.is_expired():
            log.info("SessionCache: TTL 过期，key=%s", key)
            del self._store[key]
            return None

        # sys_prompt 变化：原地替换 messages[0]，对话历史保留
        new_hash = _hash_str(sys_prompt)
        if cache.sys_prompt_hash != new_hash:
            log.info("SessionCache: sys_prompt 变化，patch messages[0]，key=%s", key)
            cache.patch_sys_prompt(sys_prompt)

        cache.touch()
        return cache

    def create(
        self,
        user_id: str,
        conversation_id: str,
        agent_name: str,
        sys_prompt: str,
        initial_messages: List[dict],
        context_window: int = DEFAULT_CONTEXT_WINDOW,
    ) -> AgentSessionCache:
        """创建新 cache（全量 rebuild 路径）"""
        key = self.make_key(user_id, conversation_id, agent_name)
        cache = AgentSessionCache(
            key=key,
            agent_name=agent_name,
            user_id=user_id,
            conversation_id=conversation_id,
            messages=list(initial_messages),
            sys_prompt_hash=_hash_str(sys_prompt),
            context_window=context_window,
        )
        self._store[key] = cache
        log.info(
            "SessionCache: 新建 cache，key=%s，initial_messages=%d，context_window=%d",
            key, len(initial_messages), context_window,
        )
        return cache

    def invalidate(self, user_id: str, conversation_id: str, agent_name: str) -> None:
        """主动销毁 cache（切换 conversation / Onboarding 完成 / 用户新建对话等事件触发）"""
        key = self.make_key(user_id, conversation_id, agent_name)
        if key in self._store:
            del self._store[key]
            log.info("SessionCache: 主动 invalidate，key=%s", key)

    def invalidate_user(self, user_id: str) -> None:
        """销毁某用户的所有 cache"""
        keys = [k for k in self._store if k.startswith(f"{user_id}:")]
        for k in keys:
            del self._store[k]
        if keys:
            log.info("SessionCache: invalidate_user，user_id=%s，cleared=%d", user_id, len(keys))

    def invalidate_conversation(self, conversation_id: str) -> None:
        """销毁某 conversation 的所有 cache（新建对话时调用）"""
        keys = [k for k in self._store if f":{conversation_id}:" in k]
        for k in keys:
            del self._store[k]
        if keys:
            log.info("SessionCache: invalidate_conversation，conv_id=%s，cleared=%d", conversation_id, len(keys))

    def has_valid_cache(self, user_id: str, conversation_id: str, agent_name: str) -> bool:
        """轻量检查：key 是否有有效 cache（不校验 sys_prompt hash，仅 TTL）
        用于调用方决定是否跳过 DB history 加载。
        """
        key = self.make_key(user_id, conversation_id, agent_name)
        cache = self._store.get(key)
        return cache is not None and not cache.is_expired()

    def get_without_prompt_check(
        self,
        user_id: str,
        conversation_id: str,
        agent_name: str,
    ) -> Optional[AgentSessionCache]:
        """获取 cache（仅 TTL 检查，不做 sys_prompt hash 校验 / patch）。

        供 executor cache HIT 路径使用：调用方已通过 has_valid_cache 确认命中，
        不需要重新组装 system_prompt，因此跳过 hash 比对直接返回对象。
        """
        key = self.make_key(user_id, conversation_id, agent_name)
        cache = self._store.get(key)
        if cache is None:
            return None
        if cache.is_expired():
            log.info("SessionCache: TTL 过期，key=%s", key)
            del self._store[key]
            return None
        cache.touch()
        return cache

    def stats(self) -> dict:
        """调试用：返回当前 cache 统计"""
        return {
            "total_caches": len(self._store),
            "keys": list(self._store.keys()),
            "round_counts": {k: v.round_count() for k, v in self._store.items()},
        }

    async def maybe_compress(
        self,
        cache: AgentSessionCache,
        llm_adapter=None,
    ) -> None:
        """对话轮数超过 MAX_ROUNDS 时异步触发 summary 压缩（不阻塞主流程）

        压缩策略：
        1. 保留 sys 段（messages[0]）和 context 段（messages[1]，如有）
        2. 对话历史中保留最近 KEEP_RECENT_ROUNDS 轮，其余调 LLM 生成摘要
        3. 用一条 system 摘要消息替换被压缩的部分
        """
        if not cache.needs_summary():
            return
        if llm_adapter is None:
            from backend.adapters.llm_adapter import get_llm_adapter
            llm_adapter = get_llm_adapter()

        log.info(
            "SessionCache: 触发 summary 压缩，key=%s，rounds=%d",
            cache.key, cache.round_count(),
        )

        dialogue = cache.get_dialogue_messages()

        # 按 user/assistant 配对，保留最近 KEEP_RECENT_ROUNDS 轮
        # 简单实现：找最近 KEEP_RECENT_ROUNDS 个 user 消息的起始 index
        user_indices = [i for i, m in enumerate(dialogue) if m.get("role") == "user"]
        if len(user_indices) <= KEEP_RECENT_ROUNDS:
            return  # 不够压缩

        keep_start = user_indices[-KEEP_RECENT_ROUNDS]
        to_compress = dialogue[:keep_start]
        keep_recent = dialogue[keep_start:]

        summary_text = await _generate_summary(llm_adapter, to_compress)
        if not summary_text:
            log.warning("SessionCache: summary 生成失败，跳过压缩，key=%s", cache.key)
            return

        summary_msg = {
            "role": "system",
            "content": f"[历史对话摘要（已压缩 {len(to_compress)} 条）]\n{summary_text}",
        }

        # 重建：保留 sys + context 段 + summary + 最近轮次
        head_count = cache.dialogue_start_index()
        cache.messages = cache.messages[:head_count] + [summary_msg] + keep_recent
        log.info(
            "SessionCache: 压缩完成，key=%s，压缩前对话=%d条，压缩后=%d条",
            cache.key, len(to_compress), len(cache.messages),
        )


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_cache_manager: Optional[SessionCacheManager] = None


def get_session_cache_manager() -> SessionCacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = SessionCacheManager()
    return _cache_manager


# ── 私有工具函数 ──────────────────────────────────────────────────────────────

def _hash_str(s: str) -> str:
    return hashlib.md5(s.encode(), usedforsecurity=False).hexdigest()[:12]


def truncate_tool_result(content: str, max_bytes: int = TOOL_RESULT_MAX_BYTES) -> str:
    """tool 返回内容超长时截断，追加截断提示"""
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return content
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    log.warning(
        "SessionCache.truncate_tool_result: 内容超过 %d KB，已截断（原始 %d bytes）",
        max_bytes // 1024, len(encoded),
    )
    return truncated + f"\n...[内容超长，已截断，原始 {len(encoded)} bytes，保留前 {max_bytes} bytes]"


async def _generate_summary(llm_adapter, messages: List[dict]) -> str:
    """调 LLM 生成对话摘要"""
    from backend.adapters.types import LLMRequest, ModelRole

    lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""
        if role == "user":
            lines.append(f"用户：{content[:300]}")
        elif role == "assistant":
            # v0.9.4 修复：不再硬编码「管家」—— assistant 可能是 管家/WTM/文笔家/Validator
            lines.append(f"AI：{content[:300]}")
        elif role == "tool":
            name = m.get("name", "tool")
            lines.append(f"工具({name})：{content[:150]}")

    if not lines:
        return ""

    dialogue_text = "\n".join(lines)
    try:
        resp = await llm_adapter.complete(LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": "你是对话摘要助手。请用 3-5 句话概括以下对话的关键信息（用户意图、已完成的步骤、重要设定）。",
                },
                {
                    "role": "user",
                    "content": f"请摘要以下对话：\n\n{dialogue_text}",
                },
            ],
            max_tokens=512,
            temperature=0.3,
            role=ModelRole.TEXT,
        ))
        return resp.content or ""
    except Exception as e:
        log.warning("_generate_summary: LLM 调用失败: %s", e)
        return ""

