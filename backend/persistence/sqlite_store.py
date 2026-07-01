"""SQLiteStore：连接管理 + WAL + 自动迁移"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional


class SQLiteStore:
    """SQLite 连接管理，WAL 模式，启动时自动跑 migrations"""

    def __init__(self, db_path: Path | str = "data/novel.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """按文件名顺序执行 migrations/v*.sql，已执行的跳过"""
        migrations_dir = Path(__file__).parent / "migrations"
        if not migrations_dir.exists():
            return

        with self.connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL
                )
            """)
            applied = {row["version"] for row in conn.execute("SELECT version FROM migrations").fetchall()}

            for migration_file in sorted(migrations_dir.glob("v*.sql")):
                version = migration_file.stem
                if version not in applied:
                    try:
                        conn.executescript(migration_file.read_text())
                    except Exception as e:
                        err_msg = str(e).lower()
                        if "duplicate column" in err_msg or "already exists" in err_msg:
                            pass  # 幂等
                        else:
                            raise
                    conn.execute(
                        "INSERT OR IGNORE INTO migrations (version, applied_at) VALUES (?, ?)",
                        (version, datetime.now()),
                    )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """autocommit 连接，WAL + 外键开启"""
        conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """显式事务：自动 BEGIN/COMMIT/ROLLBACK"""
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
