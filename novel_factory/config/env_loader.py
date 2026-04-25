"""Environment variable loader with priority.

Priority (highest to lowest):
1. OS environment variables
2. Project root .env file
3. YAML configuration defaults

This module provides a minimal .env loader without external dependencies.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_dotenv_disabled() -> bool:
    """Check if .env loading is disabled via environment variable.
    
    When NOVEL_FACTORY_DISABLE_DOTENV is set to 1, true, yes, or on,
    load_dotenv() will return an empty dict without reading any .env file.
    This is primarily used in test environments to prevent project root
    .env files from polluting test scenarios.
    """
    return os.getenv("NOVEL_FACTORY_DISABLE_DOTENV") in ("1", "true", "yes", "on")


def find_project_root() -> Path:
    """Find project root directory.
    
    Looks for .git, pyproject.toml, or setup.py markers.
    Falls back to current working directory.
    """
    # Try to find project root by looking for markers
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / "setup.py").exists():
            return parent
    return current


def load_dotenv(dotenv_path: Optional[Path] = None, override: bool = False) -> dict[str, str]:
    """Load environment variables from .env file.
    
    v3.1: Returns a dict instead of polluting os.environ.
    v3.7: Respects NOVEL_FACTORY_DISABLE_DOTENV to skip .env loading.
    
    Args:
        dotenv_path: Path to .env file. If None, looks for .env in project root.
        override: DEPRECATED - kept for API compatibility but ignored.
        
    Returns:
        Dict of environment variables loaded from .env file.
        Does NOT modify os.environ.
    """
    if is_dotenv_disabled():
        logger.debug("NOVEL_FACTORY_DISABLE_DOTENV is set, skipping .env loading")
        return {}
    
    if dotenv_path is None:
        dotenv_path = find_project_root() / ".env"
    
    result: dict[str, str] = {}
    
    if not dotenv_path.exists():
        logger.debug(f".env file not found at {dotenv_path}")
        return result
    
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                
                # Parse KEY=VALUE
                if "=" not in line:
                    logger.warning(f"Invalid .env line {line_num}: {line}")
                    continue
                
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                result[key] = value
                logger.debug(f"Loaded {key} from .env")
        
        logger.info(f"Loaded {len(result)} variables from .env at {dotenv_path}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to load .env file: {e}")
        return result


def get_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with fallback.
    
    Args:
        name: Environment variable name.
        default: Default value if not found.
        
    Returns:
        Environment variable value or default.
    """
    return os.getenv(name, default)


def create_env_getter(dotenv_vars: Optional[dict[str, str]] = None):
    """Create an env getter with priority: OS env > .env dict > default.
    
    Args:
        dotenv_vars: Dict of variables loaded from .env file.
        
    Returns:
        Function that implements the priority chain.
    """
    dotenv_vars = dotenv_vars or {}
    
    def env_getter(name: str, default: Optional[str] = None) -> Optional[str]:
        # Priority 1: OS environment (highest)
        if name in os.environ:
            return os.environ[name]
        # Priority 2: .env file
        if name in dotenv_vars:
            return dotenv_vars[name]
        # Priority 3: default
        return default
    
    return env_getter


def mask_api_key(key: Optional[str]) -> str:
    """Mask API key for safe display.
    
    Args:
        key: API key to mask.
        
    Returns:
        Always returns "***" to avoid leaking any key information.
    """
    return "***"
