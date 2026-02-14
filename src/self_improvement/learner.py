"""
NEXUS Failure Pattern Analyzer (ARCH-015)

Learns from failures and updates agent prompts accordingly.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from src.memory.store import memory

logger = logging.getLogger("nexus.self_improvement.learner")


class FailurePatternAnalyzer:
    """Analyze common mistakes from memory.db and learn from them."""

    async def analyze_failure_patterns(self, days_back: int = 30) -> dict:
        """Analyze failure patterns from memory.db.

        Args:
            days_back: Number of days to look back

        Returns:
            {
                "total_failures": int,
                "patterns": list[dict],
                "recommendations": list[str],
                "by_agent": dict,
                "by_task_type": dict,
                "common_errors": list[dict]
            }
        """
        # Get failed tasks from memory
        since = (datetime.now(UTC) - timedelta(days=days_back)).isoformat()

        # Query event log for failures
        all_events = memory.get_recent_events(limit=1000)

        # Filter to failure events
        failure_events = [
            e for e in all_events
            if e["event_type"] in ["task_failed", "defect_filed"]
            and e["timestamp"] >= since
        ]

        logger.info("Analyzing %d failure events from last %d days", len(failure_events), days_back)

        # Analyze patterns
        patterns = []
        by_agent: dict[str, int] = defaultdict(int)
        by_task_type: dict[str, int] = defaultdict(int)
        error_messages = []

        for event in failure_events:
            data = json.loads(event.get("data", "{}"))

            # Track by agent
            source = event.get("source", "unknown")
            by_agent[source] += 1

            # Extract error info
            error = data.get("error", "")
            if error:
                error_messages.append({
                    "error": error[:200],
                    "source": source,
                    "timestamp": event["timestamp"]
                })

            # Try to classify task type
            task_id = data.get("task_id", "")
            task_type = self._classify_task_type(task_id, error)
            by_task_type[task_type] += 1

        # Find common error patterns
        common_errors = self._find_common_error_patterns(error_messages)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            by_agent,
            by_task_type,
            common_errors
        )

        # Find specific patterns
        patterns = self._extract_patterns(error_messages)

        return {
            "total_failures": len(failure_events),
            "patterns": patterns,
            "recommendations": recommendations,
            "by_agent": dict(by_agent),
            "by_task_type": dict(by_task_type),
            "common_errors": common_errors[:10],  # Top 10
            "time_period_days": days_back,
        }

    def _classify_task_type(self, task_id: str, error: str) -> str:
        """Classify task type from task_id or error message."""
        task_id_lower = task_id.lower()
        error_lower = error.lower()

        if "test" in task_id_lower or "test" in error_lower:
            return "testing"
        elif "build" in task_id_lower or "compile" in error_lower:
            return "build"
        elif "deploy" in task_id_lower or "deployment" in error_lower:
            return "deployment"
        elif "security" in task_id_lower or "auth" in error_lower:
            return "security"
        elif "api" in task_id_lower or "endpoint" in error_lower:
            return "api"
        elif "database" in task_id_lower or "sql" in error_lower:
            return "database"
        else:
            return "other"

    def _find_common_error_patterns(self, error_messages: list[dict]) -> list[dict]:
        """Find frequently occurring error patterns."""
        error_counts: dict[str, int] = defaultdict(int)

        for err_data in error_messages:
            error = err_data["error"]

            # Normalize error message
            normalized = re.sub(r'\d+', 'N', error)  # Replace numbers
            normalized = re.sub(r'0x[0-9a-fA-F]+', '0xHEX', normalized)  # Replace hex
            normalized = re.sub(r'/[^\s]+/', '/PATH/', normalized)  # Replace paths

            error_counts[normalized] += 1

        # Sort by frequency
        sorted_errors = sorted(
            error_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return [
            {"pattern": pattern, "count": count}
            for pattern, count in sorted_errors[:10]
        ]

    def _extract_patterns(self, error_messages: list[dict]) -> list[dict]:
        """Extract specific failure patterns."""
        patterns = []

        # Pattern: Timeout errors
        timeout_count = sum(
            1 for e in error_messages
            if "timeout" in e["error"].lower()
        )
        if timeout_count > 0:
            patterns.append({
                "type": "timeout",
                "count": timeout_count,
                "description": "Tasks timing out",
                "recommendation": "Consider increasing timeout limits or optimizing long-running operations"
            })

        # Pattern: Import/dependency errors
        import_count = sum(
            1 for e in error_messages
            if "import" in e["error"].lower() or "module" in e["error"].lower()
        )
        if import_count > 0:
            patterns.append({
                "type": "import_dependency",
                "count": import_count,
                "description": "Import or dependency errors",
                "recommendation": "Review dependency management and installation steps"
            })

        # Pattern: Type errors
        type_count = sum(
            1 for e in error_messages
            if "type error" in e["error"].lower() or "typeerror" in e["error"].lower()
        )
        if type_count > 0:
            patterns.append({
                "type": "type_error",
                "count": type_count,
                "description": "Type errors",
                "recommendation": "Improve type checking and validation"
            })

        # Pattern: Permission errors
        permission_count = sum(
            1 for e in error_messages
            if "permission" in e["error"].lower() or "access denied" in e["error"].lower()
        )
        if permission_count > 0:
            patterns.append({
                "type": "permission",
                "count": permission_count,
                "description": "Permission/access errors",
                "recommendation": "Review file permissions and access controls"
            })

        return patterns

    def _generate_recommendations(
        self,
        by_agent: dict,
        by_task_type: dict,
        common_errors: list[dict]
    ) -> list[str]:
        """Generate actionable recommendations based on failure analysis."""
        recommendations = []

        # Check for problematic agents
        if by_agent:
            max_failures = max(by_agent.values())
            problematic_agents = [
                agent for agent, count in by_agent.items()
                if count >= max_failures * 0.5  # 50% of max
            ]

            if problematic_agents:
                recommendations.append(
                    f"Review and improve prompts for agents: {', '.join(problematic_agents)}"
                )

        # Check for problematic task types
        if by_task_type:
            max_task_failures = max(by_task_type.values())
            problematic_types = [
                task_type for task_type, count in by_task_type.items()
                if count >= max_task_failures * 0.5
            ]

            if problematic_types:
                recommendations.append(
                    f"Focus improvement efforts on: {', '.join(problematic_types)}"
                )

        # Check for common errors
        if common_errors and len(common_errors) > 0:
            top_error = common_errors[0]
            if top_error["count"] >= 3:
                recommendations.append(
                    f"Address recurring error pattern: {top_error['pattern'][:100]}"
                )

        # General recommendations
        if not recommendations:
            recommendations.append("Continue monitoring for patterns")

        return recommendations
