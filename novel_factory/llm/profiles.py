"""LLM profile models for v3.1 agent routing.

Defines the structure of LLM profiles that can be assigned to different agents.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LLMProfile(BaseModel):
    """LLM profile configuration for a specific agent or use case.
    
    Supports both direct configuration and environment variable references:
    - base_url: Direct URL or None if using base_url_env
    - base_url_env: Environment variable name for base_url
    - api_key: Direct API key (not recommended) or None if using api_key_env
    - api_key_env: Environment variable name for API key
    """
    
    provider: str = "openai_compatible"
    
    # Base URL: can be direct or from env var
    base_url: Optional[str] = None
    base_url_env: Optional[str] = None
    
    # API key: can be direct (not recommended) or from env var
    api_key: Optional[str] = Field(default=None, repr=False)
    api_key_env: Optional[str] = None
    
    # Model configuration
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    
    def get_resolved_base_url(self, env_getter) -> Optional[str]:
        """Resolve base_url from direct value or environment variable.
        
        Args:
            env_getter: Function to get environment variable (e.g., os.getenv).
            
        Returns:
            Resolved base_url or None.
        """
        # Direct value takes precedence
        if self.base_url:
            return self.base_url
        # Then try environment variable
        if self.base_url_env:
            return env_getter(self.base_url_env)
        return None
    
    def get_resolved_api_key(self, env_getter) -> Optional[str]:
        """Resolve api_key from direct value or environment variable.
        
        Args:
            env_getter: Function to get environment variable (e.g., os.getenv).
            
        Returns:
            Resolved api_key or None.
        """
        # Direct value takes precedence (not recommended but supported)
        if self.api_key:
            return self.api_key
        # Then try environment variable
        if self.api_key_env:
            return env_getter(self.api_key_env)
        return None
    
    def to_display_dict(self, mask_key: bool = True) -> dict:
        """Convert to dictionary for display, optionally masking API key.
        
        Args:
            mask_key: If True, mask the API key in output.
            
        Returns:
            Dictionary with profile information.
        """
        from ..config.env_loader import mask_api_key
        
        result = {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        
        # Show resolved values
        if self.base_url_env:
            result["base_url_env"] = self.base_url_env
        if self.api_key_env:
            result["api_key_env"] = self.api_key_env
        
        # Show API key (masked or not)
        if mask_key:
            result["api_key"] = "***"
        else:
            # This should rarely be used
            result["api_key"] = self.api_key or "***"
        
        return result


class LLMProfilesConfig(BaseModel):
    """Configuration for all LLM profiles."""
    
    default_llm: str = "default"
    llm_profiles: dict[str, LLMProfile] = Field(default_factory=dict)
    agent_llm: dict[str, str] = Field(default_factory=dict)
    
    def get_profile_for_agent(self, agent_id: str) -> tuple[str, Optional[LLMProfile]]:
        """Get the profile name and profile for an agent.
        
        Args:
            agent_id: Agent identifier (e.g., "author", "editor").
            
        Returns:
            Tuple of (profile_name, profile or None if not found).
        """
        # Check if agent has specific profile
        profile_name = self.agent_llm.get(agent_id)
        
        # Fall back to default_llm
        if not profile_name:
            profile_name = self.default_llm
        
        # Get the profile
        profile = self.llm_profiles.get(profile_name)
        
        return profile_name, profile
    
    def validate_profiles(self) -> list[str]:
        """Validate profile configuration.
        
        Returns:
            List of validation issues (empty if valid).
        """
        issues = []
        
        # Check that default_llm exists
        if self.default_llm not in self.llm_profiles:
            issues.append(f"default_llm '{self.default_llm}' not found in llm_profiles")
        
        # Check that all agent_llm references exist
        for agent_id, profile_name in self.agent_llm.items():
            if profile_name not in self.llm_profiles:
                issues.append(f"agent_llm[{agent_id}] references non-existent profile '{profile_name}'")
        
        return issues
