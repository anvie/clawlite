"""User-scoped memory tools."""

import os
from datetime import date
from pathlib import Path
from typing import Optional

from . import Tool, ToolResult

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/workspace")


def get_user_dir(user_id: int) -> Path:
    """Get the user's directory path."""
    return Path(WORKSPACE_DIR) / "users" / str(user_id)


class MemoryLogTool(Tool):
    """Append to today's daily memory log."""
    
    name = "memory_log"
    description = "Append a note to today's memory log. Use this to remember important things from the conversation."
    parameters = {
        "content": {
            "type": "string",
            "description": "Content to append to today's memory log",
            "required": True
        }
    }
    
    # Will be set per-request
    user_id: Optional[int] = None
    
    async def execute(self, content: str) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        try:
            user_dir = get_user_dir(self.user_id)
            memory_dir = user_dir / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)
            
            today = date.today().isoformat()
            path = memory_dir / f"{today}.md"
            
            # Read existing
            existing = ""
            if path.exists():
                existing = path.read_text()
            
            # Append with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M")
            
            if existing and not existing.endswith("\n"):
                existing += "\n"
            
            new_content = existing + f"\n### {timestamp}\n\n{content}\n"
            path.write_text(new_content)
            
            return ToolResult(success=True, output=f"Logged to memory/{today}.md")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MemoryReadTool(Tool):
    """Read from memory files."""
    
    name = "memory_read"
    description = "Read memory files. Without date parameter, reads MEMORY.md (long-term). With date (YYYY-MM-DD), reads that day's log."
    parameters = {
        "date": {
            "type": "string",
            "description": "Date in YYYY-MM-DD format (optional, omit for long-term memory)",
            "required": False
        }
    }
    
    user_id: Optional[int] = None
    
    async def execute(self, date: Optional[str] = None) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        try:
            user_dir = get_user_dir(self.user_id)
            
            if date:
                # Read specific day's log
                path = user_dir / "memory" / f"{date}.md"
            else:
                # Read long-term memory
                path = user_dir / "MEMORY.md"
            
            if not path.exists():
                return ToolResult(success=False, error=f"File not found: {path.name}")
            
            content = path.read_text()
            return ToolResult(success=True, output=content[:4000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MemoryUpdateTool(Tool):
    """Update long-term memory."""
    
    name = "memory_update"
    description = "Update or append to MEMORY.md (long-term memory). Use for important things to remember across sessions."
    parameters = {
        "content": {
            "type": "string",
            "description": "Content to append to MEMORY.md",
            "required": True
        }
    }
    
    user_id: Optional[int] = None
    
    async def execute(self, content: str) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        try:
            user_dir = get_user_dir(self.user_id)
            user_dir.mkdir(parents=True, exist_ok=True)
            
            path = user_dir / "MEMORY.md"
            
            existing = ""
            if path.exists():
                existing = path.read_text()
            
            if existing and not existing.endswith("\n\n"):
                existing = existing.rstrip() + "\n\n"
            
            path.write_text(existing + content + "\n")
            
            return ToolResult(success=True, output="Updated MEMORY.md")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class UserUpdateTool(Tool):
    """Update user info."""
    
    name = "user_update"
    description = "Update USER.md with information about the user (name, preferences, etc.)"
    parameters = {
        "content": {
            "type": "string",
            "description": "Content to write to USER.md (replaces existing)",
            "required": True
        }
    }
    
    user_id: Optional[int] = None
    
    async def execute(self, content: str) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        try:
            user_dir = get_user_dir(self.user_id)
            user_dir.mkdir(parents=True, exist_ok=True)
            
            path = user_dir / "USER.md"
            path.write_text(content)
            
            return ToolResult(success=True, output="Updated USER.md")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# Export tools
MEMORY_TOOLS = [
    MemoryLogTool(),
    MemoryReadTool(),
    MemoryUpdateTool(),
    UserUpdateTool(),
]
