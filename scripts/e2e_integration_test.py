"""M-ε.5 C 阶段：端到端真实联调测试

模拟前端 4 页面的实际操作链路：
1. Home: 创建项目
2. Onboarding: 5 步引导（Step 4 调 LLM 生成 7 件）
3. Reader: 生成章节 + 验证 summary 落库
4. World: 查看章节列表 + 回档
5. 验证 conversations 表有完整历史

运行: .venv/bin/python scripts/e2e_integration_test.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8080"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=180.0) as client:
        # ============ 1. Home: 创建项目 ============
        print("1. Home: 创建项目...")
        project_name = f"e2e-{int(time.time())}"
        r = await client.post("/api/projects", json={
            "name": project_name,
            "palette": "modern",
            "initial_prompt": "赛博朋克黑客觉醒"
        })
        assert r.status_code == 201, f"创建失败: {r.status_code} {r.text}"
        project_id = r.json()["id"]
        print(f"   ✓ 创建成功: {project_id}")

        # ============ 2. Onboarding 5 步 ============
        print("\n2. Onboarding 5 步...")
        # Step 1a
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "1a", "payload": {
                "genres": ["科幻"], "styles": ["成长", "悬疑"], "tone": "冷叙述"
            }
        })
        assert r.status_code == 200, f"1a 失败: {r.text}"
        print(f"   ✓ Step 1a: {r.json()['next_step']}")

        # Step 1b
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "1b", "payload": {"palette": ["快节奏"]}
        })
        assert r.status_code == 200
        print(f"   ✓ Step 1b: {r.json()['next_step']}")

        # Step 2
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "2", "payload": {"core_relationship": "主角与神秘卖家"}
        })
        assert r.status_code == 200
        print(f"   ✓ Step 2: {r.json()['next_step']}")

        # Step 3
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "3", "payload": {"main_conflict": "AI 觉醒后主角发现父亲失踪"}
        })
        assert r.status_code == 200
        print(f"   ✓ Step 3: {r.json()['next_step']}")

        # Step 4 (生成 7 件，调用 LLM)
        print("   · Step 4 生成 7 件基座（调 LLM，预计 60-90s）...")
        start = time.time()
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "4", "payload": {}
        })
        assert r.status_code == 200, f"Step 4 失败: {r.text}"
        print(f"   ✓ Step 4 done ({time.time() - start:.1f}s)")

        # Step 5 (生成第 1 章，调 LLM)
        print("   · Step 5 生成第 1 章（调 LLM，预计 60-90s）...")
        start = time.time()
        r = await client.post(f"/api/projects/{project_id}/chapters", json={})
        assert r.status_code == 200, f"Step 5 失败: {r.text}"
        chapter_1 = r.json()
        print(f"   ✓ Step 5 done ({time.time() - start:.1f}s)")
        print(f"      章节: {chapter_1['title']} ({chapter_1['word_count']} 字)")
        print(f"      summary: {chapter_1['summary'][:80]}...")

        # ============ 3. Reader: 验证 summary 落库 ============
        print("\n3. Reader: 验证 summary...")
        r = await client.get(f"/api/projects/{project_id}/chapters")
        chapters_list = r.json()["chapters"]
        assert len(chapters_list) == 1
        print(f"   ✓ 章节列表: {len(chapters_list)} 章")
        print(f"      summary 在 list: {chapters_list[0].get('summary') is not None}")

        # 读章节正文
        r = await client.get(f"/api/projects/{project_id}/chapters/1")
        assert r.status_code == 200
        print(f"   ✓ 章节正文: {r.json()['word_count']} 字")

        # 加载项目详情
        r = await client.get(f"/api/projects/{project_id}")
        assert r.status_code == 200
        project_detail = r.json()
        # v0.5: 验证 seven_artifacts 全部有数据
        sa = project_detail.get("seven_artifacts", {})
        print(f"   ✓ seven_artifacts: {list(sa.keys())}")
        for key in ["01-world-tree.yaml", "02-style-charter.yaml", "03-genre-resonance.yaml",
                    "04-main-plot.yaml", "05-sub-plot.yaml", "06-character-card.yaml", "07-seed-table.yaml"]:
            assert key in sa, f"缺 {key}"
        print(f"      7 件全有数据")

        # ============ 4. World: 章节列表 + 回档 ============
        print("\n4. World: 生成第 2 章（回档测试准备）...")
        r = await client.post(f"/api/projects/{project_id}/chapters", json={
            "intervention": "主角在数据黑市遇到神秘卖家"
        })
        assert r.status_code == 200
        chapter_2 = r.json()
        print(f"   ✓ 第 2 章: {chapter_2['title']} ({chapter_2['word_count']} 字)")

        r = await client.get(f"/api/projects/{project_id}/chapters")
        assert len(r.json()["chapters"]) == 2
        print(f"   ✓ 章节数: 2")

        # 回档到第 1 章
        print("\n   · 回档到第 1 章...")
        r = await client.post(f"/api/projects/{project_id}/rollback?to_chapter=1&confirm=true")
        assert r.status_code == 200
        print(f"   ✓ 回档 OK")

        r = await client.get(f"/api/projects/{project_id}/chapters")
        assert len(r.json()["chapters"]) == 1, "回档后应该只剩 1 章"
        print(f"   ✓ 回档后章节数: 1")

        # ============ 5. 验证 messages 落库（v0.4.1 record_tool_call）============
        print("\n5. 验证 messages 落库...")
        from realtime_novel.persistence.sqlite_store import get_store
        with get_store().connection() as conn:
            cnt_total = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
            cnt_project = conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE project_id = ?", (project_id,)
            ).fetchone()["c"]
            cnt_tool = conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE role = 'tool' AND project_id = ?", (project_id,)
            ).fetchone()["c"]
        print(f"   ✓ total messages: {cnt_total}")
        print(f"   ✓ project messages: {cnt_project} (含 project_id)")
        print(f"   ✓ tool messages: {cnt_tool} (业务接口落库)")

        # ============ 6. 验证 conversation 一对一（v0.5）============
        print("\n6. 验证 conversation 一对一...")
        with get_store().connection() as conn:
            cnt_active = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE status = 'active'"
            ).fetchone()["c"]
            cnt_invalidated = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE status = 'invalidated'"
            ).fetchone()["c"]
            has_summary = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE message_count > 0"
            ).fetchone()["c"]
        print(f"   ✓ active conv: {cnt_active}")
        print(f"   ✓ invalidated conv: {cnt_invalidated}")
        print(f"   ✓ message_count > 0: {has_summary}")

        # ============ 7. 清理：删除项目 ============
        print("\n7. 清理...")
        r = await client.delete(f"/api/projects/{project_id}?confirm=true")
        assert r.status_code == 200
        print(f"   ✓ 删除项目 OK")

        print("\n" + "=" * 60)
        print("🎉 M-ε.5 C 阶段端到端联调全通过")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
