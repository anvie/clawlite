"""ClawLite Tools - Sandboxed file and shell operations."""

from typing import Optional
from .base import Tool, ToolResult
from .file_ops import ReadFileTool, WriteFileTool, ListDirTool
from .shell import ExecTool, RunBashTool, RunPythonTool, KillProcessTool, ListProcessesTool
from .search import GrepTool, FindFilesTool
from .cron import ListCronTool, AddCronTool, RemoveCronTool
from .memory import MemoryLogTool, MemoryReadTool, MemoryUpdateTool, UserUpdateTool
from .skill_tools import load_skill_tools

# Registry of all available tools (non-user-scoped)
TOOLS = {
    "read_file": ReadFileTool(),
    "write_file": WriteFileTool(),
    "list_dir": ListDirTool(),
    "exec": ExecTool(),
    "run_bash": RunBashTool(),
    "run_python": RunPythonTool(),
    "list_processes": ListProcessesTool(),
    "kill_process": KillProcessTool(),
    "grep": GrepTool(),
    "find_files": FindFilesTool(),
    "list_cron": ListCronTool(),
    "add_cron": AddCronTool(),
    "remove_cron": RemoveCronTool(),
}

# Load and register skill-based tools
import logging
_logger = logging.getLogger("clawlite.tools")

try:
    SKILL_TOOLS = load_skill_tools()
    TOOLS.update(SKILL_TOOLS)
    if SKILL_TOOLS:
        _logger.info(f"Registered {len(SKILL_TOOLS)} skill tool(s): {list(SKILL_TOOLS.keys())}")
except Exception as e:
    _logger.error(f"Failed to load skill tools: {e}")
    SKILL_TOOLS = {}

# User-scoped memory tools (instantiated per-user)
_user_tools_cache: dict[int, dict[str, Tool]] = {}


def get_user_tools(user_id: int) -> dict[str, Tool]:
    """Get user-scoped tools (memory tools with user_id set)."""
    if user_id not in _user_tools_cache:
        # Create new instances with user_id set
        memory_log = MemoryLogTool()
        memory_log.user_id = user_id
        
        memory_read = MemoryReadTool()
        memory_read.user_id = user_id
        
        memory_update = MemoryUpdateTool()
        memory_update.user_id = user_id
        
        user_update = UserUpdateTool()
        user_update.user_id = user_id
        
        _user_tools_cache[user_id] = {
            "memory_log": memory_log,
            "memory_read": memory_read,
            "memory_update": memory_update,
            "user_update": user_update,
        }
    
    return _user_tools_cache[user_id]


def get_all_tools(user_id: Optional[int] = None) -> dict[str, Tool]:
    """Get all tools (shared + user-scoped if user_id provided)."""
    all_tools = dict(TOOLS)
    if user_id:
        all_tools.update(get_user_tools(user_id))
    return all_tools


def get_tool(name: str, user_id: Optional[int] = None) -> Optional[Tool]:
    """Get a tool by name, with user-scoped tools if user_id provided."""
    all_tools = get_all_tools(user_id)
    return all_tools.get(name)


def list_tools(user_id: Optional[int] = None) -> list[dict]:
    """List all available tools with their descriptions."""
    all_tools = get_all_tools(user_id)
    return [
        {
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for name, tool in all_tools.items()
    ]


def format_tools_for_prompt(user_id: Optional[int] = None) -> str:
    """Format tools documentation for system prompt."""
    all_tools = get_all_tools(user_id)
    lines = ["Available tools:"]
    for name, tool in all_tools.items():
        lines.append(f"\n### {name}")
        lines.append(f"{tool.description}")
        lines.append(f"Parameters: {tool.parameters}")
    return "\n".join(lines)
