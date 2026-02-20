"""
ClawLite - Channel Registry
Manages multiple messaging channels (Telegram, WhatsApp, etc.)
"""

import os
import logging
from typing import Dict, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseChannel

logger = logging.getLogger(__name__)

# Channel registry (lazy loaded)
_channels: Dict[str, Type["BaseChannel"]] = {}
_channels_loaded = False


def _load_channels():
    """Lazy load channel implementations."""
    global _channels_loaded
    if _channels_loaded:
        return
    
    # Telegram
    try:
        from .telegram import TelegramChannel
        _channels["telegram"] = TelegramChannel
        logger.debug("Telegram channel loaded")
    except ImportError as e:
        logger.warning(f"Telegram channel not available: {e}")
    
    # WhatsApp (optional - requires neonize)
    try:
        from .whatsapp import WhatsAppChannel
        _channels["whatsapp"] = WhatsAppChannel
        logger.debug("WhatsApp channel loaded")
    except ImportError as e:
        logger.debug(f"WhatsApp channel not available: {e}")
    
    _channels_loaded = True


def register_channel(name: str, channel_class: Type["BaseChannel"]):
    """Register a channel class."""
    _channels[name] = channel_class


def get_enabled_channels() -> list[str]:
    """Get list of enabled channels from environment."""
    enabled = os.getenv("ENABLED_CHANNELS", "telegram")
    return [c.strip().lower() for c in enabled.split(",") if c.strip()]


def create_channel(name: str, agent_callback) -> "BaseChannel":
    """Create a channel instance."""
    _load_channels()
    if name not in _channels:
        raise ValueError(f"Unknown channel: {name}")
    return _channels[name](agent_callback)


def get_available_channels() -> list[str]:
    """Get list of available (registered) channels."""
    _load_channels()
    return list(_channels.keys())
