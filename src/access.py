"""
ClawLite - Access Control
User authentication and authorization
"""

import logging
from typing import Optional

_logger = logging.getLogger("clawlite.access")


def _get_config_list(key: str) -> list[str]:
    """Get a list from config, handling empty/missing gracefully."""
    try:
        from .config import get as config_get
        value = config_get(key, [])
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value]
        return []
    except ImportError:
        return []


def is_user_allowed(user_id: str) -> bool:
    """
    Check if user is allowed to use the bot.
    
    Rules:
    - Admins are always allowed
    - If allowed_users is empty: everyone allowed
    - If allowed_users has items: only those users allowed
    
    Args:
        user_id: Prefixed user ID (e.g., 'tg_123456', 'wa_628xxx')
    
    Returns:
        True if user is allowed
    """
    # Admins are always allowed
    if is_admin(user_id):
        return True
    
    allowed_users = _get_config_list('access.allowed_users')
    
    # Empty list = everyone allowed
    if not allowed_users:
        return True
    
    # Check if user is in allowed list
    return user_id in allowed_users


def is_admin(user_id: str) -> bool:
    """
    Check if user is an admin.
    
    Admins:
    - Always allowed to chat (bypass allowed_users)
    - Can use all tools (bypass tools.allowed)
    
    Args:
        user_id: Prefixed user ID (e.g., 'tg_123456', 'wa_628xxx')
    
    Returns:
        True if user is admin
    """
    admins = _get_config_list('access.admins')
    return user_id in admins


def get_admins() -> list[str]:
    """Get list of admin user IDs."""
    return _get_config_list('access.admins')


def get_allowed_users() -> list[str]:
    """Get list of allowed user IDs (empty = all allowed)."""
    return _get_config_list('access.allowed_users')
