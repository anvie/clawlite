"""User-scoped memory tools."""

import os
import re
from datetime import date
from pathlib import Path
from typing import Optional, List, Tuple

from . import Tool, ToolResult

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/workspace")


def get_user_dir(user_id: str) -> Path:
    """Get the user's directory path.
    
    Args:
        user_id: Prefixed user ID (e.g., "tg_123456", "wa_628xxx")
    """
    return Path(WORKSPACE_DIR) / "users" / str(user_id)


class MemoryLogTool(Tool):
    """Append to today's daily memory log."""
    
    name = "memory_log"
    description = """Append a note to today's memory log (users/{user_id}/memory/YYYY-MM-DD.md).
Use this to remember important things from the conversation."""
    parameters = {
        "content": {
            "type": "string",
            "description": "Content to append to today's memory log",
            "required": True
        }
    }
    
    # Will be set per-request
    user_id: Optional[str] = None
    
    async def execute(self, content: str) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        # Validate content is not empty or placeholder
        content = content.strip() if content else ""
        if not content or content in ("...", ".", "-", "N/A", "none", "null"):
            return ToolResult(
                success=False, 
                error="Content cannot be empty or placeholder. Please provide actual information to log."
            )
        
        # Reject very short content that's likely a mistake
        if len(content) < 10:
            return ToolResult(
                success=False,
                error=f"Content too short ({len(content)} chars). Please provide meaningful information."
            )
        
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
    
    user_id: Optional[str] = None
    
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
    
    user_id: Optional[str] = None
    
    async def execute(self, content: str) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        # Validate content
        content = content.strip() if content else ""
        if not content or content in ("...", ".", "-", "N/A", "none", "null"):
            return ToolResult(
                success=False,
                error="Content cannot be empty or placeholder. Please provide actual information."
            )
        
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
    description = "Update USER.md with user information (name, phone, email, preferences)"
    parameters = {
        "name": {
            "type": "string",
            "description": "User's name",
            "required": False
        },
        "phone": {
            "type": "string",
            "description": "User's phone number",
            "required": False
        },
        "email": {
            "type": "string",
            "description": "User's email address",
            "required": False
        },
        "notes": {
            "type": "string",
            "description": "Additional notes or preferences",
            "required": False
        }
    }
    
    user_id: Optional[str] = None
    
    async def execute(self, name: str = None, phone: str = None, email: str = None, notes: str = None) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        # Build content from structured data
        content_parts = ["# User Info\n"]
        
        if name:
            content_parts.append(f"Name: {name}")
        if phone:
            content_parts.append(f"Phone: {phone}")
        if email:
            content_parts.append(f"Email: {email}")
        if notes:
            content_parts.append(f"\n## Notes\n{notes}")
        
        content = "\n".join(content_parts)
        
        try:
            user_dir = get_user_dir(self.user_id)
            user_dir.mkdir(parents=True, exist_ok=True)
            
            path = user_dir / "USER.md"
            path.write_text(content)
            
            return ToolResult(success=True, output="Updated USER.md")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MemorySearchTool(Tool):
    """Search across all user memory files."""
    
    name = "memory_search"
    description = """Search for information across ALL user memory files:
- USER.md (user profile & preferences)
- MEMORY.md (long-term memory)
- memory/*.md (all daily logs)

Use this when looking for past information, events, or data that might be stored anywhere in memory."""
    parameters = {
        "query": {
            "type": "string",
            "description": "Search query (case-insensitive). Can be a word, phrase, or simple pattern.",
            "required": True
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results to return (default: 10)",
            "required": False
        }
    }
    
    user_id: Optional[str] = None
    
    def _search_file(self, path: Path, query: str) -> List[Tuple[str, str, int]]:
        """Search a single file for query matches.
        
        Returns list of (source, matched_line, line_number) tuples.
        Supports multi-word queries: all words must be present (AND logic).
        """
        results = []
        try:
            if not path.exists():
                return results
            
            content = path.read_text()
            lines = content.split('\n')
            
            # Split query into words for multi-word search
            query_words = [w.lower() for w in query.split() if len(w) >= 2]
            if not query_words:
                query_words = [query.lower()]
            
            for i, line in enumerate(lines, 1):
                line_lower = line.lower()
                # All query words must be present in the line (AND logic)
                if all(word in line_lower for word in query_words):
                    # Get context: include surrounding lines
                    start = max(0, i - 2)
                    end = min(len(lines), i + 1)
                    context_lines = lines[start:end]
                    context = '\n'.join(context_lines).strip()
                    
                    source = path.name
                    if path.parent.name == "memory":
                        source = f"memory/{path.name}"
                    
                    results.append((source, context, i))
        except Exception:
            pass
        
        return results
    
    async def execute(self, query: str = "", limit: int = 10) -> ToolResult:
        if not self.user_id:
            return ToolResult(success=False, error="User ID not set")
        
        if not query or len(query.strip()) < 2:
            return ToolResult(success=False, error="Query must be at least 2 characters")
        
        query = query.strip()
        
        try:
            user_dir = get_user_dir(self.user_id)
            all_results: List[Tuple[str, str, int]] = []
            
            # Search USER.md
            user_file = user_dir / "USER.md"
            all_results.extend(self._search_file(user_file, query))
            
            # Search MEMORY.md
            memory_file = user_dir / "MEMORY.md"
            all_results.extend(self._search_file(memory_file, query))
            
            # Search all daily logs (sorted by date, newest first)
            memory_dir = user_dir / "memory"
            if memory_dir.exists():
                daily_files = sorted(memory_dir.glob("*.md"), reverse=True)
                for daily_file in daily_files:
                    all_results.extend(self._search_file(daily_file, query))
            
            if not all_results:
                return ToolResult(
                    success=True,
                    output=f"No matches found for '{query}' in any memory files."
                )
            
            # Deduplicate similar results (same file, overlapping context)
            seen_contexts = set()
            unique_results = []
            for source, context, line_num in all_results:
                # Use first 50 chars of context as dedup key
                key = (source, context[:50])
                if key not in seen_contexts:
                    seen_contexts.add(key)
                    unique_results.append((source, context, line_num))
            
            # Limit results
            unique_results = unique_results[:limit]
            
            # Format output
            output_lines = [f"🔍 Found {len(unique_results)} match(es) for '{query}':\n"]
            
            for i, (source, context, line_num) in enumerate(unique_results, 1):
                # Highlight the query in context
                highlighted = re.sub(
                    f'({re.escape(query)})',
                    r'**\1**',
                    context,
                    flags=re.IGNORECASE
                )
                output_lines.append(f"[{i}] {source} (line {line_num}):")
                output_lines.append(f"    {highlighted}")
                output_lines.append("")
            
            return ToolResult(success=True, output='\n'.join(output_lines))
            
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# Export tools
MEMORY_TOOLS = [
    MemoryLogTool(),
    MemoryReadTool(),
    MemoryUpdateTool(),
    MemorySearchTool(),
    # UserUpdateTool(),
]
