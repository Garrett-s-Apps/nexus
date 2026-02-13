"""SSoT service for agent-related data. Hides multi-database reality."""

from dataclasses import dataclass, field

from src.agents.registry import registry
from src.ml.store import ml_store


@dataclass
class AgentProfile:
    """Composite view of an agent across all data sources."""
    agent_id: str
    name: str = ""
    model: str = ""
    layer: str = ""
    status: str = ""
    tools: list[str] = field(default_factory=list)
    # Performance (from ml.db)
    success_rate: float = 0.0
    avg_cost: float = 0.0
    avg_defects: float = 0.0
    total_tasks: int = 0
    # Circuit state (from registry.db)
    circuit_trips: int = 0
    recoveries: int = 0


class AgentService:
    """Unified access to agent data across all databases."""

    def get_agent_profile(self, agent_id: str) -> AgentProfile | None:
        """Get composite agent profile with config, performance, circuit state, and cost."""
        agent = registry.get_agent(agent_id)
        if not agent:
            return None

        profile = AgentProfile(
            agent_id=agent_id,
            name=agent.name,
            model=agent.model,
            layer=agent.layer,
            status=agent.status,
            tools=agent.tools,
        )

        # Performance stats from ml.db
        try:
            success_data = ml_store.get_agent_success_rate(agent_id)
            profile.success_rate = success_data.get("success_rate", 0.0)
            profile.total_tasks = success_data.get("total_tasks", 0)
            profile.avg_cost = success_data.get("avg_cost", 0.0)
            profile.avg_defects = success_data.get("avg_defects", 0.0)
        except Exception:
            pass

        # Circuit breaker stats from registry.db
        try:
            reliability = registry.get_agent_reliability(agent_id)
            profile.circuit_trips = reliability.get("circuit_trips", 0)
            profile.recoveries = reliability.get("recoveries", 0)
        except Exception:
            pass

        return profile

    def list_agent_profiles(self) -> list[AgentProfile]:
        """Get profiles for all active agents."""
        agents = registry.get_active_agents()
        profiles = []
        for agent in agents:
            profile = self.get_agent_profile(agent.id)
            if profile:
                profiles.append(profile)
        return profiles


agent_service = AgentService()
