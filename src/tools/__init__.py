"""ClawLite Tools - Sandboxed file and shell operations."""

from .base import Tool, ToolResult
from .file_ops import ReadFileTool, WriteFileTool, ListDirTool
from .shell import ExecTool, RunBashTool, RunPythonTool, KillProcessTool, ListProcessesTool
from .search import SearchFilesTool, GrepTool
from .cron import ListCronTool, AddCronTool, RemoveCronTool

# Registry of all available tools
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
    "search_files": SearchFilesTool(),
    "list_cron": ListCronTool(),
    "add_cron": AddCronTool(),
    "remove_cron": RemoveCronTool(),
}


def get_tool(name: str) -> Tool:
    """Get a tool by name."""
    return TOOLS.get(name)


def list_tools() -> list[dict]:
    """List all available tools with their descriptions."""
    return [
        {
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for name, tool in TOOLS.items()
    ]


def format_tools_for_prompt() -> str:
    """Format tools documentation for system prompt."""
    lines = ["Available tools:"]
    for name, tool in TOOLS.items():
        lines.append(f"\n### {name}")
        lines.append(f"{tool.description}")
        lines.append(f"Parameters: {tool.parameters}")
    return "\n".join(lines)
