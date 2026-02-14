"""
NEXUS KPI Tracker

Tracks productivity, quality, cost, and security metrics.
Stores historical data in SQLite for trend analysis.
"""

import json
import os
import sqlite3
import time

DB_PATH = os.path.expanduser("~/.nexus/kpi.db")


class KPITracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kpi_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                category TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_kpi_category
            ON kpi_snapshots(category, metric)
        """)
        conn.commit()
        conn.close()

    def record(self, category: str, metric: str, value: float, metadata: dict | None = None):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO kpi_snapshots (timestamp, category, metric, value, metadata) VALUES (?, ?, ?, ?, ?)",
            (time.time(), category, metric, value, json.dumps(metadata or {})),
        )
        conn.commit()
        conn.close()

    def record_task_completion(self, agent: str, task: str, cost: float, duration_sec: float):
        self.record("productivity", "task_completed", 1, {
            "agent": agent, "task": task, "cost": cost, "duration": duration_sec
        })
        self.record("cost", "task_cost", cost, {"agent": agent, "task": task})

    def record_quality_event(self, event_type: str, agent: str, details: str = ""):
        value = 1.0 if event_type in ("lint_pass", "test_pass", "security_clean", "pr_approved") else 0.0
        self.record("quality", event_type, value, {"agent": agent, "details": details})

    def record_pr_cycle(self, pr_url: str, reviews: int, approved_first_try: bool):
        self.record("productivity", "pr_reviews", reviews, {"pr": pr_url})
        if approved_first_try:
            self.record("quality", "first_try_approval", 1)

    def get_summary(self, hours: float = 24) -> dict:
        cutoff = time.time() - (hours * 3600)
        conn = sqlite3.connect(self.db_path)

        tasks = conn.execute(
            "SELECT COUNT(*) FROM kpi_snapshots WHERE category='productivity' AND metric='task_completed' AND timestamp > ?",
            (cutoff,),
        ).fetchone()[0]

        total_cost = conn.execute(
            "SELECT COALESCE(SUM(value), 0) FROM kpi_snapshots WHERE category='cost' AND metric='task_cost' AND timestamp > ?",
            (cutoff,),
        ).fetchone()[0]

        lint_passes = conn.execute(
            "SELECT COUNT(*) FROM kpi_snapshots WHERE category='quality' AND metric='lint_pass' AND timestamp > ?",
            (cutoff,),
        ).fetchone()[0]

        lint_fails = conn.execute(
            "SELECT COUNT(*) FROM kpi_snapshots WHERE category='quality' AND metric='lint_fail' AND timestamp > ?",
            (cutoff,),
        ).fetchone()[0]

        first_try = conn.execute(
            "SELECT COUNT(*) FROM kpi_snapshots WHERE category='quality' AND metric='first_try_approval' AND timestamp > ?",
            (cutoff,),
        ).fetchone()[0]

        total_prs = conn.execute(
            "SELECT COUNT(*) FROM kpi_snapshots WHERE category='productivity' AND metric='pr_reviews' AND timestamp > ?",
            (cutoff,),
        ).fetchone()[0]

        conn.close()

        lint_total = lint_passes + lint_fails
        lint_rate = (lint_passes / lint_total * 100) if lint_total > 0 else 100
        first_try_rate = (first_try / total_prs * 100) if total_prs > 0 else 100

        return {
            "period_hours": hours,
            "tasks_completed": tasks,
            "total_cost": total_cost,
            "lint_pass_rate": lint_rate,
            "first_try_approval_rate": first_try_rate,
            "total_prs": total_prs,
        }

    def generate_dashboard(self, hours: float = 24) -> str:
        summary = self.get_summary(hours)
        from src.agents.registry import registry
        from src.agents.sdk_bridge import cost_tracker

        agents = registry.get_active_agents()

        # Pull optimization tips from costwise analyzer
        tips_section = ""
        try:
            from src.cost.costwise_bridge import get_optimization_tips
            tips = get_optimization_tips(days=30)
            if tips:
                tips_section = "\nCOST OPTIMIZATION (costwise)\n"
                for tip in tips[:5]:
                    icon = "!!" if tip["severity"] == "critical" else "!" if tip["severity"] == "warning" else "i"
                    tips_section += f"  [{icon}] {tip['message']}\n"
        except Exception:
            pass

        return f"""
NEXUS KPI Dashboard ({summary['period_hours']:.0f}h window)
{'=' * 55}

PRODUCTIVITY
  Tasks Completed:        {summary['tasks_completed']}
  PRs Created:            {summary['total_prs']}

QUALITY
  Lint Pass Rate:         {summary['lint_pass_rate']:.0f}%  {'✅' if summary['lint_pass_rate'] >= 95 else '⚠️' if summary['lint_pass_rate'] >= 80 else '❌'}
  First-Try PR Approval:  {summary['first_try_approval_rate']:.0f}%  {'✅' if summary['first_try_approval_rate'] >= 80 else '⚠️'}

COST
  Period Spend:           ${summary['total_cost']:.2f}
  Session Spend:          ${cost_tracker.total_cost:.2f}
  Hourly Rate:            ${cost_tracker.hourly_rate:.2f}/hr  {'✅' if cost_tracker.hourly_rate <= 1.0 else '⚠️' if cost_tracker.hourly_rate <= 2.0 else '❌'}
  Target:                 $1.00/hr

ORGANIZATION
  Active Agents:          {len(agents)}
  Opus:                   {len([a for a in agents if a.model == 'opus'])}
  Sonnet:                 {len([a for a in agents if a.model == 'sonnet'])}
  Haiku:                  {len([a for a in agents if a.model == 'haiku'])}
  External:               {len([a for a in agents if a.provider != 'anthropic'])}
{tips_section}
{'=' * 55}
"""


# Singleton
kpi_tracker = KPITracker()
