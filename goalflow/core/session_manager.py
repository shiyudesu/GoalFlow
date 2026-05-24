"""Session 管理器 — 持久化与恢复."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from .models import Event, Session, Stage


class SessionManager:
    """管理 Session 的生命周期、持久化与恢复."""

    def __init__(self, db_path: str = ".goalflow/sessions.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    stage TEXT,
                    payload TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save(self, session: Session) -> None:
        """保存 Session."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, data, updated_at) VALUES (?, ?, datetime('now'))",
                (session.id, session.model_dump_json()),
            )
            conn.commit()

    def load(self, session_id: str) -> Optional[Session]:
        """加载 Session."""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT data FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row:
                return Session.model_validate_json(row[0])
        return None

    def list_sessions(self) -> List[Dict[str, str]]:
        """列出所有 Session."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT id, updated_at FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
            return [{"id": r[0], "updated_at": r[1]} for r in rows]

    def delete(self, session_id: str) -> None:
        """删除 Session."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            conn.commit()

    def save_event(self, event: Event) -> None:
        """保存事件."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO events (id, session_id, type, stage, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.session_id,
                    event.type.value,
                    event.stage.value if event.stage else None,
                    json.dumps(event.payload),
                    event.created_at.isoformat(),
                ),
            )
            conn.commit()

    def load_events(self, session_id: str) -> List[Event]:
        """加载事件历史."""
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT id, session_id, type, stage, payload, created_at FROM events WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
            events = []
            for r in rows:
                events.append(Event(
                    id=r[0],
                    session_id=r[1],
                    type=r[2],  # Will be validated by Pydantic
                    stage=Stage(r[3]) if r[3] else None,
                    payload=json.loads(r[4]),
                    created_at=r[5],
                ))
            return events
