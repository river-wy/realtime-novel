# Realtime Novel · Tests

> **创建**：2026-06-15
> **状态**：M-α/M-β 阶段为验收脚本，M-γ 时升级为 pytest 风格

---

## 目录结构

```
tests/
├── README.md       # 本文件
├── conftest.py     # pytest 公共 fixtures（M-γ 时实装）
├── m1/             # M-α 验收
│   └── test_skeleton.py
├── m2/             # M-β 验收
│   └── test_chapter.py
└── m3/             # M-γ 验收（待建）
    └── test_onboarding.py
```

---

## 怎么跑

### M-α/M-β 阶段（当前）

```bash
cd /Users/wuyu/creativeToys/realtime-novel
source .venv/bin/activate

# M-α 验收
python tests/m1/test_skeleton.py

# M-β 验收（会跑真 LLM，~60s/章）
python tests/m2/test_chapter.py
```

### M-γ 之后（待升级）

```bash
pytest tests/ -v                    # 全部
pytest tests/m1/ -v                 # 单里程碑
pytest tests/m2/ -v -k "test_load"  # 单用例
```

---

## 验收脚本规范

每个 `tests/mN/test_*.py` 应：

1. **顶部 3 行元信息**（按 .realtime-novel/conventions.md §6）：
   ```python
   """M-N 验收脚本 — 跑通 N 项验收标准
   
   验收标准（docs/roadmap/v0.3-product-skeleton.md §4 M-N）:
   - [ ] 验收 1: ...
   - [ ] 验收 2: ...
   
   用法:
       cd /Users/wuyu/creativeToys/realtime-novel
       source .venv/bin/activate
       python tests/mN/test_xxx.py
   """
   ```

2. **5 个 test_ 函数 + 1 个 main**：
   - `test_<验收1>() -> str` 返回"✅ 验收 N 通过"
   - `main()` 收集结果 + 打印总结

3. **断言失败立即抛**（不用 try/except 兜底，让 traceback 暴露）

---

## 何时添加新验收脚本

- 每个新里程碑（M-γ/M-δ/...）新建 `tests/mN/`
- 脚本名：`test_<验证点>.py`（如 `test_skeleton.py` / `test_chapter.py` / `test_onboarding.py`）

---

## M-γ 升级计划

M-γ 阶段把验收脚本升级为 pytest 风格：
- `conftest.py` 加 fixtures（共享 demo project / WorldTree）
- `test_xxx.py` 改用 `def test_xxx(): assert ...`
- 路径常量从 `ROOT` 改用 fixture
- 加 `pyproject.toml` 的 `[tool.pytest.ini_options]`

不破坏现有 M-α/M-β 脚本。
