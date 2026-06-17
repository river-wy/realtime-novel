"""BaseTool 抽象 + 工具注册表

对应 core.md §B.1.1 + §B.1.2
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Any, Optional
from pydantic import BaseModel


class BaseTool(ABC):
    """所有 LangGraph Tool 的基类

    子类必须重写：
    - name / description
    - input_schema / output_schema
    - async def run(input, progress_callback=None) -> output

    可选重写：
    - is_dangerous() 默认 False
    """

    name: str = ""
    description: str = ""
    input_schema: type[BaseModel] = BaseModel
    output_schema: type[BaseModel] = BaseModel

    @abstractmethod
    async def run(
        self,
        input: BaseModel,
        progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> BaseModel:
        """执行工具

        返回结构化结果（不是抛异常给 Agent）：
        - 成功：返回 output_schema 实例
        - 失败：返回 ToolError(code, message) 结构
        """
        ...

    def is_dangerous(self) -> bool:
        """危险工具（delete/rollback）override 返回 True"""
        return False


class ToolError(BaseModel):
    """工具失败返回的结构化错误（spec §5.2）"""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


# ============ 工具注册表（LangGraph 调度用）============

_tools: dict[str, BaseTool] = {}


def register_tool(tool: BaseTool) -> None:
    """注册工具到全局表"""
    _tools[tool.name] = tool


def get_tool(name: str) -> BaseTool:
    """按名称获取工具（每次返回新实例，避免共享状态）"""
    if name not in _tools:
        raise KeyError(f"Tool not found: {name}")
    # 重新创建 tool 实例（避免 BaseTool 单例的内部状态污染）
    base_class = type(_tools[name])
    return base_class()


def list_tools() -> list[str]:
    """列出所有注册的工具名"""
    return list(_tools.keys())


def reset_tools() -> None:
    """重置工具表（测试用）"""
    _tools.clear()
