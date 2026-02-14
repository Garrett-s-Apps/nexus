"""
NEXUS Agent Registry

Mutable runtime registry for all agents. Agents can be hired, fired,
reassigned, restructured, and promoted. The initial state loads from
config/agents.yaml, but all mutations are persisted to SQLite.

The LangGraph graph rebuilds dynamically after every org change.
The ORG_CHART.md auto-regenerates after every change.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.db.sqlite_store import SQLiteStore

DB_PATH = os.path.expanduser("~/.nexus/registry.db")
YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "agents.yaml")


@dataclass
class Agent:
    id: str
    name: str
    model: str
    provider: str
    layer: str
    description: str
    system_prompt: str
    tools: list[str]
    spawns_sdk: bool
    reports_to: str | None
    status: str  # active, fired, suspended, temporary
    hired_at: float
    fired_at: float | None
    temp_expiry: float | None
    metadata: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "provider": self.provider,
            "layer": self.layer,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "spawns_sdk": self.spawns_sdk,
            "reports_to": self.reports_to,
            "status": self.status,
            "hired_at": self.hired_at,
            "fired_at": self.fired_at,
            "temp_expiry": self.temp_expiry,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "Agent":
        return cls(
            id=row[0],
            name=row[1],
            model=row[2],
            provider=row[3],
            layer=row[4],
            description=row[5],
            system_prompt=row[6],
            tools=json.loads(row[7]),
            spawns_sdk=bool(row[8]),
            reports_to=row[9],
            fired_at=row[10],
            temp_expiry=row[11],
            status=row[12],
            hired_at=row[13],
            metadata=json.loads(row[14]) if row[14] else {},
        )


# Default reporting lines for the initial org
DEFAULT_REPORTING = {
    "ceo": None,
    "cpo": "ceo",
    "cfo": "ceo",
    "cro": "ceo",
    "vp_engineering": "ceo",
    "tech_lead": "vp_engineering",
    "em_frontend": "vp_engineering",
    "em_backend": "vp_engineering",
    "em_platform": "vp_engineering",
    "sr_frontend": "em_frontend",
    "sr_backend": "em_backend",
    "sr_fullstack": "em_backend",
    "sr_devops": "em_platform",
    "frontend_dev": "em_frontend",
    "backend_jvm": "em_backend",
    "backend_scripting": "em_backend",
    "fullstack_dev": "em_backend",
    "devops_engineer": "em_platform",
    "qa_lead": "vp_engineering",
    "test_frontend": "qa_lead",
    "test_backend": "qa_lead",
    "linting_agent": "qa_lead",
    "security_consultant": "vp_engineering",
    "ux_consultant": "cpo",
    "systems_consultant": "vp_engineering",
    "cost_consultant": "cfo",
}


class AgentRegistry(SQLiteStore):
    """Mutable agent registry backed by SQLite with thread safety."""

    def __init__(self, db_path: str = DB_PATH):
        super().__init__(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._changelog: list[dict] = []

    def _init_db(self):
        conn = self._db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT DEFAULT 'anthropic',
                layer TEXT NOT NULL,
                description TEXT,
                system_prompt TEXT,
                tools TEXT DEFAULT '[]',
                spawns_sdk INTEGER DEFAULT 0,
                reports_to TEXT,
                fired_at REAL,
                temp_expiry REAL,
                status TEXT DEFAULT 'active',
                hired_at REAL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS org_changelog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                action TEXT NOT NULL,
                agent_id TEXT,
                details TEXT,
                ordered_by TEXT DEFAULT 'garrett'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS circuit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                reason TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_circuit_agent ON circuit_events(agent_id)")
        conn.commit()

    def is_initialized(self) -> bool:
        conn = self._db()
        count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        return bool(count > 0)

    def load_from_yaml(self):
        yaml_path = os.path.normpath(YAML_PATH)
        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        conn = self._db()
        now = time.time()

        for agent_id, agent_data in config["agents"].items():
            conn.execute(
                """INSERT OR REPLACE INTO agents
                   (id, name, model, provider, layer, description, system_prompt,
                    tools, spawns_sdk, reports_to, status, hired_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    agent_data.get("name", agent_id),
                    agent_data.get("model", "sonnet"),
                    agent_data.get("provider", "anthropic"),
                    agent_data.get("layer", "implementation"),
                    agent_data.get("description", ""),
                    agent_data.get("system_prompt", ""),
                    json.dumps(agent_data.get("tools", [])),
                    1 if agent_data.get("spawns_sdk", False) else 0,
                    DEFAULT_REPORTING.get(agent_id),
                    "active",
                    now,
                    json.dumps({}),
                ),
            )

        self._log_change(conn, "initialized", None, "Loaded initial org from agents.yaml")
        conn.commit()

    # ============================================
    # READ OPERATIONS
    # ============================================

    def get_agent(self, agent_id: str) -> Agent | None:
        conn = self._db()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row:
            return Agent.from_row(row)
        return None

    def get_agents_batch(self, agent_ids: list[str]) -> dict[str, Agent]:
        """Batch load agents by IDs. Returns dict mapping agent_id -> Agent."""
        if not agent_ids:
            return {}
        conn = self._db()
        ph = ",".join("?" for _ in agent_ids)
        # Safe: ph contains only "?" placeholders, no user input in query structure
        rows = conn.execute(f"SELECT * FROM agents WHERE id IN ({ph})", agent_ids).fetchall()  # noqa: S608
        return {row[0]: Agent.from_row(row) for row in rows}

    def get_active_agents(self) -> list[Agent]:
        conn = self._db()
        rows = conn.execute(
            "SELECT * FROM agents WHERE status = 'active' OR status = 'temporary'"
        ).fetchall()

        agents = []
        now = time.time()
        for row in rows:
            agent = Agent.from_row(row)
            if agent.status == "temporary" and agent.temp_expiry and agent.temp_expiry < now:
                # Fire agent without awaiting (fire_agent can be sync or async)
                import asyncio
                try:
                    asyncio.create_task(self.fire_agent(agent.id, reason="Temporary contract expired"))
                except RuntimeError:
                    pass  # No event loop running, skip cleanup
                continue
            agents.append(agent)
        return agents

    def get_active_agent_configs(self) -> dict[str, dict]:
        agents = self.get_active_agents()
        return {a.id: a.to_dict() for a in agents}

    def get_agents_by_layer(self, layer: str) -> list[Agent]:
        return [a for a in self.get_active_agents() if a.layer == layer]

    def get_direct_reports(self, manager_id: str) -> list[Agent]:
        """Get direct reports using a targeted SQL query instead of filtering all agents."""
        conn = self._db()
        rows = conn.execute(
            "SELECT * FROM agents WHERE reports_to = ? AND status IN ('active', 'temporary')",
            (manager_id,)
        ).fetchall()
        return [Agent.from_row(row) for row in rows]

    def get_agent_by_name(self, name: str) -> Agent | None:
        conn = self._db()
        row = conn.execute(
            "SELECT * FROM agents WHERE LOWER(name) = LOWER(?) AND status IN ('active', 'temporary')",
            (name,),
        ).fetchone()
        if row:
            return Agent.from_row(row)
        return None

    def search_agents(self, query: str) -> list[Agent]:
        q = f"%{query.lower()}%"
        conn = self._db()
        rows = conn.execute(
            """SELECT * FROM agents
               WHERE status IN ('active', 'temporary')
               AND (LOWER(id) LIKE ? OR LOWER(name) LIKE ? OR LOWER(description) LIKE ?)""",
            (q, q, q),
        ).fetchall()
        return [Agent.from_row(r) for r in rows]

    # ============================================
    # WRITE OPERATIONS (Org Changes)
    # ============================================

    async def hire_agent(
        self,
        agent_id: str,
        name: str,
        model: str,
        layer: str,
        description: str,
        system_prompt: str,
        tools: list[str] | None = None,
        spawns_sdk: bool = False,
        reports_to: str | None = None,
        provider: str = "anthropic",
        temporary: bool = False,
        temp_duration_hours: float | None = None,
    ) -> Agent:
        async with self._lock:
            now = time.time()
            temp_expiry = None
            if temporary and temp_duration_hours:
                temp_expiry = now + (temp_duration_hours * 3600)

            conn = self._db()
            conn.execute(
                """INSERT INTO agents
                   (id, name, model, provider, layer, description, system_prompt,
                    tools, spawns_sdk, reports_to, status, hired_at, temp_expiry, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    name,
                    model,
                    provider,
                    layer,
                    description,
                    system_prompt,
                    json.dumps(tools or []),
                    1 if spawns_sdk else 0,
                    reports_to,
                    "temporary" if temporary else "active",
                    now,
                    temp_expiry,
                    json.dumps({}),
                ),
            )
            self._log_change(conn, "hired", agent_id, f"Hired {name} ({model}) in {layer} layer, reports to {reports_to}")
            conn.commit()

            return self.get_agent(agent_id)  # type: ignore[return-value]

    async def fire_agent(self, agent_id: str, reason: str = "") -> bool:
        async with self._lock:
            conn = self._db()
            agent = self.get_agent(agent_id)
            if not agent or agent.status not in ("active", "temporary"):
                return False

            conn.execute(
                "UPDATE agents SET status = 'fired', fired_at = ? WHERE id = ?",
                (time.time(), agent_id),
            )

            orphans = conn.execute(
                "SELECT id FROM agents WHERE reports_to = ? AND status IN ('active', 'temporary')",
                (agent_id,),
            ).fetchall()

            if orphans and agent.reports_to:
                for orphan in orphans:
                    conn.execute(
                        "UPDATE agents SET reports_to = ? WHERE id = ?",
                        (agent.reports_to, orphan[0]),
                    )

            self._log_change(conn, "fired", agent_id, f"Fired {agent.name}. Reason: {reason}")
            conn.commit()
            return True

    async def reassign_agent(self, agent_id: str, new_manager_id: str) -> bool:
        async with self._lock:
            conn = self._db()
            conn.execute(
                "UPDATE agents SET reports_to = ? WHERE id = ? AND status IN ('active', 'temporary')",
                (new_manager_id, agent_id),
            )
            self._log_change(conn, "reassigned", agent_id, f"Now reports to {new_manager_id}")
            conn.commit()
            return True

    async def update_agent(self, agent_id: str, **kwargs) -> bool:
        async with self._lock:
            conn = self._db()
            _AGENT_COLS = {
                "name", "model", "provider", "layer", "description", "system_prompt",
                "reports_to", "tools", "spawns_sdk", "metadata",
            }

            # Validate all incoming columns first
            for k in kwargs:
                if k not in _AGENT_COLS:
                    raise ValueError(f"Invalid column: {k}")

            allowed_fields = {"name", "model", "provider", "layer", "description", "system_prompt", "reports_to"}
            updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

            if "tools" in kwargs:
                updates["tools"] = json.dumps(kwargs["tools"])
            if "spawns_sdk" in kwargs:
                updates["spawns_sdk"] = 1 if kwargs["spawns_sdk"] else 0
            if "metadata" in kwargs:
                updates["metadata"] = json.dumps(kwargs["metadata"])

            if not updates:
                return False

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [agent_id]
            # Safe: all column names validated against _AGENT_COLS whitelist above
            conn.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", values)  # noqa: S608
            self._log_change(conn, "updated", agent_id, f"Updated fields: {list(updates.keys())}")
            conn.commit()
            return True

    async def consolidate_agents(self, agent_ids: list[str], new_agent_id: str, new_name: str, new_description: str) -> Agent | None:
        """Consolidate multiple agents using batch queries instead of N+1 pattern."""
        # Batch fetch all agents in one query
        agents_dict = self.get_agents_batch(agent_ids)
        agents = list(agents_dict.values())
        if not agents:
            return None

        combined_tools = list(set(tool for a in agents for tool in a.tools))
        combined_prompt = "\n\n".join(
            f"[From {a.name}]: {a.system_prompt}" for a in agents
        )
        highest_model = "haiku"
        for a in agents:
            if a.model == "opus":
                highest_model = "opus"
                break
            if a.model == "sonnet":
                highest_model = "sonnet"

        reports_to = agents[0].reports_to

        for aid in agent_ids:
            await self.fire_agent(aid, reason=f"Consolidated into {new_name}")

        # Batch fetch all orphans in one query
        conn = self._db()
        ph = ",".join("?" for _ in agent_ids)
        # Safe: ph contains only "?" placeholders, no user input in query structure
        orphan_rows = conn.execute(
            f"SELECT id FROM agents WHERE reports_to IN ({ph}) AND status IN ('active', 'temporary')",  # noqa: S608
            agent_ids
        ).fetchall()
        all_orphans = [row[0] for row in orphan_rows]

        new_agent = self.hire_agent(
            agent_id=new_agent_id,
            name=new_name,
            model=highest_model,
            layer=agents[0].layer,
            description=new_description,
            system_prompt=combined_prompt,
            tools=combined_tools,
            spawns_sdk=any(a.spawns_sdk for a in agents),
            reports_to=reports_to,
        )

        for orphan_id in all_orphans:
            await self.reassign_agent(orphan_id, new_agent_id)

        return await new_agent

    async def promote_agent(self, agent_id: str, new_model: str) -> bool:
        return await self.update_agent(agent_id, model=new_model)

    async def demote_agent(self, agent_id: str, new_model: str) -> bool:
        return await self.update_agent(agent_id, model=new_model)

    # ============================================
    # ORG INTROSPECTION (for CEO questions)
    # ============================================

    def get_org_summary(self) -> str:
        agents = self.get_active_agents()
        layers: dict[str, list] = {}
        for a in agents:
            layers.setdefault(a.layer, []).append(a)

        lines = ["NEXUS Organization Summary", "=" * 40]
        for layer_name in ["executive", "management", "senior", "implementation", "quality", "consultant"]:
            if layer_name in layers:
                lines.append(f"\n{layer_name.upper()} LAYER:")
                for a in layers[layer_name]:
                    reports = f" → reports to {a.reports_to}" if a.reports_to else ""
                    lines.append(f"  {a.name} ({a.id}) [{a.model}/{a.provider}]{reports}")
        lines.append(f"\nTotal active agents: {len(agents)}")
        return "\n".join(lines)

    def get_reporting_tree(self, root_id: str = "ceo", indent: int = 0) -> str:
        """Build reporting tree with a single query instead of N+1 pattern."""
        # Fetch entire org tree in one query
        conn = self._db()
        rows = conn.execute(
            "SELECT * FROM agents WHERE status IN ('active', 'temporary')"
        ).fetchall()

        # Build lookup maps
        agents_by_id = {row[0]: Agent.from_row(row) for row in rows}
        reports_by_manager: dict[str, list[Agent]] = {}
        for agent in agents_by_id.values():
            if agent.reports_to:
                reports_by_manager.setdefault(agent.reports_to, []).append(agent)

        # Recursive tree builder using in-memory maps
        def build_tree(agent_id: str, depth: int) -> str:
            agent = agents_by_id.get(agent_id)
            if not agent:
                return ""

            prefix = "  " * depth
            status_tag = " (temp)" if agent.status == "temporary" else ""
            result = f"{prefix}{agent.name} [{agent.model}]{status_tag}\n"

            for report in reports_by_manager.get(agent_id, []):
                result += build_tree(report.id, depth + 1)

            return result

        return build_tree(root_id, indent)

    def get_changelog(self, limit: int = 20) -> list[dict]:
        conn = self._db()
        rows = conn.execute(
            "SELECT timestamp, action, agent_id, details FROM org_changelog ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"timestamp": r[0], "action": r[1], "agent_id": r[2], "details": r[3]}
            for r in rows
        ]

    # ============================================
    # INTERNAL
    # ============================================

    def _log_change(self, conn, action: str, agent_id: str | None, details: str):
        conn.execute(
            "INSERT INTO org_changelog (timestamp, action, agent_id, details) VALUES (?, ?, ?, ?)",
            (time.time(), action, agent_id, details),
        )

    # ============================================
    # CIRCUIT BREAKER EVENTS
    # ============================================

    def record_circuit_event(self, agent_id: str, event_type: str, reason: str = ""):
        """Record a circuit breaker event for reliability tracking."""
        conn = self._db()
        conn.execute(
            "INSERT INTO circuit_events (agent_id, event_type, reason, timestamp) VALUES (?, ?, ?, ?)",
            (agent_id, event_type, reason, time.time()),
        )
        conn.commit()

    def get_agent_reliability(self, agent_id: str, window_hours: int = 24) -> dict:
        """Get agent reliability metrics from circuit breaker events."""
        conn = self._db()
        cutoff = time.time() - (window_hours * 3600)

        trips = conn.execute(
            "SELECT COUNT(*) FROM circuit_events WHERE agent_id=? AND event_type='trip' AND timestamp >= ?",
            (agent_id, cutoff),
        ).fetchone()[0]

        recoveries = conn.execute(
            "SELECT COUNT(*) FROM circuit_events WHERE agent_id=? AND event_type='recovery' AND timestamp >= ?",
            (agent_id, cutoff),
        ).fetchone()[0]

        return {
            "agent_id": agent_id,
            "circuit_trips": trips,
            "recoveries": recoveries,
            "window_hours": window_hours,
        }

    def get_agent_reliability_batch(self, agent_ids: list[str], window_hours: int = 24) -> dict[str, dict]:
        """Batch load agent reliability metrics. Returns dict mapping agent_id -> stats."""
        if not agent_ids:
            return {}

        conn = self._db()
        cutoff = time.time() - (window_hours * 3600)
        ph = ",".join("?" for _ in agent_ids)

        # Get all stats in a single query using GROUP BY
        # Safe: ph contains only "?" placeholders, no user input in query structure
        rows = conn.execute(
            f"""SELECT
                agent_id,
                SUM(CASE WHEN event_type='trip' THEN 1 ELSE 0 END) as trips,
                SUM(CASE WHEN event_type='recovery' THEN 1 ELSE 0 END) as recoveries
            FROM circuit_events
            WHERE agent_id IN ({ph}) AND timestamp >= ?
            GROUP BY agent_id""",  # noqa: S608
            (*agent_ids, cutoff)
        ).fetchall()

        result = {}
        for row in rows:
            agent_id = row[0]
            result[agent_id] = {
                "agent_id": agent_id,
                "circuit_trips": row[1],
                "recoveries": row[2],
                "window_hours": window_hours,
            }

        # Fill in missing agents with zero stats
        for agent_id in agent_ids:
            if agent_id not in result:
                result[agent_id] = {
                    "agent_id": agent_id,
                    "circuit_trips": 0,
                    "recoveries": 0,
                    "window_hours": window_hours,
                }

        return result


# Singleton
registry = AgentRegistry()
