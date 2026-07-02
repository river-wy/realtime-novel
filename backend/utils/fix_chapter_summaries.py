"""fix_chapter_summaries — 修复存量章节 summary

背景：
  早期章节 sentinel 解析失败时 fallback 截了正文前100字，导致 summary 是开头几句话而非情节概括。
  本脚本找出所有"可疑"的 summary（与正文前100字高度重合），调 LLM 重新生成两句话概括并写回 DB。

用法（从项目根目录运行）：
  python -m backend.utils.fix_chapter_summaries [--project-id world-2ba833b4] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 保证 import 路径正确
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _looks_like_fallback_summary(summary: str, content: str) -> bool:
    """判断 summary 是否是截正文开头的 fallback（而非真正的情节概括）"""
    if not summary or not content:
        return False
    # 去标题行
    body_lines = [l for l in content.split("\n") if not l.strip().startswith("# ")]
    body = " ".join(body_lines).strip()
    # 如果 summary 是正文开头的子串（宽松匹配：去空白后比较前N字）
    clean_body = "".join(body.split())[:200]
    clean_summary = "".join(summary.split())
    # summary 完全包含在正文前200字里 → 大概率是截断的
    return clean_body.startswith(clean_summary[:50]) if len(clean_summary) >= 10 else False


async def _regenerate_summary(chapter_content: str, project_id: str, chapter_num: int) -> str | None:
    """调 LLM 生成两句话概括"""
    from backend.adapters.llm_adapter import get_llm_adapter
    from backend.adapters.types import ModelRole

    adapter = get_llm_adapter()
    content_snippet = chapter_content[:3000]

    prompt = f"""请用两句话概括以下小说章节的核心故事发展（不是描述开头，而是概括整章的情节推进和关键事件）：

{content_snippet}

要求：
- 恰好两句话
- 概括整章最重要的情节推进，不是复述开头
- 简洁，~50-100 字
- 直接输出两句话，不要加任何前缀或解释"""

    response = await adapter.complete_with_messages(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="你是一个专业的小说内容编辑，擅长用简洁语言概括章节核心情节。",
        max_tokens=400,
        temperature=0.3,
        role=ModelRole.TEXT,
        enable_thinking=False,  # summary 不需要 thinking，关闭节省 token
    )
    summary = response.content.strip()
    logger.info(f"[{project_id}] ch{chapter_num:03d} 新 summary: {summary}")
    return summary if summary else None


async def fix_summaries(project_id: str | None, dry_run: bool) -> None:
    from backend.persistence import ChapterRepository
    from backend.config.config_loader import PROJECT_ROOT

    chap_repo = ChapterRepository()

    # 拿所有项目或指定项目的章节
    from backend.persistence.sqlite_store import get_store
    with get_store().connection() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT project_id, chapter_num, summary, file_path FROM chapters "
                "WHERE project_id = ? ORDER BY chapter_num",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT project_id, chapter_num, summary, file_path FROM chapters "
                "ORDER BY project_id, chapter_num"
            ).fetchall()

    logger.info(f"共 {len(rows)} 章节待检查")
    fixed = 0
    skipped = 0

    for row in rows:
        pid = row["project_id"]
        num = row["chapter_num"]
        summary = row["summary"] or ""
        file_path = row["file_path"]

        # 读正文
        chapter_path = Path(file_path)
        if not chapter_path.is_absolute():
            chapter_path = PROJECT_ROOT / chapter_path
        if not chapter_path.exists():
            logger.warning(f"[{pid}] ch{num:03d} 文件不存在: {file_path}，跳过")
            skipped += 1
            continue

        content = chapter_path.read_text(encoding="utf-8")

        if not _looks_like_fallback_summary(summary, content):
            logger.debug(f"[{pid}] ch{num:03d} summary 正常，跳过")
            skipped += 1
            continue

        logger.info(f"[{pid}] ch{num:03d} 发现可疑 summary: {summary}")

        if dry_run:
            logger.info(f"[DRY-RUN] 跳过实际修复")
            fixed += 1
            continue

        try:
            new_summary = await _regenerate_summary(content, pid, num)
            if new_summary:
                chap_repo.update_summary(pid, num, summary=new_summary)
                logger.info(f"[{pid}] ch{num:03d} ✓ summary 已更新")
                fixed += 1
            else:
                logger.warning(f"[{pid}] ch{num:03d} LLM 返回空，跳过")
                skipped += 1
        except Exception as e:
            logger.error(f"[{pid}] ch{num:03d} 失败: {e}")
            skipped += 1

    logger.info(f"完成：修复 {fixed} 章，跳过 {skipped} 章")


def main():
    parser = argparse.ArgumentParser(description="修复存量章节 summary")
    parser.add_argument("--project-id", help="只修复指定项目（不传则修复所有）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不写库")
    args = parser.parse_args()

    asyncio.run(fix_summaries(args.project_id, args.dry_run))


if __name__ == "__main__":
    main()

