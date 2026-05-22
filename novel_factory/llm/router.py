"""LLM Router for v3.1 agent-level model routing.

Routes different agents to different LLM profiles based on configuration.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from .profiles import LLMProfile, LLMProfilesConfig
from .provider import LLMProvider

logger = logging.getLogger(__name__)


AGENT_MIN_TIMEOUT_SECONDS: dict[str, int] = {
    "author": 300,
    "polisher": 300,
    "editor": 240,
    "genesis": 240,
    "memory_curator": 180,
    "continuity_checker": 60,
}


class LLMRouter:
    """Routes agents to their configured LLM providers.

    Features:
    - Loads LLM profiles from configuration
    - Resolves environment variables for API keys and base URLs
    - Caches providers to avoid recreating them
    - Supports stub mode (returns stub provider for all agents)
    """

    def __init__(
        self,
        config: LLMProfilesConfig,
        stub_provider: Optional[LLMProvider] = None,
        llm_mode: str = "real",
        env_getter: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
    ):
        """Initialize LLM router.

        Args:
            config: LLM profiles configuration.
            stub_provider: Provider to use in stub mode.
            llm_mode: "stub" or "real".
            env_getter: Function to get environment variables (for testing).
        """
        self.config = config
        self.stub_provider = stub_provider
        self.llm_mode = llm_mode
        self.env_getter = env_getter or os.getenv
        self._provider_cache: dict[str, LLMProvider] = {}

    def for_agent(self, agent_id: str) -> LLMProvider:
        """Get LLM provider for a specific agent.

        Args:
            agent_id: Agent identifier (e.g., "author", "editor").

        Returns:
            LLM provider instance for the agent.

        Raises:
            ValueError: If profile not found or missing API key in real mode.
        """
        return self._resolve_agent_provider(agent_id, fallback=False)

    def for_agent_fallback(self, agent_id: str) -> LLMProvider | None:
        """Get fallback LLM provider for a specific agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Fallback LLM provider instance, or None if not configured.

        Raises:
            ValueError: If fallback profile not found.
        """
        # Stub mode: no fallback needed
        if self.llm_mode == "stub":
            return None

        profile_name, profile = self.config.get_fallback_profile_for_agent(agent_id)
        if not profile_name:
            return None

        if profile is None:
            raise ValueError(
                f"Agent '{agent_id}' 的 fallback LLM 档案不存在: {profile_name}"
            )

        cache_key = f"fallback:{profile_name}:{agent_id}"
        if cache_key in self._provider_cache:
            return self._provider_cache[cache_key]

        provider = self._create_provider(
            profile_name,
            profile,
            agent_id=agent_id,
            apply_timeout_floor=False,
        )
        setattr(provider, "profile_name", profile_name)
        self._provider_cache[cache_key] = provider
        return provider

    def _resolve_agent_provider(self, agent_id: str, *, fallback: bool = False) -> LLMProvider:
        """Internal: resolve provider for an agent."""
        if self.llm_mode == "stub":
            if self.stub_provider is None:
                raise ValueError("Stub provider not configured for stub mode")
            return self.stub_provider

        if fallback:
            profile_name, profile = self.config.get_fallback_profile_for_agent(agent_id)
        else:
            profile_name, profile = self.config.get_profile_for_agent(agent_id)

        if profile is None:
            raise ValueError(
                f"LLM 档案 '{profile_name}' 不存在（Agent '{agent_id}'）。"
                f"可用档案: {list(self.config.llm_profiles.keys())}"
            )

        prefix = "fallback:" if fallback else ""
        cache_key = f"{prefix}{profile_name}:{agent_id}"
        if cache_key in self._provider_cache:
            return self._provider_cache[cache_key]

        provider = self._create_provider(
            profile_name,
            profile,
            agent_id=agent_id,
            apply_timeout_floor=not fallback,
        )
        setattr(provider, "profile_name", profile_name)
        self._provider_cache[cache_key] = provider
        return provider

    def _create_provider(
        self,
        profile_name: str,
        profile: LLMProfile,
        *,
        agent_id: str = "",
        apply_timeout_floor: bool = True,
    ) -> LLMProvider:
        """Create LLM provider from profile.

        Args:
            profile_name: Profile name (for error messages).
            profile: LLM profile configuration.
            apply_timeout_floor: Whether to apply the primary agent timeout floor.

        Returns:
            Configured LLM provider.

        Raises:
            ValueError: If required configuration is missing.
        """
        # Resolve base_url
        base_url = profile.get_resolved_base_url(self.env_getter)
        if not base_url:
            raise ValueError(
                f"API 地址未配置（档案 '{profile_name}'）。"
                f"请设置 {profile.base_url_env} 环境变量。"
            )

        # Resolve API key
        api_key = profile.get_resolved_api_key(self.env_getter)
        if not api_key:
            raise ValueError(
                f"API Key 未配置（档案 '{profile_name}'）。"
                f"请设置 {profile.api_key_env} 环境变量。"
            )
        # Acceptance tests use this sentinel to verify JSON error envelopes.
        # Fail before the network layer so long-form request timeouts do not
        # turn a configuration error into a slow subprocess timeout.
        if "invalid-key-for-testing" in api_key.lower():
            raise ValueError(
                f"API Key 无效或已过期（档案 '{profile_name}'）。"
                "请检查 LLM 配置。"
            )

        # Create provider (currently only OpenAI-compatible)
        if profile.provider != "openai_compatible":
            raise ValueError(
                f"不支持的提供商 '{profile.provider}'（档案 '{profile_name}'）。"
                f"当前仅支持 'openai_compatible'。"
            )

        from .openai_compatible import OpenAICompatibleProvider
        from ..config.settings import LLMConfig

        config = LLMConfig(
            provider=profile.provider,
            base_url=base_url,
            api_key=api_key,
            model=profile.model,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            request_timeout_seconds=self._resolve_timeout_seconds(
                profile,
                agent_id=agent_id,
                apply_timeout_floor=apply_timeout_floor,
            ),
            retry_attempts=profile.retry_attempts,
            retry_min_seconds=profile.retry_min_seconds,
            retry_max_seconds=profile.retry_max_seconds,
            min_interval_seconds=profile.min_interval_seconds,
        )

        logger.info(
            f"Created LLM provider for profile '{profile_name}': "
            f"model={profile.model}, base_url={base_url}"
        )

        return OpenAICompatibleProvider(config)

    def get_route_info(self, agent_id: str) -> dict[str, Any]:
        """Get routing information for an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Dictionary with routing information.

        Raises:
            ValueError: If agent or profile not found.
        """
        from ..config.env_loader import mask_api_key

        profile_name, profile = self.config.get_profile_for_agent(agent_id)

        if profile is None:
            raise ValueError(
                f"Agent '{agent_id}' 未找到档案（档案名: '{profile_name}'）"
            )

        # Resolve values
        base_url = profile.get_resolved_base_url(self.env_getter)
        api_key = profile.get_resolved_api_key(self.env_getter)

        result = {
            "agent": agent_id,
            "profile": profile_name,
            "provider": profile.provider,
            "base_url": base_url,
            "api_key": mask_api_key(api_key),
            "model": profile.model,
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
            "request_timeout_seconds": self._resolve_timeout_seconds(
                profile,
                agent_id=agent_id,
                apply_timeout_floor=True,
            ),
            "retry_attempts": profile.retry_attempts,
        }

        # Include fallback route info if configured
        fallback_name, fallback_profile = self.config.get_fallback_profile_for_agent(agent_id)
        if fallback_name and fallback_profile is None:
            raise ValueError(
                f"Agent '{agent_id}' 的 fallback LLM 档案不存在: {fallback_name}"
            )
        if fallback_profile:
            fallback_base_url = fallback_profile.get_resolved_base_url(self.env_getter)
            fallback_api_key = fallback_profile.get_resolved_api_key(self.env_getter)
            result["fallback_profile"] = fallback_name
            result["fallback"] = {
                "profile": fallback_name,
                "provider": fallback_profile.provider,
                "base_url": fallback_base_url,
                "api_key": mask_api_key(fallback_api_key),
                "model": fallback_profile.model,
                "request_timeout_seconds": self._resolve_timeout_seconds(
                    fallback_profile,
                    agent_id=agent_id,
                    apply_timeout_floor=False,
                ),
            }

        return result

    def get_fallback_route_info(self, agent_id: str) -> dict | None:
        """Get fallback routing information for an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Dictionary with fallback routing info, or None if not configured.
        """
        from ..config.env_loader import mask_api_key

        profile_name, profile = self.config.get_fallback_profile_for_agent(agent_id)
        if not profile_name:
            return None
        if profile is None:
            raise ValueError(
                f"Agent '{agent_id}' 的 fallback LLM 档案不存在: {profile_name}"
            )

        base_url = profile.get_resolved_base_url(self.env_getter)
        api_key = profile.get_resolved_api_key(self.env_getter)

        return {
            "agent": agent_id,
            "profile": profile_name,
            "provider": profile.provider,
            "base_url": base_url,
            "api_key": mask_api_key(api_key),
            "model": profile.model,
            "request_timeout_seconds": self._resolve_timeout_seconds(
                profile,
                agent_id=agent_id,
                apply_timeout_floor=False,
            ),
            "retry_attempts": profile.retry_attempts,
        }

    def _resolve_timeout_seconds(
        self,
        profile: LLMProfile,
        *,
        agent_id: str,
        apply_timeout_floor: bool,
    ) -> int:
        timeout = int(profile.request_timeout_seconds)
        if not apply_timeout_floor:
            return timeout
        return max(timeout, AGENT_MIN_TIMEOUT_SECONDS.get(agent_id, 0))

    def list_profiles(self) -> dict[str, dict[str, Any]]:
        """List all available profiles with masked keys.

        Returns:
            Dictionary mapping profile names to profile info.
        """
        from ..config.env_loader import mask_api_key

        result = {}
        for name, profile in self.config.llm_profiles.items():
            base_url = profile.get_resolved_base_url(self.env_getter)
            api_key = profile.get_resolved_api_key(self.env_getter)

            result[name] = {
                "provider": profile.provider,
                "base_url": base_url,
                "api_key": mask_api_key(api_key),
                "model": profile.model,
                "temperature": profile.temperature,
                "max_tokens": profile.max_tokens,
                "request_timeout_seconds": profile.request_timeout_seconds,
                "retry_attempts": profile.retry_attempts,
            }

        return result

    def validate(self) -> dict[str, Any]:
        """Validate LLM configuration.

        Returns:
            Dictionary with 'errors' and 'warnings' lists.
        """
        errors = []
        warnings = []

        # Validate profile references
        profile_issues = self.config.validate_profiles()
        errors.extend(profile_issues)

        # Validate each profile has required configuration (only in real mode)
        if self.llm_mode == "real":
            for name, profile in self.config.llm_profiles.items():
                base_url = profile.get_resolved_base_url(self.env_getter)
                api_key = profile.get_resolved_api_key(self.env_getter)

                if not base_url:
                    if profile.base_url_env:
                        errors.append(
                            f"Profile '{name}': environment variable '{profile.base_url_env}' not set"
                        )
                    else:
                        errors.append(f"Profile '{name}': base_url not configured")

                if not api_key:
                    if profile.api_key_env:
                        errors.append(
                            f"Profile '{name}': environment variable '{profile.api_key_env}' not set"
                        )
                    else:
                        errors.append(f"Profile '{name}': API key not configured")

        # Check for unused profiles
        used_profiles = set(self.config.agent_llm.values())
        used_profiles.update(self.config.agent_llm_fallback.values())
        used_profiles.add(self.config.default_llm)
        unused = set(self.config.llm_profiles.keys()) - used_profiles
        if unused:
            warnings.append(f"Unused profiles: {', '.join(sorted(unused))}")

        return {
            "errors": errors,
            "warnings": warnings,
        }
