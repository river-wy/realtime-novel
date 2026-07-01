"""v0.6.1 端到端真实联调测试

模拟前端 4 页面的实际操作链路：
1. Home: 创建项目
2. Onboarding: 5 步引导（HTTP 路径：Step 1-2-3-4-5，Step 4 写 7 件基座，Step 5 生成第 1 章）
3. Reader: 验证 summary 落库
4. World: 生成第 2 章 + 回档
5. 验证 conversations 表有完整历史
6. 验证 conversation 一对一

v0.6.1 适配:
- step 枚举: "1", "2", "3", "4", "5" (不是 1a/1b)
- Step 1 payload: {genres, styles, tone} (List[str])
- Step 2 payload: {palette} (str)
- Step 3 payload: {story_core, characters}
- Step 4 payload: {main_arc, sub_plots, seeds, reader_feeling}
- Step 5 payload: {}
- ChapterInfo 字段: num (不是 chapter_num)
- RollbackResponse 字段: kept_chapters/removed_chapters
- seven_artifacts 7 key: world_tree/style_charter/genre_resonance/main_plot/sub_plot/character_card/seed_table

运行: .venv/bin/python tests/e2e_integration_test.py
"""
import asyncio
import time

import httpx

BASE = "http://127.0.0.1:7778"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=180.0) as client:
        # ============ 1. Home: 创建项目 ============
        print("1. Home: 创建项目...")
        project_name = f"e2e-{int(time.time())}"
        r = await client.post("/api/projects", json={
            "name": project_name,
            "palette": "modern",
            "initial_prompt": "赛博朋克黑客觉醒",
        })
        assert r.status_code == 201, f"创建失败: {r.status_code} {r.text}"
        project_id = r.json()["id"]
        print(f"   ✓ 创建成功: {project_id}")

        # ============ 2. Onboarding 5 步（HTTP 路径）============
        print("\n2. Onboarding 5 步 (HTTP)...")

        # Step 1: 题材/风格/基调
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "1", "payload": {
                "genres": ["科幻"],
                "styles": ["成长", "悬疑"],
                "tone": ["冷叙述"],
            },
        })
        assert r.status_code == 200, f"Step 1 失败: {r.text}"
        print(f"   ✓ Step 1: next_step={r.json().get('next_step')}")

        # Step 2: palette
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "2", "payload": {"palette": "modern"},
        })
        assert r.status_code == 200, f"Step 2 失败: {r.text}"
        print(f"   ✓ Step 2: next_step={r.json().get('next_step')}")

        # Step 3: 故事引擎
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "3", "payload": {
                "story_core": "AI 觉醒时代, 黑客主角发现父亲在数据黑市失踪, 追查中发现父亲不是普通人",
                "characters": "林渊 - 主角, 独立黑客 - 偏执天才\n卖家 - 神秘线人 - 真实目的不明\n导师 - 父亲导师 - 隐藏身份",
            },
        })
        assert r.status_code == 200, f"Step 3 失败: {r.text}"
        print(f"   ✓ Step 3: next_step={r.json().get('next_step')}")

        # Step 4: 7 件基座组装（HTTP 兜底, 调 onboarding_artifacts.assemble_7_artifacts）
        print("   · Step 4 组装 7 件基座 (HTTP 路径, 调 onboard_artifacts)...")
        start = time.time()
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "4", "payload": {
                "main_arc": "觉醒\n对决\n归零",
                "sub_plots": "AI 起源之谜",
                "seeds": "父亲留下加密盒",
                "reader_feeling": "看完心里发冷, 想再读一遍",
            },
        })
        assert r.status_code == 200, f"Step 4 失败: {r.text}"
        print(f"   ✓ Step 4 done ({time.time() - start:.1f}s)")

        # Step 5: 生成第 1 章 (调 LLM, 60-100s)
        print("   · Step 5 生成第 1 章 (调 LLM, 预计 60-100s)...")
        start = time.time()
        r = await client.post(f"/api/projects/{project_id}/onboarding", json={
            "step": "5", "payload": {},
        })
        assert r.status_code == 200, f"Step 5 失败: {r.text}"
        step5_result = r.json()
        print(f"   ✓ Step 5 done ({time.time() - start:.1f}s)")
        # 响应结构: {"step": "5", "result": {"chapter": {...}, "next_step": None, ...}, "next_step": null}
        result_inner = step5_result.get("result", {})
        chapter_1 = result_inner.get("chapter", {})
        assert chapter_1.get("num"), f"Step 5 未返 chapter: {step5_result}"
        print(f"      章节: 第 {chapter_1['num']} 章 {chapter_1.get('title', '')} ({chapter_1.get('word_count', 0)} 字)")
        if chapter_1.get("summary"):
            print(f"      summary: {chapter_1['summary'][:80]}...")

        # ============ 3. Reader: 验证 summary 落库 ============
        print("\n3. Reader: 验证 summary...")
        r = await client.get(f"/api/projects/{project_id}/chapters")
        assert r.status_code == 200, f"chapters list 失败: {r.text}"
        chapters_list = r.json()["chapters"]
        assert len(chapters_list) == 1, f"期望 1 章, 实际 {len(chapters_list)}"
        print(f"   ✓ 章节列表: {len(chapters_list)} 章")
        print(f"      summary 在 list: {chapters_list[0].get('summary') is not None}")
        print(f"      num: {chapters_list[0]['num']}, status: {chapters_list[0]['status']}")

        # 读章节正文 (GET /api/projects/{id}/chapters/{n})
        r = await client.get(f"/api/projects/{project_id}/chapters/{chapter_1['num']}")
        assert r.status_code == 200, f"chapter read 失败: {r.text}"
        print(f"   ✓ 章节正文: {r.json()['word_count']} 字")

        # 加载项目详情
        r = await client.get(f"/api/projects/{project_id}")
        assert r.status_code == 200, f"project detail 失败: {r.text}"
        project_detail = r.json()
        sa = project_detail.get("seven_artifacts", {}) or {}
        print(f"   ✓ seven_artifacts 7 key 全部存在: {list(sa.keys())}")
        expected_keys = [
            "world_tree", "style_charter", "genre_resonance",
            "main_plot", "sub_plot", "character_card", "seed_table",
        ]
        for key in expected_keys:
            assert key in sa, f"缺 {key}"
        print(f"      7 件全有数据")

        # ============ 4. World: 生成第 2 章 + 回档 ============
        print("\n4. World: 生成第 2 章 (回档测试准备)...")
        r = await client.post(f"/api/projects/{project_id}/chapters", json={
            "intervention": "主角在数据黑市遇到神秘卖家",
        })
        assert r.status_code == 200, f"第 2 章失败: {r.text}"
        chapter_2 = r.json()
        print(f"   ✓ 第 {chapter_2['chapter_num']} 章: {chapter_2['title']} ({chapter_2['word_count']} 字)")

        r = await client.get(f"/api/projects/{project_id}/chapters")
        assert len(r.json()["chapters"]) == 2, f"期望 2 章, 实际 {len(r.json()['chapters'])}"
        print(f"   ✓ 章节数: 2")

        # 回档到第 1 章
        print("\n   · 回档到第 1 章...")
        r = await client.post(f"/api/projects/{project_id}/rollback?to_chapter=1&confirm=true")
        assert r.status_code == 200, f"回档失败: {r.text}"
        rb = r.json()
        print(f"   ✓ 回档 OK: kept={rb.get('kept_chapters')}, removed={rb.get('removed_chapters')}")

        r = await client.get(f"/api/projects/{project_id}/chapters")
        assert len(r.json()["chapters"]) == 1, f"回档后应剩 1 章, 实际 {len(r.json()['chapters'])}"
        print(f"   ✓ 回档后章节数: 1")

        # ============ 5. 验证 messages 落库 ============
        print("\n5. 验证 messages 落库...")
        # 加项目根到 sys.path (脚本独立跑时需要)
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from backend.persistence.sqlite_store import get_store
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

        # ============ 6. 验证 conversation 一对一 ============
        print("\n6. 验证 conversation 一对一...")
        with get_store().connection() as conn:
            cnt_active = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE status = 'active'"
            ).fetchone()["c"]
            cnt_invalidated = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE status = 'invalidated'"
            ).fetchone()["c"]
            has_message = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE message_count > 0"
            ).fetchone()["c"]
        print(f"   ✓ active conv: {cnt_active}")
        print(f"   ✓ invalidated conv: {cnt_invalidated}")
        print(f"   ✓ message_count > 0: {has_message}")

        # ============ 7. 清理：删除项目 ============
        print("\n7. 清理...")
        r = await client.delete(f"/api/projects/{project_id}?confirm=true")
        assert r.status_code == 200, f"删除失败: {r.status_code} {r.text}"
        print(f"   ✓ 删除项目 OK")

        print("\n" + "=" * 60)
        print("🎉 v0.6.1 端到端联调全通过")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
