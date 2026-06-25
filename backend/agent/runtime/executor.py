"""agent_executor — Agent ReAct loop 执行器（s3.3）

职责（spec.md §9.3）：
1. 加载 Agent 的可用工具集
2. 拼 system_prompt（含可用工具列表 + 职责）
3. 调 LLM（注入 tools 参数）
4. 解析 LLM 输出：
   - 有 tool_calls → 执行 tool → 把结果拼回 messages → 继续循环
   - 无 tool_calls → LLM 输出 final_response → 退出
5. 退出条件：final_response / max_iterations=7 / 死循环检测

对应 spec.md §9.3 AgentExecutor
"""
from __future__ import annotations

import json
import time
from pydantic import BaseModel, Field
from typing import Optional, List, Any

from backend.adapters.llm_adapter import get_llm_adapter
from backend.adapters.types import LLMRequest, ModelRole
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
    """Agent 执行结果"""
    final_response: str = ""
    tool_calls_history: List[dict] = Field(default_factory=list)  # 所有调过的 tool_calls
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    error: Optional[str] = None


# ============ Agent Executor ============

@logger_decorator
class AgentExecutor:
    """Agent ReAct loop 执行器（s3.3）

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
    """

    def __init__(self, llm_adapter=None, tool_registry: Optional[ToolRegistry] = None):
        self.llm = llm_adapter or get_llm_adapter()
        self.registry = tool_registry or get_tool_registry()

    async def execute(
        self,
        agent: AgentConfig,
        user_message: str,
        project_id: Optional[str] = None,
        context: Optional[dict] = None,
        max_iterations: int = 7,  # 18:02 拍板
    ) -> AgentOutput:
        """执行 Agent ReAct 推演 loop

        Args:
            agent: Agent 配置（agent_name + system_prompt + 可选 extra_tools）
            user_message: 用户消息（首轮 user 消息）
            project_id: 项目 ID（注入到 context_block）
            context: 额外上下文 dict（注入到 system_prompt 的 context_block）
            max_iterations: 最大循环轮次（18:02 拍板 = 7）

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

        # 2. 拼 system_prompt（含工具清单 + context）
        system_prompt = self._build_system_prompt(
            agent=agent,
            tool_instances=tool_instances,
            project_id=project_id,
            context=context,
        )

        # 3. 初始化 messages
        messages: List[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

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

                    # 把 tool 结果拼回 messages
                    tool_msg = make_tool_message(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        result=tool_result,
                    )
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
                duration_ms = int((time.time() - start) * 1000)
                self.log.info(
                    "AgentExecutor[%s]: final_response at iteration=%d, "
                    "content_len=%d, tool_calls_total=%d, "
                    "tokens(in=%d, out=%d), duration=%dms",
                    agent.agent_name, iteration,
                    len(last_response_text), len(tool_calls_history),
                    total_input_tokens, total_output_tokens, duration_ms,
                )
                return AgentOutput(
                    final_response=last_response_text,
                    tool_calls_history=tool_calls_history,
                    iterations=iteration,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    duration_ms=duration_ms,
                )

        # 达到 max_iterations 仍未退出
        duration_ms = int((time.time() - start) * 1000)
        self.log.warning(
            "AgentExecutor[%s]: 达到 max_iterations=%d 仍未输出 final_response, "
            "tool_calls_total=%d, duration=%dms",
            agent.agent_name, max_iterations,
            len(tool_calls_history), duration_ms,
        )
        return AgentOutput(
            final_response=last_response_text or "（达到最大循环轮次，未输出最终回复）",
            tool_calls_history=tool_calls_history,
            iterations=max_iterations,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            duration_ms=duration_ms,
            error=last_error or "max_iterations_reached",
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


# ============ 工厂方法 ============

_executor_instance: Optional[AgentExecutor] = None


def get_agent_executor() -> AgentExecutor:
    """获取单例 AgentExecutor"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = AgentExecutor()
    return _executor_instance