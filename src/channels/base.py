"""
ClawLite - Base Channel
Abstract base class for messaging channels
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Workspace path
WORKSPACE = os.getenv("WORKSPACE_PATH", "/workspace")


@dataclass
class Message:
    """Unified message representation across channels."""
    user_id: str
    text: str
    images: Optional[list[str]] = None  # Base64 encoded images
    file_path: Optional[str] = None  # Path to uploaded file
    file_context: Optional[str] = None  # Context about the file
    reply_to: Optional[str] = None  # Message ID being replied to


@dataclass
class User:
    """Unified user representation."""
    id: str
    username: Optional[str] = None
    display_name: Optional[str] = None


# Type alias for agent callback
AgentCallback = Callable[[str, str, Optional[list[str]], Callable], Awaitable[str]]
# Args: user_id, message, images, status_callback
# Returns: response text


class BaseChannel(ABC):
    """Abstract base class for messaging channels."""
    
    name: str = "base"
    prefix: str = ""  # Channel prefix for user IDs (e.g., "tg", "wa")
    
    def __init__(self, agent_callback: AgentCallback):
        """
        Initialize channel with agent callback.
        
        Args:
            agent_callback: Async function to process messages through the agent.
                           Signature: (user_id, message, images, status_callback) -> response
        """
        self.agent_callback = agent_callback
        self.logger = logging.getLogger(f"clawlite.{self.name}")
    
    @abstractmethod
    async def start(self) -> None:
        """Start the channel (connect, authenticate, etc.)."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel gracefully."""
        pass
    
    @abstractmethod
    async def send_message(self, user_id: str, text: str, **kwargs) -> bool:
        """
        Send a message to a user.
        
        Args:
            user_id: Target user ID (can be raw or prefixed)
            text: Message text
            **kwargs: Channel-specific options
            
        Returns:
            True if sent successfully
        """
        pass
    
    def format_user_id(self, raw_id: str | int) -> str:
        """
        Format raw user ID with channel prefix.
        
        Args:
            raw_id: Raw user ID from the channel (e.g., 123456, "628xxx")
        
        Returns:
            Prefixed user ID (e.g., "tg_123456", "wa_628xxx")
        """
        raw_str = str(raw_id)
        if self.prefix:
            return f"{self.prefix}_{raw_str}"
        return raw_str
    
    def strip_prefix(self, user_id: str) -> str:
        """
        Strip channel prefix from user ID.
        
        Args:
            user_id: Prefixed user ID (e.g., "tg_123456")
        
        Returns:
            Raw user ID (e.g., "123456")
        """
        if self.prefix and user_id.startswith(f"{self.prefix}_"):
            return user_id[len(self.prefix) + 1:]
        return user_id
    
    def is_allowed(self, user_id: str) -> bool:
        """
        Check if user is allowed to use the bot.
        Uses the centralized access control module.
        
        Args:
            user_id: Prefixed user ID (e.g., "tg_123456")
        
        Returns:
            True if user is allowed
        """
        try:
            from ..access import is_user_allowed
            return is_user_allowed(user_id)
        except ImportError:
            # Fallback to old behavior if access module not available
            return True
    
    async def process_message(
        self,
        user_id: str,
        text: str,
        images: Optional[list[str]] = None,
        status_callback: Optional[Callable] = None
    ) -> str:
        """
        Process a message through the agent.
        
        Args:
            user_id: Prefixed user ID
            text: Message text
            images: Optional list of base64 encoded images
            status_callback: Optional callback for status updates
            
        Returns:
            Agent response text
        """
        # First-user-as-admin: attempt to claim ownership
        try:
            from ..access import claim_ownership
            if claim_ownership(user_id):
                self.logger.info(f"First user {user_id} claimed ownership (admin)")
        except Exception as e:
            self.logger.warning(f"Failed to check ownership: {e}")
        
        if not self.is_allowed(user_id):
            return "⛔ Not authorized."
        
        # Handle /clear command
        if text.strip() == "/clear":
            return await self._handle_clear(user_id)
        
        # Default status callback that does nothing
        if status_callback is None:
            status_callback = lambda x: None
        
        try:
            response = await self.agent_callback(
                user_id,
                text,
                images,
                status_callback
            )
            return response
        except Exception as e:
            self.logger.error(f"Error processing message from {user_id}: {e}")
            return f"❌ Error: {str(e)[:500]}"
    
    async def _handle_clear(self, user_id: str) -> str:
        """
        Handle /clear command to clear conversation history.
        
        Args:
            user_id: Prefixed user ID
        
        Returns:
            Confirmation message
        """
        try:
            from ..conversation import clear_today, is_enabled
            
            if not is_enabled():
                return "ℹ️ Conversation recording is not enabled."
            
            clear_today(user_id)
            self.logger.info(f"Cleared conversation for {user_id} via /clear command")
            return "🗑️ Conversation cleared."
            
        except Exception as e:
            self.logger.error(f"Failed to clear conversation for {user_id}: {e}")
            return f"❌ Failed to clear: {str(e)[:200]}"
