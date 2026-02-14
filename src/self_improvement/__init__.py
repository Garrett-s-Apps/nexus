"""
NEXUS Self-Improvement Module (ARCH-015)

Enables Nexus to analyze and improve its own codebase through:
- Automated self-analysis
- Auto-fixing low/medium severity issues
- Creating PRs for high/critical issues
- Learning from failure patterns
- Adaptive prompt evolution
"""

from src.self_improvement.analyzer import SelfImprovementLoop
from src.self_improvement.metrics import ImprovementMetrics
from src.self_improvement.learner import FailurePatternAnalyzer

__all__ = [
    "SelfImprovementLoop",
    "ImprovementMetrics",
    "FailurePatternAnalyzer",
]
