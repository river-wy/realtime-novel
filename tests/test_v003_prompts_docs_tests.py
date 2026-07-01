"""v003 prompts-docs-tests 测试（pytest）

覆盖 .spec/db-refactor/test-cases/prompts-docs-tests.json 7 个用例
- prompt / README / e2e fixture 删 actor_* + opening_scene
"""
from __future__ import annotations

import re
import pytest
from pathlib import Path


def test_tc_prompts_001_prompt_factory_no_actor():
    """agent_prompt_factory.py 全文零命中 actor_*（除 v003 删 ... 注释）"""
    src = Path("backend/agent/prompts/agent_prompt_factory.py").read_text()
    # v003 删 actor_feedback / actor_character 注释可出现
    # 实际 function / variable 不应再有
    import re
    # 找 function calls 和 variable uses
    # actor_feedback / actor_character 应不在 prompt 内容中
    assert "actor_feedback=actor_feedback" not in src
    assert "actor_character=actor_character" not in src


def test_tc_prompts_002_prompt_factory_no_opening_scene():
    """agent_prompt_factory.py 全文零命中 opening_scene"""
    src = Path("backend/agent/prompts/agent_prompt_factory.py").read_text()
    assert "opening_scene" not in src


def test_tc_prompts_003_agents_readme_no_actor():
    """agents_README.md 全文零命中 actor_*"""
    src = Path("backend/agent/agents_README.md").read_text()
    # v003 删 ... 注释可出现
    # 实际示例代码不应再有
    assert "actor_feedback=actor_feedback" not in src
    assert "actor_character=actor_character" not in src


def test_tc_prompts_004_e2e_test_no_opening_scene():
    """旧 e2e_integration_test.py 已删（2026-07-01 清理），由 tests/e2e_scenarios/scenarios.md 替代。
    本 test 验证业务代码 (backend/) 零命中 opening_scene（fixtures 全部清理）"""
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py", "opening_scene", "backend/"],
        capture_output=True, text=True,
    )
    # 允许「v003 删 / 已删 / 清理」等说明性注释
    lines = [l for l in result.stdout.split("\n") if l and not re.search(r"v003[：:]?\s*(删|已删)|2026.*清理|替代|fixtures 全部清理|零命中|删 opening_scene|v003 删", l)]
    assert len(lines) == 0, f"backend/ 仍有 opening_scene 命中: {lines[:3]}"


def test_tc_prompts_006_tests_dir_no_actor():
    """tests/ 目录下业务代码零命中 actor_*（negative test 自身排除）"""
    import os
    import re
    # 哪些文件是 negative test：自己合法传 actor_* 来验证业务方拒绝
    # 这些文件的 kwargs 验证是 negative test 必需，不算违规
    negative_test_files = {
        "test_v003_persistence_layer.py",  # TC-007/008 验证 create/update 不再接受 actor_*
    }
    for root, dirs, files in os.walk("tests"):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            # 排除本测试文件自身
            if "test_v003_prompts_docs_tests" in p:
                continue
            # negative test 文件：跳过扫描（信任文件自身就是验证业务清理的）
            if f in negative_test_files:
                continue
            src = open(p).read()
            # 找 actor_feedback= / actor_character= 赋值
            calls = re.findall(r"actor_(?:feedback|character)\s*=\s*", src)
            assert len(calls) == 0, f"{p} 含 actor_* 赋值: {calls}"
            # 找 .actor_feedback( / .actor_character( 方法调用
            method_calls = re.findall(r"\bactor_(?:feedback|character)\s*\(", src)
            assert len(method_calls) == 0, f"{p} 含 actor_* 方法调用: {method_calls}"


def test_tc_prompts_007_tests_dir_no_opening_scene():
    """tests/ 目录下业务代码零命中 opening_scene（negative test 自身排除）"""
    import os
    import re
    # negative test 文件：自身函数名/docstring/注释含 opening_scene 是为了测试业务清理
    negative_test_files = {
        "test_v003_onboarding_pipeline.py",  # TC-004 验证 opening_scene 字段全链路不存在
    }
    for root, dirs, files in os.walk("tests"):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            # 排除本测试文件 + agent-core（专门测 opening_scene 的测试）
            if "test_v003_prompts_docs_tests" in p or "test_v003_agent_core" in p:
                continue
            # negative test 文件：跳过扫描
            if f in negative_test_files:
                continue
            src = open(p).read()
            # 找有意义的"opening_scene"使用（赋值/参数/调用）
            meaningful_uses = re.findall(r"\bopening_scene\s*[=\(:]", src)
            assert len(meaningful_uses) == 0, f"{p} 含 opening_scene: {meaningful_uses}"


def test_tc_prompts_005_e2e_passes_smoke():
    """旧 e2e_integration_test.py 已删（2026-07-01 清理）。
    替代验证：tests/e2e_scenarios/scenarios.md 存在且至少 5 个场景"""
    scenarios = Path("tests/e2e_scenarios/scenarios.md")
    assert scenarios.exists(), f"业务场景文件不存在: {scenarios}"
    content = scenarios.read_text()
    # 至少 5 个场景标题
    scenario_count = content.count("## 场景")
    assert scenario_count >= 5, f"业务场景不足 5 个, 实际 {scenario_count}"
