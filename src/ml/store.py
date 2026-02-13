"""
ML Data Store — Persistent storage for learning signals.

Stores:
- Task outcome records (agent + task + result + cost + duration)
- Directive embeddings for similarity search
- Circuit breaker / escalation events for reliability modeling
- Trained model artifacts (serialized sklearn pipelines)

All tables live in ~/.nexus/ml.db to keep ML data separate from core state.
"""

import json
import os
import pickle
import sqlite3
import threading
import time

from src.config import NEXUS_DIR

ML_DB_PATH = os.path.join(NEXUS_DIR, "ml.db")


class MLStore:
    """Persistent storage for ML training data and model artifacts."""

    def __init__(self, db_path: str = ML_DB_PATH):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    @property
    def _db(self) -> sqlite3.Connection:
        """Return the connection, asserting it's been initialized."""
        assert self._conn is not None, "MLStore.init() must be called first"
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

        # Task outcomes: links agent assignment to result quality
        c.execute("""CREATE TABLE IF NOT EXISTS task_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            directive_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            task_description TEXT NOT NULL,
            specialty TEXT DEFAULT '',
            outcome TEXT NOT NULL,
            cost_usd REAL DEFAULT 0,
            duration_sec REAL DEFAULT 0,
            defect_count INTEGER DEFAULT 0,
            qa_cycles INTEGER DEFAULT 0,
            model TEXT DEFAULT ''
        )""")

        # Directive embeddings for similarity search
        c.execute("""CREATE TABLE IF NOT EXISTS directive_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            directive_id TEXT UNIQUE NOT NULL,
            directive_text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            total_cost REAL DEFAULT 0,
            total_tasks INTEGER DEFAULT 0,
            total_duration_sec REAL DEFAULT 0,
            outcome TEXT DEFAULT '',
            created_at REAL NOT NULL
        )""")

        # Circuit breaker events (persisted, not in-memory only)
        c.execute("""CREATE TABLE IF NOT EXISTS circuit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            agent_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            failure_count INTEGER DEFAULT 0,
            model TEXT DEFAULT '',
            task_type TEXT DEFAULT '',
            recovery_time_sec REAL DEFAULT 0
        )""")

        # Escalation events
        c.execute("""CREATE TABLE IF NOT EXISTS escalation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            agent_id TEXT NOT NULL,
            from_model TEXT NOT NULL,
            to_model TEXT,
            reason TEXT DEFAULT '',
            task_type TEXT DEFAULT '',
            resolved INTEGER DEFAULT 0
        )""")

        # Serialized model artifacts
        c.execute("""CREATE TABLE IF NOT EXISTS model_artifacts (
            name TEXT PRIMARY KEY,
            version INTEGER DEFAULT 1,
            artifact BLOB NOT NULL,
            metrics TEXT DEFAULT '{}',
            training_samples INTEGER DEFAULT 0,
            updated_at REAL NOT NULL
        )""")

        # RAG knowledge chunks — general-purpose semantic store
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chunk_type TEXT NOT NULL,
            source_id TEXT DEFAULT '',
            content TEXT NOT NULL,
            embedding BLOB NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at REAL NOT NULL
        )""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_agent ON task_outcomes(agent_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_directive ON task_outcomes(directive_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_circuit_agent ON circuit_events(agent_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_escalation_agent ON escalation_events(agent_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_type ON knowledge_chunks(chunk_type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON knowledge_chunks(source_id)")

        self._db.commit()

    # === TASK OUTCOMES ===
    def record_outcome(
        self,
        directive_id: str,
        task_id: str,
        agent_id: str,
        task_description: str,
        outcome: str,
        specialty: str = "",
        cost_usd: float = 0,
        duration_sec: float = 0,
        defect_count: int = 0,
        qa_cycles: int = 0,
        model: str = "",
    ):
        with self._lock:
            self._db.cursor().execute(
                "INSERT INTO task_outcomes (timestamp,directive_id,task_id,agent_id,"
                "task_description,specialty,outcome,cost_usd,duration_sec,defect_count,"
                "qa_cycles,model) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), directive_id, task_id, agent_id, task_description,
                 specialty, outcome, cost_usd, duration_sec, defect_count,
                 qa_cycles, model),
            )
            self._db.commit()

    def get_outcomes(self, agent_id: str | None = None, limit: int = 500) -> list[dict]:
        c = self._db.cursor()
        if agent_id:
            c.execute(
                "SELECT * FROM task_outcomes WHERE agent_id=? ORDER BY timestamp DESC LIMIT ?",
                (agent_id, limit),
            )
        else:
            c.execute("SELECT * FROM task_outcomes ORDER BY timestamp DESC LIMIT ?", (limit,))
        return [dict(r) for r in c.fetchall()]

    def get_agent_success_rate(self, agent_id: str) -> dict:
        c = self._db.cursor()
        total = c.execute(
            "SELECT COUNT(*) FROM task_outcomes WHERE agent_id=?", (agent_id,)
        ).fetchone()[0]
        successes = c.execute(
            "SELECT COUNT(*) FROM task_outcomes WHERE agent_id=? AND outcome='complete'",
            (agent_id,),
        ).fetchone()[0]
        avg_cost = c.execute(
            "SELECT COALESCE(AVG(cost_usd), 0) FROM task_outcomes WHERE agent_id=?",
            (agent_id,),
        ).fetchone()[0]
        avg_defects = c.execute(
            "SELECT COALESCE(AVG(defect_count), 0) FROM task_outcomes WHERE agent_id=?",
            (agent_id,),
        ).fetchone()[0]
        return {
            "agent_id": agent_id,
            "total_tasks": total,
            "success_rate": successes / total if total > 0 else 0,
            "avg_cost": float(avg_cost),
            "avg_defects": float(avg_defects),
        }

    # === DIRECTIVE EMBEDDINGS ===
    def store_embedding(
        self,
        directive_id: str,
        directive_text: str,
        embedding: bytes,
        total_cost: float = 0,
        total_tasks: int = 0,
        total_duration_sec: float = 0,
        outcome: str = "",
    ):
        with self._lock:
            self._db.cursor().execute(
                "INSERT INTO directive_embeddings "
                "(directive_id,directive_text,embedding,total_cost,total_tasks,"
                "total_duration_sec,outcome,created_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(directive_id) DO UPDATE SET "
                "total_cost=excluded.total_cost,total_tasks=excluded.total_tasks,"
                "total_duration_sec=excluded.total_duration_sec,outcome=excluded.outcome",
                (directive_id, directive_text, embedding, total_cost, total_tasks,
                 total_duration_sec, outcome, time.time()),
            )
            self._db.commit()

    def get_all_embeddings(self) -> list[dict]:
        c = self._db.cursor()
        c.execute("SELECT * FROM directive_embeddings ORDER BY created_at DESC")
        return [dict(r) for r in c.fetchall()]

    # === RAG KNOWLEDGE CHUNKS ===
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
                "VALUES (?,?,?,?,?,?)",
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

    # === CIRCUIT BREAKER EVENTS ===
    def record_circuit_event(
        self,
        agent_id: str,
        event_type: str,
        failure_count: int = 0,
        model: str = "",
        task_type: str = "",
        recovery_time_sec: float = 0,
    ):
        with self._lock:
            self._db.cursor().execute(
                "INSERT INTO circuit_events (timestamp,agent_id,event_type,"
                "failure_count,model,task_type,recovery_time_sec) VALUES (?,?,?,?,?,?,?)",
                (time.time(), agent_id, event_type, failure_count, model,
                 task_type, recovery_time_sec),
            )
            self._db.commit()

    def get_agent_reliability(self, agent_id: str) -> dict:
        c = self._db.cursor()
        trips = c.execute(
            "SELECT COUNT(*) FROM circuit_events WHERE agent_id=? AND event_type='trip'",
            (agent_id,),
        ).fetchone()[0]
        recoveries = c.execute(
            "SELECT COUNT(*) FROM circuit_events WHERE agent_id=? AND event_type='recovery'",
            (agent_id,),
        ).fetchone()[0]
        avg_recovery = c.execute(
            "SELECT COALESCE(AVG(recovery_time_sec), 0) FROM circuit_events "
            "WHERE agent_id=? AND event_type='recovery'",
            (agent_id,),
        ).fetchone()[0]
        return {
            "agent_id": agent_id,
            "circuit_trips": trips,
            "recoveries": recoveries,
            "avg_recovery_sec": float(avg_recovery),
        }

    # === ESCALATION EVENTS ===
    def record_escalation(
        self,
        agent_id: str,
        from_model: str,
        to_model: str | None = None,
        reason: str = "",
        task_type: str = "",
    ):
        with self._lock:
            self._db.cursor().execute(
                "INSERT INTO escalation_events (timestamp,agent_id,from_model,"
                "to_model,reason,task_type) VALUES (?,?,?,?,?,?)",
                (time.time(), agent_id, from_model, to_model, reason, task_type),
            )
            self._db.commit()

    # === MODEL ARTIFACTS ===
    def save_model(self, name: str, model_obj: object, metrics: dict | None = None,
                   training_samples: int = 0):
        artifact = pickle.dumps(model_obj)
        with self._lock:
            c = self._db.cursor()
            existing = c.execute("SELECT version FROM model_artifacts WHERE name=?", (name,)).fetchone()
            version = (existing[0] + 1) if existing else 1
            c.execute(
                "INSERT INTO model_artifacts (name,version,artifact,metrics,training_samples,updated_at) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET "
                "version=excluded.version,artifact=excluded.artifact,metrics=excluded.metrics,"
                "training_samples=excluded.training_samples,updated_at=excluded.updated_at",
                (name, version, artifact, json.dumps(metrics or {}), training_samples, time.time()),
            )
            self._db.commit()

    def load_model(self, name: str) -> object | None:
        c = self._db.cursor()
        row = c.execute("SELECT artifact FROM model_artifacts WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        result: object = pickle.loads(row[0])  # noqa: S301
        return result

    def get_model_info(self, name: str) -> dict | None:
        c = self._db.cursor()
        row = c.execute(
            "SELECT name,version,metrics,training_samples,updated_at FROM model_artifacts WHERE name=?",
            (name,),
        ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_training_data_count(self) -> dict:
        c = self._db.cursor()
        return {
            "task_outcomes": c.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0],
            "directive_embeddings": c.execute("SELECT COUNT(*) FROM directive_embeddings").fetchone()[0],
            "circuit_events": c.execute("SELECT COUNT(*) FROM circuit_events").fetchone()[0],
            "escalation_events": c.execute("SELECT COUNT(*) FROM escalation_events").fetchone()[0],
        }


# Singleton
ml_store = MLStore()
