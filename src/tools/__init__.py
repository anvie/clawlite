"""ClawLite Tools - Sandboxed file and shell operations."""

import logging
from typing import Optional

from .base import Tool, ToolResult
from .file_ops import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool, SendFileTool
from .shell import ExecTool, RunBashTool
from .search import GrepTool, FindFilesTool
from .cron import ListCronTool, AddCronTool, RemoveCronTool
from .reminder import (
    AddReminderTool, 
    ListRemindersTool, 
    EditReminderTool, 
    DeleteReminderTool
)
from .memory import MemoryLogTool, MemoryReadTool, MemoryUpdateTool, UserUpdateTool
from .web import WebSearchTool, WebFetchTool
from .skill_tools import load_skill_tools

_logger = logging.getLogger("clawlite.tools")


def _filter_tools_by_config(tools: dict, user_id: Optional[str] = None) -> dict:
    """Filter tools based on config/clawlite.yaml settings.
    
    If tools.allowed is empty or missing: all tools enabled
    If tools.allowed has items: only those tools enabled
    Admin users bypass this filter and get all tools.
    
    Args:
        tools: Dict of all available tools
        user_id: Optional prefixed user ID for admin check
    
    Returns:
        Filtered dict of tools
    """
    # Check if user is admin - admins get all tools
    if user_id:
        try:
            from ..access import is_admin
            if is_admin(user_id):
                _logger.debug(f"Admin user {user_id}: all tools enabled")
                return tools
        except ImportError:
            pass
    
    try:
        from ..config import get as config_get
    except ImportError:
        return tools
    
    allowed = config_get('tools.allowed', [])
    
    if allowed:
        filtered = {k: v for k, v in tools.items() if k in allowed}
        disabled_count = len(tools) - len(filtered)
        _logger.info(f"Tools: {len(filtered)} enabled, {disabled_count} disabled (allowlist mode)")
        return filtered
    
    # Empty or missing = all tools enabled
    return tools


# Registry of all available tools (non-user-scoped)
_ALL_TOOLS = {
    "read_file": ReadFileTool(),
    "write_file": WriteFileTool(),
    "edit_file": EditFileTool(),
    "list_dir": ListDirTool(),
    "exec": ExecTool(),
    "run_bash": RunBashTool(),
    "grep": GrepTool(),
    "find_files": FindFilesTool(),
    "send_file": SendFileTool(),
    "list_cron": ListCronTool(),
    "add_cron": AddCronTool(),
    "remove_cron": RemoveCronTool(),
    # Reminder tools (file-based, supports one-time + recurring)
    "add_reminder": AddReminderTool(),
    "list_reminders": ListRemindersTool(),
    "edit_reminder": EditReminderTool(),
    "delete_reminder": DeleteReminderTool(),
    "web_search": WebSearchTool(),
    "web_fetch": WebFetchTool(),
}

# Load and register skill-based tools
try:
    SKILL_TOOLS = load_skill_tools()
    _ALL_TOOLS.update(SKILL_TOOLS)
    if SKILL_TOOLS:
        _logger.info(f"Registered {len(SKILL_TOOLS)} skill tool(s): {list(SKILL_TOOLS.keys())}")
except Exception as e:
    _logger.error(f"Failed to load skill tools: {e}")
    SKILL_TOOLS = {}

# Apply config-based filtering (default, without user context)
TOOLS = _filter_tools_by_config(_ALL_TOOLS)

# User-scoped memory tools (instantiated per-user)
_user_tools_cache: dict[str, dict[str, Tool]] = {}


def get_user_tools(user_id: str) -> dict[str, Tool]:
    """Get user-scoped tools (memory tools with user_id set)."""
    if user_id not in _user_tools_cache:
        # Create new instances with user_id set
        memory_log = MemoryLogTool()
        memory_log.user_id = user_id
        
        memory_read = MemoryReadTool()
        memory_read.user_id = user_id
        
        memory_update = MemoryUpdateTool()
        memory_update.user_id = user_id
        
        # user_update = UserUpdateTool()
        # user_update.user_id = user_id
        
        _user_tools_cache[user_id] = {
            "memory_log": memory_log,
            "memory_read": memory_read,
            "memory_update": memory_update,
            # "user_update": user_update,
        }
    
    return _user_tools_cache[user_id]


def get_all_tools(user_id: Optional[str] = None) -> dict[str, Tool]:
    """Get all tools (shared + user-scoped if user_id provided).
    
    Admin users get all tools regardless of config filtering.
    
    Args:
        user_id: Prefixed user ID (e.g., "tg_123456")
    
    Returns:
        Dict of available tools
    """
    # Re-filter with user context (for admin bypass)
    filtered_tools = _filter_tools_by_config(_ALL_TOOLS, user_id)
    all_tools = dict(filtered_tools)
    
    if user_id:
        all_tools.update(get_user_tools(user_id))
    return all_tools


def get_tool(name: str, user_id: Optional[str] = None) -> Optional[Tool]:
    """Get a tool by name, with user-scoped tools if user_id provided.
    
    Sets user_id on the tool for access control (e.g., file path validation).
    """
    all_tools = get_all_tools(user_id)
    tool = all_tools.get(name)
    if tool and user_id:
        tool.user_id = user_id  # Set for path validation access control
    return tool


def list_tools(user_id: Optional[str] = None) -> list[dict]:
    """List all available tools with their descriptions.
    
    Args:
        user_id: Prefixed user ID (e.g., "tg_123456")
    """
    all_tools = get_all_tools(user_id)
    return [
        {
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for name, tool in all_tools.items()
    ]


def format_tools_for_prompt(user_id: Optional[str] = None) -> str:
    """Format tools documentation for system prompt.
    
    Args:
        user_id: Prefixed user ID (e.g., "tg_123456")
    """
    all_tools = get_all_tools(user_id)
    lines = ["Available tools:"]
    for name, tool in all_tools.items():
        lines.append(f"\n### {name}")
        lines.append(f"{tool.description}")
        lines.append(f"Parameters: {tool.parameters}")
    return "\n".join(lines)
