"""Context loader with user isolation and mtime-based caching."""

import os
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Optional

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/workspace")


# --- mtime-based file cache ---

@dataclass
class CachedFile:
    """Cached file content with modification time."""
    mtime: float
    content: str


_cache: Dict[str, CachedFile] = {}
_cache_lock = threading.Lock()


def read_file_cached(path: Path) -> Optional[str]:
    """
    Read file with mtime-based caching.
    
    Only performs disk read if file has been modified since last cache.
    Returns None if file doesn't exist.
    """
    try:
        if not path.exists():
            # Remove from cache if file was deleted
            path_str = str(path)
            with _cache_lock:
                _cache.pop(path_str, None)
            return None
        
        path_str = str(path)
        current_mtime = path.stat().st_mtime
        
        with _cache_lock:
            if path_str in _cache:
                cached = _cache[path_str]
                if cached.mtime == current_mtime:
                    return cached.content  # Cache HIT
            
            # Cache MISS — reload from disk
            content = path.read_text()
            _cache[path_str] = CachedFile(mtime=current_mtime, content=content)
            return content
    except Exception:
        return None


def get_cache_stats() -> dict:
    """Return cache statistics for debugging."""
    with _cache_lock:
        return {
            "entries": len(_cache),
            "files": list(_cache.keys())
        }


def clear_cache() -> None:
    """Clear the file cache."""
    with _cache_lock:
        _cache.clear()


def get_user_dir(user_id: str) -> Path:
    """Get the user's directory path."""
    return Path(WORKSPACE_DIR) / "users" / str(user_id)


def ensure_user_dir(user_id: str) -> Path:
    """Create user directory structure if it doesn't exist."""
    user_dir = get_user_dir(user_id)
    memory_dir = user_dir / "memory"
    
    # Create directories
    memory_dir.mkdir(parents=True, exist_ok=True)
    
    # Create default USER.md if not exists
    user_file = user_dir / "USER.md"
    if not user_file.exists():
        user_file.write_text(f"# User {user_id}\n\n*(User info will be added here)*\n")
    
    # Create empty MEMORY.md if not exists
    memory_file = user_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("# Long-term Memory\n\n")
    
    return user_dir


def is_bot_unconfigured() -> bool:
    """Check if bot needs initial configuration (SOUL.md not set up)."""
    workspace = Path(WORKSPACE_DIR)
    soul_file = workspace / "SOUL.md"
    
    if not soul_file.exists():
        return True
    
    content = soul_file.read_text()
    return "_UNCONFIGURED_" in content


def read_file_safe(path: Path) -> Optional[str]:
    """Read file if exists, return None otherwise."""
    try:
        if path.exists():
            return path.read_text()
    except Exception:
        pass
    return None


def load_shared_context() -> str:
    """Load shared context files (SOUL.md, AGENTS.md, CONTEXT.md, TOOLS.md)."""
    workspace = Path(WORKSPACE_DIR)
    parts = []
    
    # Shared files in order: Identity → Rules → Domain → Tools (notes only)
    for filename in ["SOUL.md", "AGENTS.md", "CONTEXT.md", "TOOLS.md"]:
        content = read_file_cached(workspace / filename)
        if content:
            parts.append(f"## {filename}\n\n{content}")
    
    return "\n\n---\n\n".join(parts)


def load_user_context(user_id: str) -> str:
    """Load user-specific context files."""
    user_dir = ensure_user_dir(user_id)
    parts = []
    
    # User info
    user_md = read_file_cached(user_dir / "USER.md")
    if user_md:
        parts.append(f"## USER.md (Info tentang user ini)\n\n{user_md}")
    
    # Long-term memory
    memory_md = read_file_cached(user_dir / "MEMORY.md")
    if memory_md:
        parts.append(f"## MEMORY.md (Long-term memory)\n\n{memory_md}")
    
    # Recent daily logs (today + yesterday)
    memory_dir = user_dir / "memory"
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    for d in [yesterday, today]:
        daily_file = memory_dir / f"{d.isoformat()}.md"
        content = read_file_cached(daily_file)
        if content:
            parts.append(f"## Daily Log: {d.isoformat()}\n\n{content}")
    
    return "\n\n---\n\n".join(parts)


def load_full_context(user_id: str) -> str:
    """Load complete context for a user (shared + user-specific)."""
    shared = load_shared_context()
    user = load_user_context(user_id)
    
    parts = []
    if shared:
        parts.append("# Shared Context\n\n" + shared)
    if user:
        parts.append("# Your Context\n\n" + user)
    
    return "\n\n===\n\n".join(parts)


def load_conversation_history(user_id: str) -> list[dict]:
    """
    Load persisted conversation history for a user.
    Only loads today's messages if conversation recording is enabled.
    
    Args:
        user_id: Prefixed user ID (e.g., "tg_123456")
    
    Returns:
        List of message dicts with 'role' and 'content' keys
    """
    try:
        from .conversation import load_today
        return load_today(user_id)
    except ImportError:
        return []


def get_today_memory_path(user_id: str) -> Path:
    """Get path to today's memory file for a user."""
    user_dir = ensure_user_dir(user_id)
    today = date.today().isoformat()
    return user_dir / "memory" / f"{today}.md"


def append_to_daily_memory(user_id: str, content: str) -> bool:
    """Append content to today's memory file."""
    try:
        path = get_today_memory_path(user_id)
        
        # Read existing content
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
        return True
    except Exception:
        return False
