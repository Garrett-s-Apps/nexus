"""
NEXUS Cost Tracker with CFO Budget Enforcement

Extends the basic cost tracker with:
- Per-project budget allocation
- Automatic model downgrading when over budget
- CFO alerts and escalation
- Historical cost persistence in SQLite
- Projected monthly spend calculations
"""

import os
import sqlite3
import time
from typing import Any

from src.config import COST_DB_PATH

DB_PATH = COST_DB_PATH

# Model pricing per 1M tokens (input/output)
MODEL_PRICING = {
    "opus": {"input": 15.0, "output": 75.0},
    "sonnet": {"input": 3.0, "output": 15.0},
    "haiku": {"input": 0.25, "output": 1.25},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "o3": {"input": 10.0, "output": 40.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    # Claude Code CLI uses Max subscription — $0 API cost
    "claude-code:opus": {"input": 0.0, "output": 0.0},
    "claude-code:sonnet": {"input": 0.0, "output": 0.0},
    "claude-code:haiku": {"input": 0.0, "output": 0.0},
}

# Default budget allocation
DEFAULT_BUDGETS = {
    "hourly_target": 1.00,          # $1/hr target
    "hourly_hard_cap": 2.50,        # Hard cap triggers model downgrade
    "session_warning": 5.00,        # Warn CFO at $5/session
    "session_hard_cap": 15.00,      # Kill session at $15
    "monthly_target": 160.00,       # Monthly target
    "monthly_hard_cap": 250.00,     # Monthly hard cap
}

# When over budget, downgrade models
DOWNGRADE_MAP = {
    "opus": "sonnet",
    "sonnet": "haiku",
    "haiku": "haiku",  # Can't go lower
}


class CostTracker:
    """Full cost tracking with CFO budget enforcement."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

        # In-memory session tracking
        self.session_start = time.time()
        self.session_cost = 0.0
        self.by_model: dict[str, float] = {}
        self.by_agent: dict[str, float] = {}
        self.by_project: dict[str, float] = {}
        self.call_count = 0
        self.budgets = dict(DEFAULT_BUDGETS)
        self._downgrade_active = False
        self._alerts_sent: set[str] = set()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cost_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                model TEXT NOT NULL,
                agent TEXT NOT NULL,
                project TEXT DEFAULT '',
                tokens_in INTEGER DEFAULT 0,
                tokens_out INTEGER DEFAULT 0,
                cost_usd REAL NOT NULL,
                session_id TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budget_config (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cost_timestamp
            ON cost_events(timestamp)
        """)
        conn.commit()
        conn.close()

    def calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["sonnet"])
        return (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000

    def record(
        self,
        model: str,
        agent_name: str,
        tokens_in: int,
        tokens_out: int,
        project: str = "",
        session_id: str = "",
    ) -> dict:
        """Record a cost event. Returns enforcement actions."""
        cost = self.calculate_cost(model, tokens_in, tokens_out)

        # Update in-memory
        self.session_cost += cost
        self.by_model[model] = self.by_model.get(model, 0.0) + cost
        self.by_agent[agent_name] = self.by_agent.get(agent_name, 0.0) + cost
        if project:
            self.by_project[project] = self.by_project.get(project, 0.0) + cost
        self.call_count += 1

        # Persist
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO cost_events (timestamp, model, agent, project, tokens_in, tokens_out, cost_usd, session_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), model, agent_name, project, tokens_in, tokens_out, cost, session_id),
        )
        conn.commit()
        conn.close()

        # Enforcement
        return self._enforce_budget(cost, agent_name)

    def _enforce_budget(self, latest_cost: float, agent: str) -> dict:
        """CFO budget enforcement. Returns actions to take."""
        actions: dict[str, Any] = {"alerts": [], "downgrade": False, "kill_session": False}

        hourly = self.hourly_rate

        # Hourly rate warning
        if hourly > self.budgets["hourly_target"] and "hourly_warning" not in self._alerts_sent:
            actions["alerts"].append(
                f"CFO Alert: Hourly rate ${hourly:.2f}/hr exceeds ${self.budgets['hourly_target']:.2f}/hr target"
            )
            self._alerts_sent.add("hourly_warning")

        # Hourly hard cap — trigger model downgrade
        if hourly > self.budgets["hourly_hard_cap"]:
            actions["downgrade"] = True
            self._downgrade_active = True
            if "hourly_hard" not in self._alerts_sent:
                actions["alerts"].append(
                    f"CFO ENFORCEMENT: Hourly rate ${hourly:.2f}/hr exceeds hard cap. Downgrading models."
                )
                self._alerts_sent.add("hourly_hard")

        # Session warning
        if self.session_cost > self.budgets["session_warning"] and "session_warning" not in self._alerts_sent:
            actions["alerts"].append(
                f"CFO Alert: Session cost ${self.session_cost:.2f} exceeds ${self.budgets['session_warning']:.2f} warning threshold"
            )
            self._alerts_sent.add("session_warning")

        # Session hard cap — kill
        if self.session_cost > self.budgets["session_hard_cap"]:
            actions["kill_session"] = True
            actions["alerts"].append(
                f"CFO ENFORCEMENT: Session cost ${self.session_cost:.2f} exceeds hard cap. Terminating."
            )

        # Monthly check
        monthly = self.get_monthly_cost()
        if monthly > self.budgets["monthly_target"] and "monthly_warning" not in self._alerts_sent:
            actions["alerts"].append(
                f"CFO Alert: Monthly cost ${monthly:.2f} exceeds ${self.budgets['monthly_target']:.2f} target"
            )
            self._alerts_sent.add("monthly_warning")

        if monthly > self.budgets["monthly_hard_cap"]:
            actions["downgrade"] = True
            self._downgrade_active = True

        return actions

    def get_effective_model(self, requested_model: str) -> str:
        """Return the model to actually use, considering budget enforcement."""
        if self._downgrade_active:
            return DOWNGRADE_MAP.get(requested_model, requested_model)
        return requested_model

    @property
    def total_cost(self) -> float:
        return self.session_cost

    @property
    def hourly_rate(self) -> float:
        elapsed = time.time() - self.session_start
        if elapsed < 60:
            return 0.0
        return self.session_cost / (elapsed / 3600)

    @property
    def over_budget(self) -> bool:
        return self.hourly_rate > self.budgets["hourly_hard_cap"]

    def get_monthly_cost(self) -> float:
        """Get current month's total cost from persistent store."""
        now = time.time()
        # Start of current month
        t = time.localtime(now)
        month_start = time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1))

        conn = sqlite3.connect(self.db_path)
        result = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM cost_events WHERE timestamp >= ?",
            (month_start,),
        ).fetchone()[0]
        conn.close()
        return float(result)

    def get_daily_breakdown(self, days: int = 7) -> list[dict]:
        """Cost breakdown by day for the last N days."""
        cutoff = time.time() - (days * 86400)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT date(timestamp, 'unixepoch', 'localtime') as day,
                      SUM(cost_usd) as total,
                      COUNT(*) as calls
               FROM cost_events
               WHERE timestamp >= ?
               GROUP BY day
               ORDER BY day DESC""",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [{"date": r[0], "cost": r[1], "calls": r[2]} for r in rows]

    def get_agent_breakdown(self) -> list[dict]:
        """Cost by agent, sorted by spend."""
        return sorted(
            [{"agent": k, "cost": v} for k, v in self.by_agent.items()],
            key=lambda x: x["cost"],
            reverse=True,
        )

    def generate_cfo_report(self) -> str:
        """Full CFO cost report."""
        monthly = self.get_monthly_cost()
        daily = self.get_daily_breakdown(7)
        projected = self.hourly_rate * 24 * 30 if self.hourly_rate > 0 else 0

        report = f"""
CFO Cost Report
{'=' * 55}

SESSION
  Cost:            ${self.session_cost:.2f}
  Hourly Rate:     ${self.hourly_rate:.2f}/hr  {'✅' if self.hourly_rate <= 1.0 else '⚠️' if self.hourly_rate <= 2.5 else '❌'}
  API Calls:       {self.call_count}
  Downgrade Active: {'YES ⚠️' if self._downgrade_active else 'No ✅'}

MONTH-TO-DATE
  Total:           ${monthly:.2f}
  Target:          ${self.budgets['monthly_target']:.2f}
  Hard Cap:        ${self.budgets['monthly_hard_cap']:.2f}
  Status:          {'✅' if monthly <= self.budgets['monthly_target'] else '⚠️' if monthly <= self.budgets['monthly_hard_cap'] else '❌'}

PROJECTED
  Monthly (at current rate): ${projected:.2f}

BY MODEL:
"""
        for model, cost in sorted(self.by_model.items(), key=lambda x: x[1], reverse=True):
            report += f"  {model:20s} ${cost:.4f}\n"

        report += "\nBY AGENT (top 10):\n"
        for item in self.get_agent_breakdown()[:10]:
            report += f"  {item['agent']:20s} ${item['cost']:.4f}\n"

        if daily:
            report += "\nDAILY (last 7 days):\n"
            for d in daily:
                report += f"  {d['date']}  ${d['cost']:.2f}  ({d['calls']} calls)\n"

        report += f"\n{'=' * 55}\n"
        return report


# Singleton
cost_tracker = CostTracker()
