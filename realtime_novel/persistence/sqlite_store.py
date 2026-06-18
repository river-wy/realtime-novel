"""SQLiteStore: 连接管理 + WAL + sqlite-vec 加载 + 迁移执行

对应 spec.md §4.1 + infra.md §B.3.1
"""
from __future__ import annotations

import json
import sqlite3
import sqlite_vec
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


class SQLiteStore:
    """SQLite 连接管理 + sqlite-vec 加载 + WAL 模式 + 自动迁移"""

    def __init__(self, db_path: Path | str = "data/novel.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """启动时跑 migrations"""
        migrations_dir = Path(__file__).parent / "migrations"
        if not migrations_dir.exists():
            return

        with self.connection() as conn:
            # 创建 migrations 表（如果不存在）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL
                )
            """)
            # 已跑的迁移
            applied = {row["version"] for row in conn.execute("SELECT version FROM migrations").fetchall()}

            for migration_file in sorted(migrations_dir.glob("v*.sql")):
                version = migration_file.stem  # v001_init
                if version not in applied:
                    try:
                        conn.executescript(migration_file.read_text())
                    except Exception as e:
                        # 幂等保护：ALTER TABLE 重复列错误不致命
                        # 例如 v003 ALTER TABLE conversations ADD COLUMN status
                        # 重复跑时 会报 "duplicate column name: status"
                        # 但 migrations 表已记录为 applied，正常
                        err_msg = str(e).lower()
                        if "duplicate column" in err_msg or "already exists" in err_msg:
                            pass  # 幂等
                        else:
                            raise
                    conn.execute(
                        "INSERT INTO migrations (version, applied_at) VALUES (?, ?)",
                        (version, datetime.now()),
                    )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """context manager: 自动加载 vec 扩展 + WAL + 外键 + 关闭"""
        conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,  # autocommit
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # 加载 sqlite-vec 扩展（用全路径，避开 sqlite 默认搜索路径）
        try:
            conn.enable_load_extension(True)
            import sqlite_vec
            vec0_path = Path(sqlite_vec.__file__).parent / "vec0.dylib"
            if vec0_path.exists():
                conn.load_extension(str(vec0_path))
        except Exception:
            # 如果 vec 扩展未安装，world_entries_vec 表会失败但其他表 OK
            pass
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """事务 context manager: 自动 BEGIN/COMMIT/ROLLBACK"""
        with self.connection() as conn:
            conn.execute("BEGIN")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise


# 全局单例
_store: Optional[SQLiteStore] = None


def get_store(db_path: Path | str = "data/novel.db") -> SQLiteStore:
    """获取全局 SQLiteStore 单例（首次调用时创建）"""
    global _store
    if _store is None:
        _store = SQLiteStore(db_path)
    return _store


def reset_store() -> None:
    """重置全局单例（测试用）"""
    global _store
    _store = None
