"""上下文与记忆存储 — Session级 + Repo级 + 长期记忆."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryStore:
    """分层记忆存储.

    - Session 级：单次对话链路的完整上下文
    - Repo 级：代码库索引（文件树、符号表）
    - 长期记忆：成功/失败的方案模式
    """

    def __init__(self, db_path: str = ".goalflow/memory.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_context (
                    session_id TEXT PRIMARY KEY,
                    context TEXT,
                    summary TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS repo_index (
                    repo_path TEXT PRIMARY KEY,
                    file_tree TEXT,
                    symbols TEXT,
                    dependencies TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    pattern TEXT,
                    outcome TEXT,
                    success BOOLEAN,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    # ===== Session 级 =====

    def save_session_context(self, session_id: str, context: Dict[str, Any], summary: str = "") -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO session_context (session_id, context, summary, updated_at) VALUES (?, ?, ?, datetime('now'))",
                (session_id, json.dumps(context), summary),
            )
            conn.commit()

    def load_session_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT context FROM session_context WHERE session_id = ?", (session_id,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def get_session_summary(self, session_id: str) -> str:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT summary FROM session_context WHERE session_id = ?", (session_id,)
            ).fetchone()
            return row[0] if row else ""

    # ===== Repo 级 =====

    def save_repo_index(self, repo_path: str, file_tree: List[str], symbols: Dict[str, Any], dependencies: Dict[str, Any]) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO repo_index (repo_path, file_tree, symbols, dependencies, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                (repo_path, json.dumps(file_tree), json.dumps(symbols), json.dumps(dependencies)),
            )
            conn.commit()

    def load_repo_index(self, repo_path: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT file_tree, symbols, dependencies FROM repo_index WHERE repo_path = ?", (repo_path,)
            ).fetchone()
            if row:
                return {
                    "file_tree": json.loads(row[0]),
                    "symbols": json.loads(row[1]),
                    "dependencies": json.loads(row[2]),
                }
            return None

    # ===== 长期记忆 =====

    def save_pattern(self, query: str, pattern: str, outcome: str, success: bool) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO long_term_memory (query, pattern, outcome, success) VALUES (?, ?, ?, ?)",
                (query, pattern, outcome, success),
            )
            conn.commit()

    def find_similar_patterns(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """简单关键词匹配，后续可替换为向量检索."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT query, pattern, outcome, success FROM long_term_memory WHERE query LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            return [
                {"query": r[0], "pattern": r[1], "outcome": r[2], "success": bool(r[3])}
                for r in rows
            ]
