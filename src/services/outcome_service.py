"""SSoT service for task outcomes and ML data."""

from dataclasses import dataclass

from src.ml.feedback import get_learning_status
from src.ml.store import ml_store


@dataclass
class OutcomeSummary:
    total_outcomes: int = 0
    success_rate: float = 0.0
    avg_cost: float = 0.0
    avg_defects: float = 0.0
    training_data_count: int = 0


class OutcomeService:
    """Unified access to outcome and ML learning data."""

    def get_summary(self) -> OutcomeSummary:
        """Get aggregate outcome summary."""
        learning = get_learning_status()
        data_counts = learning.get("data", {})

        # Get aggregate stats from all outcomes
        try:
            outcomes = ml_store.get_outcomes(limit=1000)
            if outcomes:
                total = len(outcomes)
                successes = sum(1 for o in outcomes if o.get("outcome") == "complete")
                total_cost = sum(o.get("cost_usd", 0) for o in outcomes)
                total_defects = sum(o.get("defect_count", 0) for o in outcomes)

                return OutcomeSummary(
                    total_outcomes=total,
                    success_rate=successes / total if total > 0 else 0.0,
                    avg_cost=total_cost / total if total > 0 else 0.0,
                    avg_defects=total_defects / total if total > 0 else 0.0,
                    training_data_count=data_counts.get("task_outcomes", 0),
                )
        except Exception:
            pass

        return OutcomeSummary(
            training_data_count=data_counts.get("task_outcomes", 0),
        )


outcome_service = OutcomeService()
