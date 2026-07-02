"""exceptions.py — 异常层级（M-α 阶段最小集合）

异常层级:
    RealtimeNovelError              # 所有产品异常的基类
    ├── ConfigError                 # 配置缺失/错误（config.private.json 找不到）
    ├── ProjectError                # 项目相关错误
    │   ├── ProjectNotFoundError    # 项目不存在
    │   ├── ProjectAlreadyExistsError  # 项目已存在（create 时冲突）
    │   └── ProjectCorruptError     # 项目 7 件不全 / 解析失败
    ├── LLMError                    # LLM 调用相关
    │   └── LLMEmptyResponseError   # LLM 返空 content
    └── GenerationError             # 章节生成失败
        └── GenerationQualityError  # 字数不达标 / 内容质量不达标
"""
from __future__ import annotations


class RealtimeNovelError(Exception):
    """所有产品异常的基类（用户捕获可以一把抓）"""


# === 配置 ===

class ConfigError(RealtimeNovelError):
    """配置缺失或错误"""


# === 项目 ===

class ProjectError(RealtimeNovelError):
    """项目相关错误的基类"""


class ProjectNotFoundError(ProjectError):
    """项目不存在"""


class ProjectAlreadyExistsError(ProjectError):
    """项目已存在（create 时冲突）"""


class ProjectCorruptError(ProjectError):
    """项目 7 件不全或解析失败"""


# === LLM ===

class LLMError(RealtimeNovelError):
    """LLM 调用相关错误"""


class LLMEmptyResponseError(LLMError):
    """LLM 返回空 content"""


# === 生成 ===

class GenerationError(RealtimeNovelError):
    """章节生成失败"""


class GenerationQualityError(GenerationError):
    """生成质量不达标（字数 / 内容检查失败）"""
