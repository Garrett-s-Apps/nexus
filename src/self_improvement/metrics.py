"""
NEXUS Self-Improvement Metrics Tracker (ARCH-015)

Tracks improvement trends over time.
"""

import json
import logging
import os
from datetime import UTC, datetime

from src.config import NEXUS_DIR

logger = logging.getLogger("nexus.self_improvement.metrics")

METRICS_DB_PATH = os.path.join(NEXUS_DIR, "self_improvement_metrics.json")


class ImprovementMetrics:
    """Track self-improvement over time."""

    def __init__(self, metrics_path: str | None = None):
        self.metrics_path = metrics_path or METRICS_DB_PATH
        self._ensure_metrics_file()

    def _ensure_metrics_file(self):
        """Ensure metrics file exists."""
        os.makedirs(os.path.dirname(self.metrics_path), exist_ok=True)
        if not os.path.exists(self.metrics_path):
            initial_data = {
                "version": "1.0",
                "created_at": datetime.now(UTC).isoformat(),
                "analyses": []
            }
            with open(self.metrics_path, "w") as f:
                json.dump(initial_data, f, indent=2)

    def record_analysis(self, findings: list[dict], summary: dict):
        """Record analysis results.

        Args:
            findings: List of Finding dictionaries
            summary: Summary dictionary with counts by severity/category
        """
        with open(self.metrics_path) as f:
            data = json.load(f)

        # Calculate effort estimate
        total_effort_hours = self._calculate_effort_hours(findings)

        analysis_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_findings": len(findings),
            "by_severity": summary.get("bySeverity", {}),
            "by_category": summary.get("byCategory", {}),
            "total_effort_hours": total_effort_hours,
            "estimated_work_days": round(total_effort_hours / 8, 1),
            "findings_by_effort": self._count_by_effort(findings),
        }

        data["analyses"].append(analysis_record)

        # Keep only last 50 analyses
        if len(data["analyses"]) > 50:
            data["analyses"] = data["analyses"][-50:]

        with open(self.metrics_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("Recorded analysis metrics: %d findings", len(findings))

    def get_trend(self) -> dict:
        """Show improvement trend over time.

        Returns:
            {
                "total_analyses": int,
                "first_analysis": dict,
                "latest_analysis": dict,
                "trend": {
                    "findings_change": int,  # negative = improvement
                    "findings_change_pct": float,
                    "critical_change": int,
                    "high_change": int,
                    "improving": bool
                },
                "average_effort_hours": float,
                "time_span_days": float
            }
        """
        with open(self.metrics_path) as f:
            data = json.load(f)

        analyses = data.get("analyses", [])

        if not analyses:
            return {
                "total_analyses": 0,
                "message": "No analysis data available"
            }

        if len(analyses) == 1:
            return {
                "total_analyses": 1,
                "latest_analysis": analyses[0],
                "message": "Need at least 2 analyses to show trend"
            }

        first = analyses[0]
        latest = analyses[-1]

        # Calculate changes
        findings_change = latest["total_findings"] - first["total_findings"]
        findings_change_pct = (
            (findings_change / first["total_findings"] * 100)
            if first["total_findings"] > 0
            else 0
        )

        first_critical = first.get("by_severity", {}).get("CRITICAL", 0)
        latest_critical = latest.get("by_severity", {}).get("CRITICAL", 0)
        critical_change = latest_critical - first_critical

        first_high = first.get("by_severity", {}).get("HIGH", 0)
        latest_high = latest.get("by_severity", {}).get("HIGH", 0)
        high_change = latest_high - first_high

        # Calculate time span
        first_time = datetime.fromisoformat(first["timestamp"])
        latest_time = datetime.fromisoformat(latest["timestamp"])
        time_span_days = (latest_time - first_time).total_seconds() / 86400

        # Calculate average effort
        avg_effort = sum(
            a.get("total_effort_hours", 0) for a in analyses
        ) / len(analyses)

        return {
            "total_analyses": len(analyses),
            "first_analysis": first,
            "latest_analysis": latest,
            "trend": {
                "findings_change": findings_change,
                "findings_change_pct": round(findings_change_pct, 1),
                "critical_change": critical_change,
                "high_change": high_change,
                "improving": findings_change < 0 and critical_change <= 0,
            },
            "average_effort_hours": round(avg_effort, 1),
            "time_span_days": round(time_span_days, 1),
        }

    def get_latest_analysis(self) -> dict | None:
        """Get the most recent analysis record."""
        with open(self.metrics_path) as f:
            data = json.load(f)

        analyses = data.get("analyses", [])
        return analyses[-1] if analyses else None

    def _calculate_effort_hours(self, findings: list[dict]) -> int:
        """Calculate total effort hours from findings."""
        total = 0
        for finding in findings:
            effort = finding.get("effort", "M")
            # Map effort to hours
            effort_map = {
                "XS": 0.5,
                "S": 2,
                "M": 8,
                "L": 24,
                "XL": 80,
            }
            total += effort_map.get(effort, 8)
        return round(total)

    def _count_by_effort(self, findings: list[dict]) -> dict:
        """Count findings by effort level."""
        counts = {"XS": 0, "S": 0, "M": 0, "L": 0, "XL": 0}
        for finding in findings:
            effort = finding.get("effort", "M")
            if effort in counts:
                counts[effort] += 1
        return counts
