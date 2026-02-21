"""Unified configuration system for ClawLite."""

import os
import logging
from typing import Any

logger = logging.getLogger("clawlite.config")

_config: dict = None


def load_config() -> dict:
    """Load config from config/clawlite.yaml"""
    global _config
    if _config is not None:
        return _config
    
    config_path = os.environ.get("CLAWLITE_CONFIG", "config/clawlite.yaml")
    
    # Try relative to src/ first, then absolute
    if not os.path.isabs(config_path):
        src_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(src_dir, "..", config_path),
            config_path,
        ]
    else:
        candidates = [config_path]
    
    for path in candidates:
        real_path = os.path.realpath(path)
        if os.path.exists(real_path):
            try:
                import yaml
                with open(real_path) as f:
                    _config = yaml.safe_load(f) or {}
                logger.info(f"Loaded config from {real_path}")
                return _config
            except ImportError:
                logger.warning("PyYAML not installed, using empty config")
                _config = {}
                return _config
            except Exception as e:
                logger.error(f"Failed to load config from {real_path}: {e}")
                _config = {}
                return _config
    
    logger.debug(f"No config file found, using defaults")
    _config = {}
    return _config


def reload_config() -> dict:
    """Force reload config from file."""
    global _config
    _config = None
    return load_config()


def get(key: str, default: Any = None) -> Any:
    """
    Get config value by dot notation.
    
    Examples:
        get('tools.mode', 'blocklist')
        get('agent.tool_timeout', 30)
        get('llm.model')
    """
    config = load_config()
    keys = key.split('.')
    value = config
    
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
        if value is None:
            return default
    
    return value


def get_section(section: str) -> dict:
    """Get entire config section as dict."""
    return get(section, {})
