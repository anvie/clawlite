"""Conversation persistence utilities.

Saves conversation history to per-day JSONL files for each user.
Automatically cleans up files older than retention_days.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import get as config_get

logger = logging.getLogger("clawlite.conversation")

# Get workspace from env
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/workspace")

# Timezone (hardcoded to Asia/Jakarta for now)
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jakarta")
except ImportError:
    TZ = None  # Fall back to local time


def _now() -> datetime:
    """Get current datetime with timezone."""
    if TZ:
        return datetime.now(TZ)
    return datetime.now()


def _today() -> date:
    """Get today's date."""
    return _now().date()


def is_enabled() -> bool:
    """Check if conversation recording is enabled."""
    return config_get("conversation.record", False)


def get_retention_days() -> int:
    """Get retention days from config."""
    return config_get("conversation.retention_days", 3)


def get_convo_dir(user_id: str) -> Path:
    """Get user's conversations directory."""
    return Path(WORKSPACE_DIR) / "users" / str(user_id) / "conversations"


def get_today_file(user_id: str) -> Path:
    """Get path to today's conversation file."""
    convo_dir = get_convo_dir(user_id)
    today_str = _today().isoformat()
    return convo_dir / f"convo-{today_str}.jsonl"


def append_message(
    user_id: str,
    role: str,
    content: str,
    tool_calls: Optional[list] = None,
    tool_results: Optional[list] = None,
    thinking: Optional[str] = None,
) -> bool:
    """
    Append a message to today's conversation file.
    
    Args:
        user_id: Prefixed user ID (e.g., "tg_123456")
        role: Message role ("user", "assistant", "system")
        content: Message content
        tool_calls: Optional list of tool calls made
        tool_results: Optional list of tool results
        thinking: Optional CoT/reasoning content (for debugging)
    
    Returns:
        True if saved successfully, False otherwise
    """
    if not is_enabled():
        return False
    
    try:
        convo_file = get_today_file(user_id)
        
        # Create directory if needed
        convo_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Build message record
        record = {
            "ts": _now().isoformat(),
            "role": role,
            "content": content,
        }
        
        if tool_calls:
            record["tool_calls"] = tool_calls
        if tool_results:
            record["tool_results"] = tool_results
        if thinking:
            record["thinking"] = thinking
        
        # Append to file
        with open(convo_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        logger.debug(f"Saved {role} message for {user_id}")
        
        # Cleanup old files (cheap operation, run every append)
        cleanup_old_files(user_id)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to save conversation for {user_id}: {e}")
        return False


def load_today(user_id: str) -> list[dict]:
    """
    Load today's conversation history.
    
    Args:
        user_id: Prefixed user ID
    
    Returns:
        List of message dicts with role and content
    """
    if not is_enabled():
        return []
    
    convo_file = get_today_file(user_id)
    
    if not convo_file.exists():
        return []
    
    messages = []
    try:
        with open(convo_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    messages.append({
                        "role": record.get("role", "user"),
                        "content": record.get("content", ""),
                    })
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping corrupted line {line_num} in {convo_file}: {e}")
                    continue
        
        logger.debug(f"Loaded {len(messages)} messages for {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to load conversation for {user_id}: {e}")
    
    return messages


def clear_today(user_id: str) -> bool:
    """
    Delete today's conversation file.
    
    Args:
        user_id: Prefixed user ID
    
    Returns:
        True if cleared successfully
    """
    try:
        convo_file = get_today_file(user_id)
        if convo_file.exists():
            convo_file.unlink()
            logger.info(f"Cleared conversation for {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to clear conversation for {user_id}: {e}")
        return False


def cleanup_old_files(user_id: str) -> int:
    """
    Delete conversation files older than retention_days.
    
    Args:
        user_id: Prefixed user ID
    
    Returns:
        Number of files deleted
    """
    retention_days = get_retention_days()
    cutoff_date = _today() - timedelta(days=retention_days)
    
    convo_dir = get_convo_dir(user_id)
    if not convo_dir.exists():
        return 0
    
    deleted = 0
    
    try:
        for f in convo_dir.glob("convo-*.jsonl"):
            # Extract date from filename: convo-YYYY-MM-DD.jsonl
            try:
                date_str = f.stem.replace("convo-", "")
                file_date = date.fromisoformat(date_str)
                
                if file_date < cutoff_date:
                    f.unlink()
                    deleted += 1
                    logger.info(f"Deleted old conversation file: {f.name}")
                    
            except ValueError:
                # Invalid date format, skip
                continue
                
    except Exception as e:
        logger.error(f"Error during cleanup for {user_id}: {e}")
    
    return deleted
