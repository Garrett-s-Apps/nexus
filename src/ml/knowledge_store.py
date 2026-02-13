"""
Knowledge Store — dedicated persistence for RAG knowledge chunks.

Separated from MLStore to avoid competing workloads: RAG does bulk cosine
similarity scans while MLStore handles frequent task_outcome inserts and
model artifact serialization.
"""

import json
import os
import sqlite3
import threading
import time

from src.config import KNOWLEDGE_DB_PATH


class KnowledgeStore:
    """Persistent storage for RAG knowledge chunks in a dedicated database."""

    def __init__(self, db_path: str = KNOWLEDGE_DB_PATH):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    @property
    def _db(self) -> sqlite3.Connection:
        assert self._conn is not None, "KnowledgeStore.init() must be called first"
        return self._conn

    def init(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()

    def _create_tables(self):
        c = self._db.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_type TEXT NOT NULL,
            source_id TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            embedding BLOB NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at REAL NOT NULL,
            UNIQUE(source_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_type ON knowledge_chunks(chunk_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON knowledge_chunks(source_id)")
        self._db.commit()

    def store_chunk(
        self,
        chunk_type: str,
        content: str,
        embedding: bytes,
        source_id: str = "",
        metadata: dict | None = None,
    ):
        with self._lock:
            self._db.cursor().execute(
                "INSERT INTO knowledge_chunks "
                "(chunk_type,source_id,content,embedding,metadata,created_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "content=excluded.content, embedding=excluded.embedding, "
                "metadata=excluded.metadata, created_at=excluded.created_at",
                (chunk_type, source_id, content, embedding,
                 json.dumps(metadata or {}), time.time()),
            )
            self._db.commit()

    def get_all_chunks(
        self, chunk_type: str | None = None, limit: int = 500,
    ) -> list[dict]:
        c = self._db.cursor()
        if chunk_type:
            c.execute(
                "SELECT * FROM knowledge_chunks WHERE chunk_type=? "
                "ORDER BY created_at DESC LIMIT ?",
                (chunk_type, limit),
            )
        else:
            c.execute(
                "SELECT * FROM knowledge_chunks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in c.fetchall()]

    def count_chunks(self) -> dict:
        c = self._db.cursor()
        rows = c.execute(
            "SELECT chunk_type, COUNT(*) as cnt FROM knowledge_chunks GROUP BY chunk_type"
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def prune_old_chunks(self, max_age_days: int = 30, keep_types: tuple = ("error_resolution",)):
        """Remove chunks older than max_age_days, preserving high-value types."""
        cutoff = time.time() - (max_age_days * 86400)
        placeholders = ",".join("?" for _ in keep_types)
        with self._lock:
            self._db.cursor().execute(
                f"DELETE FROM knowledge_chunks WHERE created_at < ? "
                f"AND chunk_type NOT IN ({placeholders})",
                (cutoff, *keep_types),
            )
            self._db.commit()


# Singleton
knowledge_store = KnowledgeStore()
