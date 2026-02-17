"""
NEXUS Adaptive Prompt Evolution (ARCH-015)

Updates agent system prompts based on learnings.
"""

import logging
import os
from datetime import UTC, datetime

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger("nexus.self_improvement.prompt_updater")


class PromptUpdater:
    """Update agent prompts based on learnings."""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            # Default to config/agents.yaml
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            config_path = os.path.join(base_path, "config", "agents.yaml")

        self.config_path = config_path

    def update_agent_prompt(self, agent_key: str, learnings: list[str]) -> bool:
        """Update agent system prompt based on learnings.

        Args:
            agent_key: Agent identifier (e.g., "code_reviewer", "executor")
            learnings: List of learning strings to append

        Returns:
            True if update successful, False otherwise
        """
        try:
            # Load config/agents.yaml
            with open(self.config_path) as f:
                config = yaml.safe_load(f)

            if not config or "agents" not in config:
                logger.error("Invalid agents config file")
                return False

            # Find the agent
            agents = config["agents"]
            agent_config = None

            for agent in agents:
                if agent.get("key") == agent_key or agent.get("name") == agent_key:
                    agent_config = agent
                    break

            if not agent_config:
                logger.error("Agent not found: %s", agent_key)
                return False

            # Get current system prompt
            system_prompt = agent_config.get("system_prompt", "")

            # Check if there's already a learnings section
            learnings_section = "\n\n## Learnings from Self-Improvement\n"
            if learnings_section not in system_prompt:
                system_prompt += learnings_section

            # Append new learnings with timestamp
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
            for learning in learnings:
                learning_line = f"\n- [{timestamp}] {learning}"
                if learning_line not in system_prompt:
                    system_prompt += learning_line

            # Update the config
            agent_config["system_prompt"] = system_prompt

            # Save updated config
            with open(self.config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info("Updated prompt for agent: %s with %d learnings", agent_key, len(learnings))
            return True

        except Exception as e:
            logger.error("Failed to update agent prompt: %s", e)
            return False

    def add_learning_to_all_agents(self, learning: str) -> int:
        """Add a learning to all agents.

        Args:
            learning: Learning string to add

        Returns:
            Number of agents updated
        """
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)

            if not config or "agents" not in config:
                return 0

            updated_count = 0
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d")

            for agent in config["agents"]:
                system_prompt = agent.get("system_prompt", "")

                # Check if there's already a learnings section
                learnings_section = "\n\n## Learnings from Self-Improvement\n"
                if learnings_section not in system_prompt:
                    system_prompt += learnings_section

                # Append the learning
                learning_line = f"\n- [{timestamp}] {learning}"
                if learning_line not in system_prompt:
                    system_prompt += learning_line
                    agent["system_prompt"] = system_prompt
                    updated_count += 1

            if updated_count > 0:
                # Save updated config
                with open(self.config_path, "w") as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info("Added learning to %d agents", updated_count)
            return updated_count

        except Exception as e:
            logger.error("Failed to add learning to all agents: %s", e)
            return 0

    def get_agent_learnings(self, agent_key: str) -> list[str]:
        """Get all learnings for a specific agent.

        Args:
            agent_key: Agent identifier

        Returns:
            List of learning strings
        """
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)

            if not config or "agents" not in config:
                return []

            # Find the agent
            for agent in config["agents"]:
                if agent.get("key") == agent_key or agent.get("name") == agent_key:
                    system_prompt = agent.get("system_prompt", "")

                    # Extract learnings
                    learnings = []
                    in_learnings_section = False

                    for line in system_prompt.split("\n"):
                        if "## Learnings from Self-Improvement" in line:
                            in_learnings_section = True
                            continue

                        if in_learnings_section:
                            # Check if we've hit a new section
                            if line.startswith("##"):
                                break

                            # Extract learning items
                            if line.strip().startswith("-"):
                                learnings.append(line.strip()[1:].strip())

                    return learnings

            return []

        except Exception as e:
            logger.error("Failed to get agent learnings: %s", e)
            return []
