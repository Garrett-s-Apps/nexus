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
from datetime import datetime, timedelta

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
            domain_tag TEXT DEFAULT '',
            created_at REAL NOT NULL,
            UNIQUE(source_id)
        )""")
        # Migrate existing databases: add domain_tag column if missing
        try:
            c.execute("ALTER TABLE knowledge_chunks ADD COLUMN domain_tag TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_type ON knowledge_chunks(chunk_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON knowledge_chunks(source_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_domain ON knowledge_chunks(domain_tag)")
        self._db.commit()

    def store_chunk(
        self,
        chunk_type: str,
        content: str,
        embedding: bytes,
        source_id: str = "",
        metadata: dict | None = None,
        domain_tag: str = "",
    ):
        with self._lock:
            self._db.cursor().execute(
                "INSERT INTO knowledge_chunks "
                "(chunk_type,source_id,content,embedding,metadata,domain_tag,created_at) "
                "VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "content=excluded.content, embedding=excluded.embedding, "
                "metadata=excluded.metadata, domain_tag=excluded.domain_tag, created_at=excluded.created_at",
                (chunk_type, source_id, content, embedding,
                 json.dumps(metadata or {}), domain_tag, time.time()),
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

    def get_chunks_filtered(
        self,
        chunk_type: str | None = None,
        domain_tag: str | None = None,
        max_age_days: int | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Get chunks with SQL pre-filtering before cosine similarity.

        Reduces candidate set for similarity scoring by filtering on indexed columns.
        """
        conditions = []
        params: list[str | float] = []

        if chunk_type:
            conditions.append("chunk_type = ?")
            params.append(chunk_type)
        if domain_tag:
            conditions.append("domain_tag = ?")
            params.append(domain_tag)
        if max_age_days:
            cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).timestamp()
            conditions.append("created_at > ?")
            params.append(cutoff)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(float(limit))
        rows = self._db.execute(
            f"SELECT * FROM knowledge_chunks {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def count_chunks(self) -> dict:
        c = self._db.cursor()
        rows = c.execute(
            "SELECT chunk_type, COUNT(*) as cnt FROM knowledge_chunks GROUP BY chunk_type"
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def prune_old_chunks(self):
        """Remove chunks based on type-specific retention policies.

        Retention policy:
        - error_resolution: kept indefinitely
        - task_outcome: 90-day TTL
        - conversation, code_change: 30-day TTL
        """
        now = time.time()
        with self._lock:
            # Prune conversation and code_change chunks older than 30 days
            cutoff_30 = now - (30 * 86400)
            self._db.cursor().execute(
                "DELETE FROM knowledge_chunks WHERE created_at < ? "
                "AND chunk_type IN ('conversation', 'code_change')",
                (cutoff_30,),
            )

            # Prune task_outcome chunks older than 90 days
            cutoff_90 = now - (90 * 86400)
            self._db.cursor().execute(
                "DELETE FROM knowledge_chunks WHERE created_at < ? "
                "AND chunk_type = 'task_outcome'",
                (cutoff_90,),
            )

            # error_resolution chunks are never pruned
            self._db.commit()


# Singleton
knowledge_store = KnowledgeStore()
