"""
ClawLite - Access Control
User authentication and authorization
"""

import os
import logging
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("clawlite.access")

# Owner file location (outside workspace, not accessible to tools)
OWNER_FILE = Path(os.getenv("OWNER_FILE", "/app/.owner"))


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
    - Instance owner (first user)
    - Users listed in config access.admins
    
    Admin privileges:
    - Always allowed to chat (bypass allowed_users)
    - Can use all tools (bypass tools.allowed)
    
    Args:
        user_id: Prefixed user ID (e.g., 'tg_123456', 'wa_628xxx')
    
    Returns:
        True if user is admin
    """
    # Owner is always admin
    if is_owner(user_id):
        return True
    
    # Check config-based admins
    admins = _get_config_list('access.admins')
    return user_id in admins


def get_admins() -> list[str]:
    """Get list of admin user IDs."""
    return _get_config_list('access.admins')


def get_allowed_users() -> list[str]:
    """Get list of allowed user IDs (empty = all allowed)."""
    return _get_config_list('access.allowed_users')


# --- Owner (First-User-As-Admin) ---

def get_owner() -> Optional[str]:
    """
    Get the instance owner (first user who chatted).
    
    Returns:
        Owner user ID or None if not set
    """
    try:
        if OWNER_FILE.exists():
            content = OWNER_FILE.read_text().strip()
            if content:
                return content
    except Exception as e:
        _logger.error(f"Error reading owner file: {e}")
    return None


def set_owner(user_id: str) -> bool:
    """
    Set the instance owner (only works if no owner set yet).
    
    Args:
        user_id: Prefixed user ID to set as owner
    
    Returns:
        True if owner was set, False if already has owner
    """
    try:
        # Check if already has owner
        if get_owner() is not None:
            return False
        
        # Set owner
        OWNER_FILE.write_text(user_id)
        _logger.info(f"Instance owner set: {user_id}")
        return True
    except Exception as e:
        _logger.error(f"Error setting owner: {e}")
        return False


def is_owner(user_id: str) -> bool:
    """
    Check if user is the instance owner.
    
    Args:
        user_id: Prefixed user ID
    
    Returns:
        True if user is the owner
    """
    return get_owner() == user_id


def claim_ownership(user_id: str) -> bool:
    """
    Attempt to claim ownership (first user becomes owner).
    
    Call this on every message. Only the first user will successfully claim.
    
    Args:
        user_id: Prefixed user ID attempting to claim
    
    Returns:
        True if this user just became owner, False otherwise
    """
    if get_owner() is None:
        return set_owner(user_id)
    return False
