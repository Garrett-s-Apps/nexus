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
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

import yaml  # type: ignore[import-untyped]

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


class AgentRegistry:
    """Mutable agent registry backed by SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        self._changelog: list[dict] = []

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
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
        conn.close()

    def is_initialized(self) -> bool:
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        conn.close()
        return bool(count > 0)

    def load_from_yaml(self):
        yaml_path = os.path.normpath(YAML_PATH)
        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        conn = sqlite3.connect(self.db_path)
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
        conn.close()

    # ============================================
    # READ OPERATIONS
    # ============================================

    def get_agent(self, agent_id: str) -> Agent | None:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        conn.close()
        if row:
            return Agent.from_row(row)
        return None

    def get_active_agents(self) -> list[Agent]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT * FROM agents WHERE status = 'active' OR status = 'temporary'"
        ).fetchall()
        conn.close()

        agents = []
        now = time.time()
        for row in rows:
            agent = Agent.from_row(row)
            if agent.status == "temporary" and agent.temp_expiry and agent.temp_expiry < now:
                self.fire_agent(agent.id, reason="Temporary contract expired")
                continue
            agents.append(agent)
        return agents

    def get_active_agent_configs(self) -> dict[str, dict]:
        agents = self.get_active_agents()
        return {a.id: a.to_dict() for a in agents}

    def get_agents_by_layer(self, layer: str) -> list[Agent]:
        return [a for a in self.get_active_agents() if a.layer == layer]

    def get_direct_reports(self, manager_id: str) -> list[Agent]:
        return [a for a in self.get_active_agents() if a.reports_to == manager_id]

    def get_agent_by_name(self, name: str) -> Agent | None:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM agents WHERE LOWER(name) = LOWER(?) AND status IN ('active', 'temporary')",
            (name,),
        ).fetchone()
        conn.close()
        if row:
            return Agent.from_row(row)
        return None

    def search_agents(self, query: str) -> list[Agent]:
        q = f"%{query.lower()}%"
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT * FROM agents
               WHERE status IN ('active', 'temporary')
               AND (LOWER(id) LIKE ? OR LOWER(name) LIKE ? OR LOWER(description) LIKE ?)""",
            (q, q, q),
        ).fetchall()
        conn.close()
        return [Agent.from_row(r) for r in rows]

    # ============================================
    # WRITE OPERATIONS (Org Changes)
    # ============================================

    def hire_agent(
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
        now = time.time()
        temp_expiry = None
        if temporary and temp_duration_hours:
            temp_expiry = now + (temp_duration_hours * 3600)

        conn = sqlite3.connect(self.db_path)
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
        conn.close()

        return self.get_agent(agent_id)  # type: ignore[return-value]

    def fire_agent(self, agent_id: str, reason: str = "") -> bool:
        conn = sqlite3.connect(self.db_path)
        agent = self.get_agent(agent_id)
        if not agent or agent.status not in ("active", "temporary"):
            conn.close()
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
        conn.close()
        return True

    def reassign_agent(self, agent_id: str, new_manager_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE agents SET reports_to = ? WHERE id = ? AND status IN ('active', 'temporary')",
            (new_manager_id, agent_id),
        )
        self._log_change(conn, "reassigned", agent_id, f"Now reports to {new_manager_id}")
        conn.commit()
        conn.close()
        return True

    def update_agent(self, agent_id: str, **kwargs) -> bool:
        conn = sqlite3.connect(self.db_path)
        _AGENT_COLS = {
            "name", "model", "provider", "layer", "description", "system_prompt",
            "reports_to", "tools", "spawns_sdk",
        }

        # Validate all incoming columns first
        for k in kwargs:
            if k not in _AGENT_COLS:
                conn.close()
                raise ValueError(f"Invalid column: {k}")

        allowed_fields = {"name", "model", "provider", "layer", "description", "system_prompt", "reports_to"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields and v is not None}

        if "tools" in kwargs:
            updates["tools"] = json.dumps(kwargs["tools"])
        if "spawns_sdk" in kwargs:
            updates["spawns_sdk"] = 1 if kwargs["spawns_sdk"] else 0

        if not updates:
            conn.close()
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [agent_id]
        # Safe: all column names validated against _AGENT_COLS whitelist above
        conn.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", values)  # noqa: S608
        self._log_change(conn, "updated", agent_id, f"Updated fields: {list(updates.keys())}")
        conn.commit()
        conn.close()
        return True

    def consolidate_agents(self, agent_ids: list[str], new_agent_id: str, new_name: str, new_description: str) -> Agent | None:
        agents = [a for aid in agent_ids if (a := self.get_agent(aid)) is not None]
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
            self.fire_agent(aid, reason=f"Consolidated into {new_name}")

        all_orphans = []
        conn = sqlite3.connect(self.db_path)
        for aid in agent_ids:
            orphans = conn.execute(
                "SELECT id FROM agents WHERE reports_to = ? AND status IN ('active', 'temporary')",
                (aid,),
            ).fetchall()
            all_orphans.extend([o[0] for o in orphans])
        conn.close()

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
            self.reassign_agent(orphan_id, new_agent_id)

        return new_agent

    def promote_agent(self, agent_id: str, new_model: str) -> bool:
        return self.update_agent(agent_id, model=new_model)

    def demote_agent(self, agent_id: str, new_model: str) -> bool:
        return self.update_agent(agent_id, model=new_model)

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
        agent = self.get_agent(root_id)
        if not agent or agent.status not in ("active", "temporary"):
            return ""

        prefix = "  " * indent
        status_tag = " (temp)" if agent.status == "temporary" else ""
        line = f"{prefix}{agent.name} [{agent.model}]{status_tag}\n"

        reports = self.get_direct_reports(root_id)
        for report in reports:
            line += self.get_reporting_tree(report.id, indent + 1)

        return line

    def get_changelog(self, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT timestamp, action, agent_id, details FROM org_changelog ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
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
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO circuit_events (agent_id, event_type, reason, timestamp) VALUES (?, ?, ?, ?)",
            (agent_id, event_type, reason, time.time()),
        )
        conn.commit()
        conn.close()

    def get_agent_reliability(self, agent_id: str, window_hours: int = 24) -> dict:
        """Get agent reliability metrics from circuit breaker events."""
        conn = sqlite3.connect(self.db_path)
        cutoff = time.time() - (window_hours * 3600)

        trips = conn.execute(
            "SELECT COUNT(*) FROM circuit_events WHERE agent_id=? AND event_type='trip' AND timestamp >= ?",
            (agent_id, cutoff),
        ).fetchone()[0]

        recoveries = conn.execute(
            "SELECT COUNT(*) FROM circuit_events WHERE agent_id=? AND event_type='recovery' AND timestamp >= ?",
            (agent_id, cutoff),
        ).fetchone()[0]

        conn.close()

        return {
            "agent_id": agent_id,
            "circuit_trips": trips,
            "recoveries": recoveries,
            "window_hours": window_hours,
        }


# Singleton
registry = AgentRegistry()
