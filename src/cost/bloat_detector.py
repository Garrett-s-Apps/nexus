"""
Model Bloat Detector — costwise-powered smart model routing.

Analyzes costwise data to detect agents over-consuming expensive models
when cheaper alternatives would suffice. Goes beyond simple budget caps
by examining per-agent cost efficiency patterns.

Signals:
- High cost-per-call agents using opus/o3 for routine tasks
- Agents with high error rates on expensive models (wasted spend)
- Agents that could be downgraded based on task complexity patterns
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("nexus.cost.bloat")

# Models ranked by cost tier (0 = cheapest)
_MODEL_TIERS: dict[str, int] = {
    "haiku": 0,
    "claude-code:haiku": 0,
    "gemini-2.0-flash": 0,
    "sonnet": 1,
    "claude-code:sonnet": 1,
    "gpt-4o": 1,
    "gemini-2.5-pro": 2,
    "o3": 3,
    "opus": 3,
    "claude-code:opus": 0,  # Free under Max sub
}

# Downgrade paths: model -> cheaper alternative
_SMART_DOWNGRADE: dict[str, str] = {
    "opus": "sonnet",
    "o3": "gpt-4o",
    "sonnet": "haiku",
    "gpt-4o": "gemini-2.0-flash",
    "gemini-2.5-pro": "gemini-2.0-flash",
}

# Thresholds
BLOAT_SCORE_DOWNGRADE_THRESHOLD = 65  # Auto-downgrade above this
HIGH_ERROR_RATE_THRESHOLD = 0.15  # 15% error rate = wasteful
HIGH_COST_PER_CALL_THRESHOLD = 0.05  # $0.05/call on tier-1 models is bloated
MIN_CALLS_FOR_ANALYSIS = 5  # Need enough data to judge


@dataclass
class AgentBloatProfile:
    """Bloat analysis for a single agent."""
    agent_name: str
    bloat_score: int = 0  # 0-100
    total_cost: float = 0.0
    call_count: int = 0
    avg_cost_per_call: float = 0.0
    error_rate: float = 0.0
    primary_model: str = ""
    recommended_model: str = ""
    reasons: list[str] = field(default_factory=list)
    should_downgrade: bool = False


@dataclass
class BloatReport:
    """System-wide bloat analysis."""
    timestamp: float = 0.0
    overall_bloat_score: int = 0
    total_waste_estimate: float = 0.0
    agents_flagged: int = 0
    agents_analyzed: int = 0
    profiles: dict[str, AgentBloatProfile] = field(default_factory=dict)
    tips_applied: int = 0


class BloatDetector:
    """Singleton that periodically analyzes cost data for model bloat."""

    def __init__(self):
        self._lock = threading.Lock()
        self._report: BloatReport = BloatReport()
        self._downgrade_overrides: dict[str, str] = {}  # agent -> forced model
        self._last_analysis: float = 0.0
        self._enabled = True

    def analyze(self, days: int = 7) -> BloatReport:
        """Run bloat analysis using costwise data. Called by background scheduler."""
        try:
            from src.cost.costwise_bridge import _get_costwise_tracker

            tracker = _get_costwise_tracker()
            records = tracker.storage.query(since=time.time() - (days * 86400))

            if not records:
                return self._report

            # Group by agent tag
            by_agent: dict[str, list[Any]] = {}
            for r in records:
                agent = ""
                if hasattr(r, "tags") and r.tags:
                    agent = r.tags.get("agent", "unknown")
                else:
                    agent = "unknown"
                by_agent.setdefault(agent, []).append(r)

            report = BloatReport(
                timestamp=time.time(),
                agents_analyzed=len(by_agent),
            )
            overrides: dict[str, str] = {}
            total_waste = 0.0

            for agent_name, agent_records in by_agent.items():
                if len(agent_records) < MIN_CALLS_FOR_ANALYSIS:
                    continue

                profile = self._analyze_agent(agent_name, agent_records)
                report.profiles[agent_name] = profile

                if profile.should_downgrade:
                    report.agents_flagged += 1
                    overrides[agent_name] = profile.recommended_model
                    total_waste += profile.total_cost * (profile.bloat_score / 100) * 0.5

            report.total_waste_estimate = round(total_waste, 4)
            report.overall_bloat_score = (
                round(sum(p.bloat_score for p in report.profiles.values()) / len(report.profiles))
                if report.profiles
                else 0
            )

            # Apply costwise optimization tips count
            try:
                from src.cost.costwise_bridge import get_optimization_tips
                tips = get_optimization_tips(days=days)
                report.tips_applied = len(tips)
            except Exception:
                pass

            with self._lock:
                self._report = report
                self._downgrade_overrides = overrides
                self._last_analysis = time.time()

            logger.info(
                "Bloat analysis complete: score=%d, flagged=%d/%d, waste_est=$%.4f",
                report.overall_bloat_score,
                report.agents_flagged,
                report.agents_analyzed,
                report.total_waste_estimate,
            )

            return report

        except Exception as e:
            logger.warning("Bloat analysis failed (non-fatal): %s", e)
            return self._report

    def _analyze_agent(self, agent_name: str, records: list[Any]) -> AgentBloatProfile:
        """Compute bloat profile for a single agent."""
        profile = AgentBloatProfile(agent_name=agent_name)
        profile.call_count = len(records)
        profile.total_cost = sum(r.total_cost for r in records)
        profile.avg_cost_per_call = profile.total_cost / profile.call_count if profile.call_count else 0

        # Error rate
        errors = sum(1 for r in records if not r.success)
        profile.error_rate = errors / len(records)

        # Primary model (most used)
        model_counts: dict[str, int] = {}
        model_costs: dict[str, float] = {}
        for r in records:
            model_counts[r.model] = model_counts.get(r.model, 0) + 1
            model_costs[r.model] = model_costs.get(r.model, 0) + r.total_cost
        profile.primary_model = max(model_counts, key=lambda m: model_counts[m]) if model_counts else ""

        # Bloat scoring
        score = 0
        reasons = []

        # Factor 1: High error rate on expensive models (30 pts max)
        tier = _MODEL_TIERS.get(profile.primary_model, 1)
        if profile.error_rate > HIGH_ERROR_RATE_THRESHOLD and tier >= 2:
            factor = min(30, int(profile.error_rate * 100))
            score += factor
            reasons.append(
                f"High error rate ({profile.error_rate:.0%}) on expensive model {profile.primary_model}"
            )

        # Factor 2: High cost-per-call for the model tier (30 pts max)
        if tier <= 1 and profile.avg_cost_per_call > HIGH_COST_PER_CALL_THRESHOLD:
            factor = min(30, int((profile.avg_cost_per_call / HIGH_COST_PER_CALL_THRESHOLD) * 10))
            score += factor
            reasons.append(
                f"High avg cost ${profile.avg_cost_per_call:.4f}/call suggests prompt bloat"
            )
        elif tier >= 2 and profile.avg_cost_per_call > HIGH_COST_PER_CALL_THRESHOLD * 3:
            factor = min(30, int((profile.avg_cost_per_call / (HIGH_COST_PER_CALL_THRESHOLD * 3)) * 15))
            score += factor
            reasons.append(
                f"Very high avg cost ${profile.avg_cost_per_call:.4f}/call on tier-{tier} model"
            )

        # Factor 3: Using expensive model for high-volume calls (25 pts max)
        if tier >= 2 and profile.call_count > 20:
            factor = min(25, profile.call_count // 4)
            score += factor
            reasons.append(
                f"{profile.call_count} calls on expensive model {profile.primary_model} — consider cheaper tier"
            )

        # Factor 4: Cost concentration (15 pts max)
        if profile.total_cost > 1.0 and tier >= 2:
            factor = min(15, int(profile.total_cost * 3))
            score += factor
            reasons.append(f"${profile.total_cost:.2f} total spend on {profile.primary_model}")

        profile.bloat_score = min(100, score)
        profile.reasons = reasons
        profile.should_downgrade = score >= BLOAT_SCORE_DOWNGRADE_THRESHOLD

        # Recommend downgrade
        if profile.should_downgrade and profile.primary_model in _SMART_DOWNGRADE:
            profile.recommended_model = _SMART_DOWNGRADE[profile.primary_model]
        else:
            profile.recommended_model = profile.primary_model

        return profile

    def get_effective_model(self, agent_name: str, requested_model: str) -> str:
        """Return the model to use, applying bloat-based downgrades.

        Called by the cost tracker after budget enforcement.
        Only downgrades — never upgrades a model.
        """
        if not self._enabled:
            return requested_model

        # Snapshot under lock to avoid race condition
        with self._lock:
            override = self._downgrade_overrides.get(agent_name)
            # Stale report guard: disable downgrades if analysis is >1hr old
            if self._last_analysis > 0 and (time.time() - self._last_analysis) > 3600:
                return requested_model

        if not override:
            return requested_model

        # Only downgrade, never upgrade
        requested_tier = _MODEL_TIERS.get(requested_model, 1)
        override_tier = _MODEL_TIERS.get(override, 1)
        if override_tier < requested_tier:
            logger.debug(
                "Bloat downgrade: %s %s -> %s",
                agent_name,
                requested_model,
                override,
            )
            return override

        return requested_model

    @property
    def report(self) -> BloatReport:
        with self._lock:
            return self._report

    @property
    def enabled(self) -> bool:
        return bool(self._enabled)

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if not value:
            with self._lock:
                self._downgrade_overrides.clear()

    def get_bloat_summary(self) -> dict[str, Any]:
        """JSON-safe summary for API responses."""
        with self._lock:
            r = self._report
        return {
            "overall_bloat_score": r.overall_bloat_score,
            "total_waste_estimate": r.total_waste_estimate,
            "agents_flagged": r.agents_flagged,
            "agents_analyzed": r.agents_analyzed,
            "tips_applied": r.tips_applied,
            "last_analysis": self._last_analysis,
            "enabled": self._enabled,
            "downgrade_overrides": dict(self._downgrade_overrides),
            "profiles": {
                name: {
                    "bloat_score": p.bloat_score,
                    "total_cost": p.total_cost,
                    "call_count": p.call_count,
                    "avg_cost_per_call": round(p.avg_cost_per_call, 6),
                    "error_rate": round(p.error_rate, 4),
                    "primary_model": p.primary_model,
                    "recommended_model": p.recommended_model,
                    "should_downgrade": p.should_downgrade,
                    "reasons": p.reasons,
                }
                for name, p in r.profiles.items()
            },
        }

    def get_efficiency_report(self, days: int = 30) -> dict[str, Any]:
        """Cost efficiency metrics for the whole system."""
        try:
            from src.cost.costwise_bridge import get_model_breakdown, get_summary

            summary = get_summary(days=days)
            models = get_model_breakdown(days=days)

            total_cost = summary.get("total_cost", 0)
            total_requests = summary.get("total_requests", 0)

            # Compute efficiency: what % of spend is on tier-2+ models?
            expensive_spend = 0.0
            cheap_spend = 0.0
            for m in models:
                model_name = m.get("model", "")
                cost = m.get("total_cost", 0)
                tier = _MODEL_TIERS.get(model_name, 1)
                if tier >= 2:
                    expensive_spend += cost
                else:
                    cheap_spend += cost

            efficiency_ratio = (
                round(cheap_spend / total_cost * 100, 1) if total_cost > 0 else 100.0
            )

            return {
                "period_days": days,
                "total_cost": total_cost,
                "total_requests": total_requests,
                "expensive_model_spend": round(expensive_spend, 4),
                "cheap_model_spend": round(cheap_spend, 4),
                "efficiency_ratio": efficiency_ratio,  # Higher = better
                "avg_cost_per_request": summary.get("avg_cost_per_request", 0),
                "error_rate": summary.get("error_rate", 0),
                "bloat_score": self._report.overall_bloat_score,
                "agents_flagged": self._report.agents_flagged,
            }
        except Exception as e:
            logger.warning("Efficiency report failed: %s", e)
            return {"error": str(e)}


# Singleton
bloat_detector = BloatDetector()
