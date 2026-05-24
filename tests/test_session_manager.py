"""测试 Session Manager."""

import tempfile
from pathlib import Path

from goalflow.core.models import Session
from goalflow.core.session_manager import SessionManager


class TestSessionManager:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            mgr = SessionManager(str(db_path))

            session = Session(repo_path="/tmp/repo")
            mgr.save(session)

            loaded = mgr.load(session.id)
            assert loaded is not None
            assert loaded.repo_path == "/tmp/repo"
            assert loaded.id == session.id

    def test_list_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            mgr = SessionManager(str(db_path))

            s1 = Session(repo_path="/tmp/repo1")
            s2 = Session(repo_path="/tmp/repo2")
            mgr.save(s1)
            mgr.save(s2)

            sessions = mgr.list_sessions()
            assert len(sessions) == 2

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            mgr = SessionManager(str(db_path))

            session = Session(repo_path="/tmp/repo")
            mgr.save(session)
            assert mgr.load(session.id) is not None

            mgr.delete(session.id)
            assert mgr.load(session.id) is None
