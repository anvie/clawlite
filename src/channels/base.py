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
        if not self.is_allowed(user_id):
            return "⛔ Not authorized."
        
        # Handle /new command (new session, keep memory)
        if text.strip() == "/new":
            return await self._handle_new(user_id)
        
        # Handle /clear command
        if text.strip() == "/clear":
            return await self._handle_clear(user_id)
        
        # Handle /status command
        if text.strip() == "/status":
            return await self._handle_status(user_id)
        
        # Handle /dump command (owner/admin only)
        if text.strip() == "/dump":
            return await self._handle_dump(user_id)
        
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
        Handle /clear command to clear conversation history only.
        
        Deletes:
        - Conversation history (all JSONL files)
        
        Preserves:
        - USER.md (user info)
        - MEMORY.md (long-term memory)
        - Daily memory logs (memory/*.md)
        
        Args:
            user_id: Prefixed user ID
        
        Returns:
            Confirmation message
        """
        try:
            from ..conversation import is_enabled, get_convo_dir
            
            deleted_count = 0
            
            # Clear conversation history only
            if is_enabled():
                convo_dir = get_convo_dir(user_id)
                if convo_dir.exists():
                    for f in convo_dir.glob("*.jsonl"):
                        f.unlink()
                        deleted_count += 1
            
            self.logger.info(f"Cleared conversation for {user_id}: {deleted_count} files")
            
            if deleted_count > 0:
                return f"🗑️ Cleared {deleted_count} conversation file(s). Memory preserved."
            else:
                return "ℹ️ No conversation to clear."
            
        except Exception as e:
            self.logger.error(f"Failed to clear conversation for {user_id}: {e}")
            return f"❌ Failed to clear: {str(e)[:200]}"
    
    async def _handle_new(self, user_id: str) -> str:
        """
        Handle /new command to start a new session without deleting memory.
        
        This inserts a session break marker in the conversation file.
        The agent starts fresh but USER.md, MEMORY.md, and daily logs are preserved.
        
        Args:
            user_id: Prefixed user ID
        
        Returns:
            Confirmation message
        """
        try:
            from ..conversation import insert_session_break, is_enabled
            
            if is_enabled():
                insert_session_break(user_id)
            
            self.logger.info(f"New session started for {user_id}")
            return "🆕 Session baru dimulai.\nMemory & preferences tetap ada."
            
        except Exception as e:
            self.logger.error(f"Failed to start new session for {user_id}: {e}")
            return f"❌ Failed: {str(e)[:200]}"
    
    async def _handle_status(self, user_id: str) -> str:
        """
        Handle /status command to show model and usage info.
        
        Args:
            user_id: Prefixed user ID
        
        Returns:
            Status message
        """
        try:
            from ..config import get as config_get
            from ..agent import get_history_limit
            
            # Get config values
            provider = config_get("llm.provider", "unknown")
            model = config_get("llm.model", "unknown")
            base_url = config_get("llm.base_url", "")
            history_limit = get_history_limit()
            
            # Note: base channel doesn't have conversations dict
            # Subclasses should override this for accurate counts
            
            status = (
                f"📊 ClawLite Status\n\n"
                f"Model: {model}\n"
                f"Provider: {provider}\n"
            )
            if base_url:
                status += f"Base URL: {base_url}\n"
            status += f"History limit: {history_limit} messages\n"
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get status: {e}")
            return f"❌ Failed: {str(e)[:200]}"
    
    async def _handle_dump(self, user_id: str) -> str:
        """
        Handle /dump command to dump full agent context to file.
        Only available to owner/admin.
        
        Args:
            user_id: Prefixed user ID
        
        Returns:
            Confirmation message
        """
        try:
            from ..access import is_admin
            
            # Only owner/admin can dump context
            if not is_admin(user_id):
                return "⛔ Only owner/admin can use /dump"
            
            import os
            from datetime import datetime
            import pytz
            from ..context import load_full_context
            from ..tools import format_tools_for_prompt
            from ..access import is_owner
            
            # Build the same context that agent sees
            workspace = os.environ.get("WORKSPACE_DIR", "/workspace")
            tz = pytz.timezone(os.environ.get("TZ", "UTC"))
            now = datetime.now(tz)
            
            # Load context components
            user_context = load_full_context(user_id)
            tools_prompt = format_tools_for_prompt(user_id)
            
            # Build runtime context
            user_is_owner = is_owner(user_id)
            user_is_admin_flag = is_admin(user_id)
            
            if user_is_owner:
                role_info = "⚠️ THIS USER IS THE OWNER - Full admin privileges"
            elif user_is_admin_flag:
                role_info = "⚠️ THIS USER IS AN ADMIN - Full privileges"
            else:
                role_info = "Regular user (limited access)"
            
            # Compose full dump
            dump_content = f"""# ClawLite Context Dump
Generated: {now.strftime("%Y-%m-%d %H:%M:%S %Z")}
User ID: {user_id}
Role: {role_info}

================================================================================
## TOOLS AVAILABLE
================================================================================

{tools_prompt}

================================================================================
## USER CONTEXT (from workspace files)
================================================================================

{user_context if user_context else "(No context loaded)"}

================================================================================
# END OF DUMP
================================================================================
"""
            
            # Write to file
            dump_path = os.path.join(workspace, "context.dump.txt")
            with open(dump_path, "w") as f:
                f.write(dump_content)
            
            self.logger.info(f"Context dumped for {user_id} to {dump_path}")
            return f"📄 Context dumped to `context.dump.txt` ({len(dump_content)} chars)"
            
        except Exception as e:
            self.logger.error(f"Failed to dump context for {user_id}: {e}")
            return f"❌ Failed to dump: {str(e)[:200]}"
    
    async def send_debug_alert(self, chat_id: str, tool_info: dict) -> None:
        """
        Send a debug alert for failed tool calls.
        Override in channel subclass to implement (e.g., Telegram).
        Default: no-op.
        
        Args:
            chat_id: Raw chat/user ID for this channel
            tool_info: Dict with tool, args, result, success, exit_code, duration_ms
        """
        pass
