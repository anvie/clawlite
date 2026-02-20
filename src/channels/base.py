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
            user_id: Target user ID
            text: Message text
            **kwargs: Channel-specific options
            
        Returns:
            True if sent successfully
        """
        pass
    
    def is_allowed(self, user_id: str) -> bool:
        """Check if user is allowed to use the bot."""
        allowed_env = os.getenv(f"{self.name.upper()}_ALLOWED_USERS", "")
        if not allowed_env:
            # Fall back to global ALLOWED_USERS
            allowed_env = os.getenv("ALLOWED_USERS", "")
        
        if not allowed_env:
            return True  # No restriction
        
        allowed = [u.strip() for u in allowed_env.split(",") if u.strip()]
        return str(user_id) in allowed
    
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
            user_id: User ID
            text: Message text
            images: Optional list of base64 encoded images
            status_callback: Optional callback for status updates
            
        Returns:
            Agent response text
        """
        if not self.is_allowed(user_id):
            return "⛔ Not authorized."
        
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
