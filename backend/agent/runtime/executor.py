"""agent_executor — Agent ReAct loop 执行器

职责：
1. 加载 Agent 的可用工具集
2. 拼 system_prompt（含可用工具列表 + 职责 + 上下文）
3. 调 LLM（注入 tools 参数）
4. 解析 LLM 输出：
   - 有 tool_calls → 执行 tool → 把结果拼回 messages → 继续循环
   - 无 tool_calls → LLM 输出 final_response → 退出
5. 退出条件：final_response / max_iterations / 死循环检测
6. 后置节点插槽：execute() 完成后依次运行注册的 middleware

后置节点（Middleware）机制：
    executor = get_agent_executor()

    # 注册全局后置节点（对所有 Agent 生效）
    @executor.middleware()
    async def safety_check(output: AgentOutput, context: dict) -> AgentOutput:
        if contains_sensitive(output.final_response):
            output.final_response = "[已过滤]"
        return output

    # 注册 Agent 专属后置节点
    @executor.middleware(agent_name="novel_writer")
    async def word_count_check(output: AgentOutput, context: dict) -> AgentOutput:
        if len(output.final_response) < 500:
            output.structured_data["quality_warn"] = "章节字数不足"
        return output
"""
from __future__ import annotations

import asyncio
import json
import time
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Callable, Awaitable

from backend.adapters.llm_adapter import get_llm_adapter
from backend.adapters.types import LLMRequest, ModelRole
from backend.agent.runtime.session_cache import truncate_tool_result
from backend.agent.tools.base import BaseTool, ToolError
from backend.agent.tools.registry import (
    get_tool_registry,
    make_tool_message,
    ToolRegistry,
)
from backend.utils.logger import logger as logger_decorator


# ============ Agent 配置 ============

class AgentConfig(BaseModel):
    """Agent 配置（系统提示 + Agent 名）"""
    agent_name: str  # novel_steward / novel_writer / world_tree_manager
    system_prompt: str  # 主体职责描述
    # 可选：追加特殊工具（Onboarding 期间管家临时加 generate_chapter 等）
    extra_tools: List[str] = Field(default_factory=list)


# ============ 执行结果 ============

class AgentOutput(BaseModel):
    """Agent 执行结果（标准化 NodeResult）

    final_response：LLM 输出的自然语言回复
    structured_data：工具调用产生的结构化数据（由 tool / middleware 写入）
    tool_calls_history：完整 tool 调用链路（含 iteration / args / result / status）
    """
    final_response: str = ""
    structured_data: dict = Field(
        default_factory=dict,
        description="结构化数据（章节内容 / WorldTreeDiff / 项目列表等），由 tool 或后置 middleware 写入",
    )
    tool_calls_history: List[dict] = Field(default_factory=list)
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None
    # 流程控制（后置节点可写入）
    needs_review: bool = False          # 需要人工审核
    skip_response: bool = False         # 后置节点决定拦截（不回复用户）


# Middleware 类型：async fn(output: AgentOutput, context: dict) -> AgentOutput
# 用 Any 避免部分 linter 对 Callable + Awaitable 组合类型的误报
MiddlewareFn = Any  # Callable[[AgentOutput, dict], Awaitable[AgentOutput]]


# ============ Agent Executor ============

@logger_decorator
class AgentExecutor:
    """Agent ReAct loop 执行器

    使用方式：
        executor = AgentExecutor()
        output = await executor.execute(
            agent=AgentConfig(
                agent_name="world_tree_manager",
                system_prompt="你是世界树管理...",
            ),
            user_message="把主角的师父改成反派",
            project_id="proj-123",
        )
        # output.final_response = "我理解你想..."

    注册后置节点（Middleware）：
        @executor.middleware()                         # 对所有 Agent 生效
        async def safety(output, ctx): ...

        @executor.middleware(agent_name="novel_writer")  # 仅对文笔家生效
        async def quality(output, ctx): ...
    """

    def __init__(self, llm_adapter=None, tool_registry: Optional[ToolRegistry] = None):
        self.llm = llm_adapter or get_llm_adapter()
        self.registry = tool_registry or get_tool_registry()
        # 后置节点表：None key = 全局（对所有 Agent 生效）
        self._middlewares: Dict[Optional[str], List[MiddlewareFn]] = {}

    # ── 后置节点注册 ─────────────────────────────────

    def middleware(
        self,
        agent_name: Optional[str] = None,
    ) -> Callable[[MiddlewareFn], MiddlewareFn]:  # type: ignore[type-arg]
        """装饰器：注册后置节点（Middleware）

        Args:
            agent_name: 指定 Agent 名时只对该 Agent 生效；None = 全局生效

        用法：
            @executor.middleware()
            async def safety_check(output: AgentOutput, context: dict) -> AgentOutput:
                ...
                return output

            @executor.middleware(agent_name="novel_writer")
            async def word_count(output: AgentOutput, context: dict) -> AgentOutput:
                ...
                return output
        """
        def decorator(fn: MiddlewareFn) -> MiddlewareFn:
            key = agent_name  # None = 全局
            if key not in self._middlewares:
                self._middlewares[key] = []
            self._middlewares[key].append(fn)
            self.log.debug(
                "AgentExecutor: registered middleware '%s.%s' for agent=%s",
                fn.__module__, fn.__qualname__, agent_name or "*",
            )
            return fn
        return decorator

    def add_middleware(
        self,
        fn: MiddlewareFn,
        agent_name: Optional[str] = None,
    ) -> None:
        """编程式注册 middleware（非装饰器场景）"""
        key = agent_name
        if key not in self._middlewares:
            self._middlewares[key] = []
        self._middlewares[key].append(fn)
        self.log.debug(
            "AgentExecutor: added middleware '%s.%s' for agent=%s",
            fn.__module__, fn.__qualname__, agent_name or "*",
        )

    async def _run_middlewares(
        self,
        agent_name: str,
        output: AgentOutput,
        context: dict,
    ) -> AgentOutput:
        """依次执行全局 middleware + agent 专属 middleware

        顺序：全局（注册顺序）→ agent 专属（注册顺序）
        单个 middleware 抛异常时打 WARNING 并跳过，不中断后续
        """
        mw_global = self._middlewares.get(None, [])
        mw_agent = self._middlewares.get(agent_name, [])

        for mw in mw_global + mw_agent:
            try:
                output = await mw(output, context)
            except Exception as e:
                self.log.warning(
                    "AgentExecutor._run_middlewares: middleware '%s.%s' 失败 (跳过): %s",
                    mw.__module__, mw.__qualname__, e,
                    exc_info=True,
                )
        return output

    async def execute(
        self,
        agent: AgentConfig,
        user_message: str,
        project_id: Optional[str] = None,
        context: Optional[dict] = None,
        context_message: Optional[str] = None,
        history: Optional[List[dict]] = None,
        session_key: Optional[str] = None,
        max_iterations: int = 15,
    ) -> AgentOutput:
        """执行 Agent ReAct 推演 loop

        Args:
            agent: Agent 配置（agent_name + system_prompt + 可选 extra_tools）
            user_message: 用户消息（首轮 user 消息）
            project_id: 项目 ID（注入到 context_block）
            context: 额外上下文 dict（注入到 system_prompt 的 context_block）
            context_message: 预注入的上下文 user message（7 件基座 + 章节摘要等），
                作为独立 user message 插入到 system 和 user_message 之间
            history: cache miss 时由调用方提供的历史 messages（用于 rebuild）
            session_key: cache key（"user_id:conv_id:agent_name"）；
                传入时启用 session cache，hit 则复用 cache，miss 则用 history rebuild
            max_iterations: 最大循环轮次（默认 15）

        Returns:
            AgentOutput
        """
        start = time.time()

        self.log.info(
            "AgentExecutor.execute START: agent=%s, project_id=%s, "
            "max_iterations=%d, msg_len=%d",
            agent.agent_name, project_id, max_iterations, len(user_message or ""),
        )

        # 1. 加载工具集（基础 + 临时扩展）
        tool_instances = self.registry.get_agent_tools(agent.agent_name)
        if agent.extra_tools:
            from backend.agent.tools.base import get_tool
            for name in agent.extra_tools:
                try:
                    tool_instances.append(get_tool(name))
                except KeyError:
                    self.log.warning(
                        "AgentExecutor.execute: extra_tool '%s' 未注册, agent=%s",
                        name, agent.agent_name,
                    )

        openai_tools = self.registry.to_openai_tools(agent.agent_name)
        if agent.extra_tools:
            from backend.agent.tools.base import get_tool
            for name in agent.extra_tools:
                try:
                    inst = get_tool(name)
                    # 转 OpenAI schema
                    from backend.agent.tools.registry import _base_tool_to_openai
                    openai_tools.append(_base_tool_to_openai(inst))
                except KeyError:
                    pass

        self.log.debug(
            "AgentExecutor.execute: agent=%s, tools=%s",
            agent.agent_name, [t.name for t in tool_instances],
        )

        # 2 & 3. 拼 system_prompt + 初始化 messages（cache hit / miss 两条路径）
        messages: List[dict]
        session_cache_obj = None
        messages_base_len = 0  # 本轮开始前 messages 的长度，用于计算 delta

        if session_key:
            from backend.agent.runtime.session_cache import get_session_cache_manager
            cache_mgr = get_session_cache_manager()

            # 解析 session_key → user_id / conv_id
            # make_key 是 3 段（user_id:conv_id:agent_name），
            # 本解析只取前 2 段，agent_name 独立从 agent.agent_name 传。
            # 当前 writer 路径能对上（conv_id="novel_writer"），但 key 格式变更会静默错位。
            # 未来重构：execute() 签名加 (user_id, conversation_id, agent_name) 三参。
            _parts = session_key.split(":")
            _user_id = _parts[0] if len(_parts) > 0 else "default"
            _conv_id = _parts[1] if len(_parts) > 1 else ""

            # 先用轻量 TTL 检查判断是否命中，cache HIT 时跳过 system_prompt 组装
            if cache_mgr.has_valid_cache(_user_id, _conv_id, agent.agent_name):
                # ── cache HIT：复用 + 校验 sys_prompt hash ──────────
                # 不绕过 hash 校验——改 style_pack 时 sys_prompt 会变
                # hash 变化 → patch_sys_prompt 原地替换 messages[0]
                session_cache_obj = cache_mgr.get(
                    user_id=_user_id,
                    conversation_id=_conv_id,
                    agent_name=agent.agent_name,
                    sys_prompt=agent.system_prompt,  # hash 校验依赖
                )
                if session_cache_obj is not None:
                    self.log.info(
                        "AgentExecutor[%s]: session cache HIT，key=%s，cached_msgs=%d",
                        agent.agent_name, session_key, len(session_cache_obj.messages),
                    )
                    messages = list(session_cache_obj.messages)  # 浅拷贝，防止污染 cache
                else:
                    # has_valid_cache 与 get 之间极小概率 TTL 刚好过期，降级走 MISS
                    session_cache_obj = None

            if session_cache_obj is None:
                # ── cache MISS：组装 system_prompt，rebuild ──
                system_prompt = self._build_system_prompt(
                    agent=agent,
                    tool_instances=tool_instances,
                    project_id=project_id,
                    context=context,
                )
                self.log.info(
                    "AgentExecutor[%s]: session cache MISS，rebuild，key=%s",
                    agent.agent_name, session_key,
                )
                initial_messages: List[dict] = [{"role": "system", "content": system_prompt}]
                if history:
                    initial_messages.extend(history)
                # 从 agents.json 读取模型 context_window（供 token 压缩阈值计算）
                _context_window = self._get_context_window(agent.agent_name)
                session_cache_obj = cache_mgr.create(
                    user_id=_user_id,
                    conversation_id=_conv_id,
                    agent_name=agent.agent_name,
                    sys_prompt=system_prompt,
                    initial_messages=initial_messages,
                    context_window=_context_window,
                )
                messages = list(session_cache_obj.messages)

            # context_message（7 件基座快照）每轮都需要刷新，用 patch_context 原地替换
            # 而不是追加，避免历史基座快照在 cache 里累积
            if context_message:
                session_cache_obj.patch_context(context_message)
                messages = list(session_cache_obj.messages)  # 重取，含最新 context 段

            # delta 基准线：patch_context 不算新增对话，只算 user_message 之后的部分
            messages_base_len = len(messages)
            messages.append({"role": "user", "content": user_message})
        else:
            # ── 无 session_key：原有逻辑（文笔家 / 架构师） ──
            system_prompt = self._build_system_prompt(
                agent=agent,
                tool_instances=tool_instances,
                project_id=project_id,
                context=context,
            )
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                messages.extend(history)
            if context_message:
                messages.append({"role": "user", "content": context_message})
            messages.append({"role": "user", "content": user_message})

        # 4. ReAct loop
        tool_calls_history = []
        last_response_text = ""
        last_error = None
        total_input_tokens = 0
        total_output_tokens = 0

        for iteration in range(1, max_iterations + 1):
            self.log.info(
                "AgentExecutor[%s]: iteration %d/%d, messages=%d",
                agent.agent_name, iteration, max_iterations, len(messages),
            )

            try:
                llm_response = await self.llm.complete(
                    LLMRequest(
                        messages=messages,
                        tools=openai_tools,
                        tool_choice="auto",
                        max_tokens=4096,
                        temperature=0.7,
                        role=ModelRole.TEXT,
                    )
                )
                total_input_tokens += llm_response.input_tokens
                total_output_tokens += llm_response.output_tokens
                # 每轮 LLM 调用后累加 token 到 session cache
                if session_cache_obj is not None:
                    session_cache_obj.add_tokens(
                        llm_response.input_tokens + llm_response.output_tokens
                    )
            except Exception as e:
                self.log.error(
                    "AgentExecutor[%s]: LLM 调用失败 iteration=%d: %s",
                    agent.agent_name, iteration, e,
                )
                last_error = f"LLM 调用失败: {e}"
                break

            # 5. 解析 LLM 响应
            if llm_response.tool_calls:
                # ── LLM 决定调工具 ─────────────────────
                self.log.info(
                    "AgentExecutor[%s]: iteration=%d, LLM 输出 %d 个 tool_calls: %s",
                    agent.agent_name, iteration,
                    len(llm_response.tool_calls),
                    [tc.function.name for tc in llm_response.tool_calls],
                )

                # 把 assistant 的 tool_calls 消息追加
                assistant_msg = {
                    "role": "assistant",
                    "content": llm_response.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in llm_response.tool_calls
                    ],
                }
                messages.append(assistant_msg)

                # 执行每个 tool_call
                for tc in llm_response.tool_calls:
                    tool_name = tc.function.name
                    tool_call_id = tc.id

                    # 权限校验
                    if not self.registry.has_tool(agent.agent_name, tool_name):
                        if agent.extra_tools and tool_name in agent.extra_tools:
                            pass  # 临时扩展的 tool 允许
                        else:
                            self.log.warning(
                                "AgentExecutor[%s]: LLM 调用了不可用工具 '%s' iteration=%d",
                                agent.agent_name, tool_name, iteration,
                            )
                            tool_msg = make_tool_message(
                                tool_call_id=tool_call_id,
                                tool_name=tool_name,
                                result={"error": f"工具 '{tool_name}' 不在 {agent.agent_name} 的可用工具集中"},
                            )
                            messages.append(tool_msg)
                            tool_calls_history.append({
                                "iteration": iteration,
                                "tool_name": tool_name,
                                "arguments": tc.function.arguments,
                                "result": {"error": "tool not available"},
                                "status": "rejected",
                            })
                            continue

                    # 解析 arguments（Pydantic validate）
                    try:
                        args_dict = json.loads(tc.function.arguments)
                    except json.JSONDecodeError as e:
                        self.log.warning(
                            "AgentExecutor[%s]: tool '%s' arguments 不是合法 JSON: %s",
                            agent.agent_name, tool_name, e,
                        )
                        tool_msg = make_tool_message(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            result={"error": f"arguments 不是合法 JSON: {e}"},
                        )
                        messages.append(tool_msg)
                        tool_calls_history.append({
                            "iteration": iteration,
                            "tool_name": tool_name,
                            "arguments": tc.function.arguments,
                            "result": {"error": "invalid JSON"},
                            "status": "invalid_args",
                        })
                        continue

                    # 找到 tool 实例
                    tool_instance = next(
                        (t for t in tool_instances if t.name == tool_name), None
                    )
                    if not tool_instance:
                        self.log.error(
                            "AgentExecutor[%s]: 找不到 tool '%s' 实例",
                            agent.agent_name, tool_name,
                        )
                        continue

                    # Pydantic validate input
                    try:
                        input_obj = tool_instance.input_schema(**args_dict)
                    except Exception as e:
                        self.log.warning(
                            "AgentExecutor[%s]: tool '%s' 参数验证失败: %s",
                            agent.agent_name, tool_name, e,
                        )
                        tool_msg = make_tool_message(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            result={"error": f"参数验证失败: {e}"},
                        )
                        messages.append(tool_msg)
                        tool_calls_history.append({
                            "iteration": iteration,
                            "tool_name": tool_name,
                            "arguments": args_dict,
                            "result": {"error": str(e)},
                            "status": "validation_failed",
                        })
                        continue

                    # 执行 tool
                    self.log.info(
                        "AgentExecutor[%s]: 执行 tool '%s', iteration=%d, args=%s",
                        agent.agent_name, tool_name, iteration,
                        str(args_dict)[:200],
                    )
                    t_tool = time.time()
                    try:
                        tool_output = await tool_instance.run(input_obj)
                        tool_duration_ms = int((time.time() - t_tool) * 1000)
                        # 检查是否是 ToolError
                        if isinstance(tool_output, ToolError):
                            tool_result = {
                                "error": tool_output.code,
                                "message": tool_output.message,
                                "details": tool_output.details,
                            }
                            status = "tool_error"
                            self.log.warning(
                                "AgentExecutor[%s]: tool '%s' 返回 ToolError: %s (%dms)",
                                agent.agent_name, tool_name,
                                tool_output.code, tool_duration_ms,
                            )
                        elif hasattr(tool_output, "success") and tool_output.success is False:
                            # Pydantic 风格的 tool result（如 EditArtifactResult）返 success=False
                            # 不当成功走 else 分支，否则会误记为 SUCCESS — 修正 #4 生产黑盒
                            error_msg = getattr(tool_output, "error", "") or "tool reported success=False"
                            tool_result = tool_output.model_dump() if hasattr(tool_output, "model_dump") else {"error": error_msg}
                            status = "tool_error"
                            self.log.warning(
                                "AgentExecutor[%s]: tool '%s' 返 success=False: %s (%dms)",
                                agent.agent_name, tool_name,
                                error_msg, tool_duration_ms,
                            )
                        else:
                            tool_result = tool_output.model_dump() if hasattr(tool_output, "model_dump") else tool_output
                            status = "success"
                            self.log.info(
                                "AgentExecutor[%s]: tool '%s' SUCCESS (%dms)",
                                agent.agent_name, tool_name, tool_duration_ms,
                            )
                    except Exception as e:
                        tool_duration_ms = int((time.time() - t_tool) * 1000)
                        self.log.error(
                            "AgentExecutor[%s]: tool '%s' 执行异常 (%dms): %s",
                            agent.agent_name, tool_name, tool_duration_ms, e,
                        )
                        tool_result = {"error": str(e)}
                        status = "exception"

                    # 把 tool 结果拼回 messages（超长时截断 content）
                    tool_msg = make_tool_message(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        result=tool_result,
                    )
                    tool_msg["content"] = truncate_tool_result(tool_msg.get("content", ""))
                    messages.append(tool_msg)
                    tool_calls_history.append({
                        "iteration": iteration,
                        "tool_name": tool_name,
                        "arguments": args_dict,
                        "result": tool_result,
                        "status": status,
                    })

                # ── 继续 loop，让 LLM 看 tool 结果决定下一步 ──
                continue

            else:
                # ── LLM 输出 final_response，退出 ──
                last_response_text = llm_response.content or ""
                # 把 final_response 追加到 messages（供 cache 存储）
                messages.append({"role": "assistant", "content": last_response_text})
                break

        duration_ms = int((time.time() - start) * 1000)

        # ── 完成后写回 session cache ───────────────────────────────────────────
        if session_cache_obj is not None and messages_base_len > 0:
            delta = messages[messages_base_len:]
            if delta:
                session_cache_obj.append_delta(delta)
                self.log.info(
                    "AgentExecutor[%s]: session cache 写回 delta=%d，total_cached=%d，key=%s",
                    agent.agent_name, len(delta),
                    len(session_cache_obj.messages), session_key,
                )
                # 超长时异步触发 summary 压缩（不阻塞返回）
                if session_cache_obj.needs_summary():
                    from backend.agent.runtime.session_cache import get_session_cache_manager
                    asyncio.ensure_future(
                        get_session_cache_manager().maybe_compress(session_cache_obj, self.llm)
                    )

        if last_error or (not last_response_text and not tool_calls_history):
            self.log.warning(
                "AgentExecutor[%s]: 达到 max_iterations=%d 或发生错误，"
                "tool_calls_total=%d, duration=%dms",
                agent.agent_name, max_iterations,
                len(tool_calls_history), duration_ms,
            )
            raw_output = AgentOutput(
                final_response=last_response_text or "（达到最大循环轮次，未输出最终回复）",
                tool_calls_history=tool_calls_history,
                iterations=max_iterations,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                duration_ms=duration_ms,
                error=last_error or "max_iterations_reached",
            )
        else:
            self.log.info(
                "AgentExecutor[%s]: final_response，"
                "content_len=%d, tool_calls_total=%d, "
                "tokens(in=%d, out=%d), duration=%dms",
                agent.agent_name,
                len(last_response_text), len(tool_calls_history),
                total_input_tokens, total_output_tokens, duration_ms,
            )
            raw_output = AgentOutput(
                final_response=last_response_text,
                tool_calls_history=tool_calls_history,
                iterations=len(tool_calls_history) + 1,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                duration_ms=duration_ms,
            )

        mw_context = {
            "agent_name": agent.agent_name,
            "project_id": project_id,
            **(context or {}),
        }
        return await self._run_middlewares(
            agent_name=agent.agent_name,
            output=raw_output,
            context=mw_context,
        )

    def _build_system_prompt(
        self,
        agent: AgentConfig,
        tool_instances: List[BaseTool],
        project_id: Optional[str],
        context: Optional[dict],
    ) -> str:
        """拼 system_prompt（含工具清单 + context）"""
        parts = [
            agent.system_prompt,
            "",
            "【可用工具】",
            "以下是你**唯一**可以使用的工具，调用时请严格使用这些 name + arguments 格式：",
        ]

        for tool in tool_instances:
            parts.append(f"- **{tool.name}**: {tool.description}")
            parts.append(f"  - input: `{tool.input_schema.__name__}`")
            if tool.is_dangerous():
                parts.append(f"  - ⚠️ 危险工具（需二次确认）")

        parts.extend([
            "",
            "【当前上下文】",
        ])

        if project_id:
            parts.append(f"- project_id: `{project_id}`")
        else:
            parts.append("- 无项目上下文（管家大厅模式）")

        if context:
            for k, v in context.items():
                parts.append(f"- {k}: {v}")

        parts.extend([
            "",
            "【ReAct 输出格式】",
            "1. thought: 你的思考（为什么调这个 tool / 顺序）",
            "2. tool_calls: 调用哪些 tool（每次调 1+ 个）",
            "3. 调完 tool 后看结果，必要时再调下一个 tool",
            "4. 任务完成 → 输出纯文本 final_response（不要带 tool_calls）",
            "",
            "【约束】",
            "- 只能调上面列出的工具，调用未列出的工具会被拒接",
            "- tool arguments 必须是合法 JSON",
            "- 完成所有 tool 调用后必须输出 final_response 终止 loop",
        ])

        return "\n".join(parts)


    def _get_context_window(self, agent_name: str) -> int:
        """从 agents.json 查找 agent 对应模型的 context_window

        查找路径：agents.json agents[agent_name].model → models[model_id].context_window
        任一步失败则降级为 DEFAULT_CONTEXT_WINDOW。
        """
        from backend.agent.runtime.session_cache import DEFAULT_CONTEXT_WINDOW
        try:
            from backend.config.config_loader import load_agents_config
            cfg = load_agents_config()
            # agents.json agents 键中 agent_name 的大小写可能与代码中不同
            # 这里用 agent.agent_name 与 agents 表做大小写不敏感匹配
            agents_cfg = cfg.get("agents", {})
            # agents.json key 与 agent_name 保持一致，直接索引
            agent_cfg = agents_cfg.get(agent_name)
            if agent_cfg is None:
                return DEFAULT_CONTEXT_WINDOW
            model_name = agent_cfg.get("model", "")
            models_cfg = cfg.get("models", {})
            model_cfg = models_cfg.get(model_name, {})
            return model_cfg.get("context_window", DEFAULT_CONTEXT_WINDOW)
        except Exception as e:
            self.log.debug("_get_context_window: 查询失败 agent=%s: %s", agent_name, e)
            return DEFAULT_CONTEXT_WINDOW


# ============ 工厂方法 ============

_executor_instance: Optional[AgentExecutor] = None


def get_agent_executor() -> AgentExecutor:
    """获取单例 AgentExecutor"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = AgentExecutor()
    return _executor_instance