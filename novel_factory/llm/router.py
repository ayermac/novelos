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
        # Stub mode: return stub provider for all agents
        if self.llm_mode == "stub":
            if self.stub_provider is None:
                raise ValueError("Stub provider not configured for stub mode")
            return self.stub_provider
        
        # Real mode: route to appropriate profile
        profile_name, profile = self.config.get_profile_for_agent(agent_id)
        
        if profile is None:
            raise ValueError(
                f"LLM profile '{profile_name}' for agent '{agent_id}' not found. "
                f"Available profiles: {list(self.config.llm_profiles.keys())}"
            )
        
        # Check cache
        if profile_name in self._provider_cache:
            return self._provider_cache[profile_name]
        
        # Create new provider
        provider = self._create_provider(profile_name, profile)
        self._provider_cache[profile_name] = provider
        return provider
    
    def _create_provider(self, profile_name: str, profile: LLMProfile) -> LLMProvider:
        """Create LLM provider from profile.
        
        Args:
            profile_name: Profile name (for error messages).
            profile: LLM profile configuration.
            
        Returns:
            Configured LLM provider.
            
        Raises:
            ValueError: If required configuration is missing.
        """
        # Resolve base_url
        base_url = profile.get_resolved_base_url(self.env_getter)
        if not base_url:
            raise ValueError(
                f"base_url not configured for profile '{profile_name}'. "
                f"Set base_url or {profile.base_url_env} environment variable."
            )
        
        # Resolve API key
        api_key = profile.get_resolved_api_key(self.env_getter)
        if not api_key:
            raise ValueError(
                f"API key not configured for profile '{profile_name}'. "
                f"Set api_key or {profile.api_key_env} environment variable."
            )
        
        # Create provider (currently only OpenAI-compatible)
        if profile.provider != "openai_compatible":
            raise ValueError(
                f"Unsupported provider '{profile.provider}' for profile '{profile_name}'. "
                f"Only 'openai_compatible' is supported."
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
                f"No profile found for agent '{agent_id}' "
                f"(profile_name: '{profile_name}')"
            )
        
        # Resolve values
        base_url = profile.get_resolved_base_url(self.env_getter)
        api_key = profile.get_resolved_api_key(self.env_getter)
        
        return {
            "agent": agent_id,
            "profile": profile_name,
            "provider": profile.provider,
            "base_url": base_url,
            "api_key": mask_api_key(api_key),
            "model": profile.model,
            "temperature": profile.temperature,
            "max_tokens": profile.max_tokens,
        }
    
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
        used_profiles.add(self.config.default_llm)
        unused = set(self.config.llm_profiles.keys()) - used_profiles
        if unused:
            warnings.append(f"Unused profiles: {', '.join(sorted(unused))}")
        
        return {
            "errors": errors,
            "warnings": warnings,
        }
