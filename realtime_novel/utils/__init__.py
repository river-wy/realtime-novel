"""utils — 工具类（M-α 阶段最小集合）

- seed_demo.py       从 v0.2 case JSON 转 YAML 装载到 projects/demo-urban-romance/
- version.py         __version__ 常量

未来: log / config 加载 / 路径处理等
"""
from .version import __version__
from . import seed_demo

__all__ = ["__version__", "seed_demo"]
