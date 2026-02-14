"""
Provider Factory - Feature-flagged provider abstraction.

Allows NEXUS to use either:
1. Old code path (direct Anthropic API calls)
2. New SDK path (nexus_sdk providers)

Controlled by NEXUS_USE_SDK_PROVIDERS environment variable.
"""

import logging
import os
from typing import Any

logger = logging.getLogger("nexus.provider_factory")

# Feature flag - set to "1" to enable SDK providers
USE_SDK_PROVIDERS = os.environ.get("NEXUS_USE_SDK_PROVIDERS", "0") == "1"

# Default provider
DEFAULT_PROVIDER = os.environ.get("NEXUS_PROVIDER", "claude")


class ProviderFactory:
    """Factory for creating AI providers with feature flag support."""

    def __init__(self):
        """Initialize provider factory."""
        self._sdk_provider: Any = None
        self._initialized = False

    def _init_sdk_provider(self) -> Any:
        """Lazy-initialize SDK provider (only when USE_SDK_PROVIDERS=1)."""
        if self._initialized:
            return self._sdk_provider

        if not USE_SDK_PROVIDERS:
            self._initialized = True
            return None

        # Import SDK only when needed (feature flag enabled)
        try:
            from src.config import get_key

            if DEFAULT_PROVIDER == "claude":
                # Add packages/nexus-sdk to Python path temporarily
                import sys
                sdk_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "packages",
                    "nexus-sdk",
                )
                if sdk_path not in sys.path:
                    sys.path.insert(0, sdk_path)

                from nexus_sdk.providers.claude import ClaudeProvider

                api_key = get_key("ANTHROPIC_API_KEY")
                if not api_key:
                    logger.warning("ANTHROPIC_API_KEY not set, SDK provider unavailable")
                    self._initialized = True
                    return None

                self._sdk_provider = ClaudeProvider(api_key=api_key)
                logger.info("✅ SDK provider initialized: ClaudeProvider")

            elif DEFAULT_PROVIDER == "openai":
                from nexus_sdk.providers.openai_provider import OpenAIProvider

                api_key = get_key("OPENAI_API_KEY")
                if not api_key:
                    logger.warning("OPENAI_API_KEY not set, SDK provider unavailable")
                    self._initialized = True
                    return None

                self._sdk_provider = OpenAIProvider(api_key=api_key)
                logger.info("✅ SDK provider initialized: OpenAIProvider")

            elif DEFAULT_PROVIDER == "gemini":
                from nexus_sdk.providers.gemini import GeminiProvider

                api_key = get_key("GOOGLE_AI_API_KEY")
                if not api_key:
                    logger.warning("GOOGLE_AI_API_KEY not set, SDK provider unavailable")
                    self._initialized = True
                    return None

                self._sdk_provider = GeminiProvider(api_key=api_key)
                logger.info("✅ SDK provider initialized: GeminiProvider")

            else:
                logger.warning(f"Unknown provider: {DEFAULT_PROVIDER}, defaulting to Claude")
                from nexus_sdk.providers.claude import ClaudeProvider

                api_key = get_key("ANTHROPIC_API_KEY")
                if api_key:
                    self._sdk_provider = ClaudeProvider(api_key=api_key)
                    logger.info("✅ SDK provider initialized: ClaudeProvider (fallback)")

        except ImportError as e:
            logger.warning(f"SDK not available: {e}. Using legacy code path.")
            self._sdk_provider = None

        self._initialized = True
        return self._sdk_provider

    async def execute(
        self,
        prompt: str,
        model: str = "sonnet",
        system_prompt: str = "",
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Execute a prompt using configured provider.

        Returns dict with: output, tokens_in, tokens_out, cost_usd, model

        If SDK providers are disabled, returns None (caller uses old path).
        """
        if not USE_SDK_PROVIDERS:
            return None  # type: ignore[return-value]

        provider = self._init_sdk_provider()
        if not provider:
            return None  # type: ignore[return-value]

        # Execute via SDK
        result = await provider.execute(
            prompt=prompt,
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

        # Convert TaskResult to dict format NEXUS expects
        return {
            "output": result.output,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "model": result.model,
            "status": result.status,
        }

    def is_sdk_enabled(self) -> bool:
        """Check if SDK providers are enabled."""
        return USE_SDK_PROVIDERS


# Global factory instance
provider_factory = ProviderFactory()


def get_provider_factory() -> ProviderFactory:
    """Get the global provider factory instance."""
    return provider_factory
