"""
Robust reminder system for ClawLite.

Supports:
- One-time reminders (relative: "5 menit", absolute: "14:30")
- Recurring reminders (cron schedule)
- List, edit, delete operations
- File-based storage (reminders.json)
"""

import os
import json
import re
import uuid
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from .base import Tool, ToolResult, WORKSPACE

logger = logging.getLogger("clawlite.tools.reminder")

# Default timezone
DEFAULT_TZ = ZoneInfo("Asia/Jakarta")

# Reminders file path
def get_reminders_file() -> Path:
    return Path(WORKSPACE) / "reminders.json"


def load_reminders() -> List[Dict[str, Any]]:
    """Load reminders from JSON file."""
    path = get_reminders_file()
    if not path.exists():
        return []
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_reminders(reminders: List[Dict[str, Any]]) -> bool:
    """Save reminders to JSON file."""
    path = get_reminders_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(reminders, f, indent=2, default=str)
        return True
    except IOError as e:
        logger.error(f"Failed to save reminders: {e}")
        return False


def parse_relative_time(text: str) -> Optional[datetime]:
    """
    Parse relative time expressions in Indonesian/English.
    
    Examples:
    - "5 menit" / "5 minutes" -> now + 5 minutes
    - "1 jam" / "1 hour" -> now + 1 hour
    - "30 detik" / "30 seconds" -> now + 30 seconds
    - "2 hari" / "2 days" -> now + 2 days
    """
    text = text.lower().strip()
    now = datetime.now(DEFAULT_TZ)
    
    # Patterns for Indonesian and English
    patterns = [
        # Minutes
        (r'(\d+)\s*(?:menit|minutes?|mins?|m)\b', 'minutes'),
        # Hours
        (r'(\d+)\s*(?:jam|hours?|hrs?|h)\b', 'hours'),
        # Seconds
        (r'(\d+)\s*(?:detik|seconds?|secs?|s)\b', 'seconds'),
        # Days
        (r'(\d+)\s*(?:hari|days?|d)\b', 'days'),
    ]
    
    for pattern, unit in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            delta = timedelta(**{unit: value})
            return now + delta
    
    return None


def parse_absolute_time(text: str) -> Optional[datetime]:
    """
    Parse absolute time expressions.
    
    Examples:
    - "14:30" -> today at 14:30
    - "09:00" -> today at 09:00 (or tomorrow if already passed)
    - "2026-03-17 14:30" -> specific datetime
    """
    text = text.strip()
    now = datetime.now(DEFAULT_TZ)
    
    # Try HH:MM format
    time_match = re.match(r'^(\d{1,2}):(\d{2})$', text)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # If time already passed today, schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)
        return target
    
    # Try YYYY-MM-DD HH:MM format
    dt_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})\s+(\d{1,2}):(\d{2})$', text)
    if dt_match:
        year, month, day = int(dt_match.group(1)), int(dt_match.group(2)), int(dt_match.group(3))
        hour, minute = int(dt_match.group(4)), int(dt_match.group(5))
        return datetime(year, month, day, hour, minute, tzinfo=DEFAULT_TZ)
    
    # Try YYYY-MM-DD format (default to 09:00)
    date_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', text)
    if date_match:
        year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        return datetime(year, month, day, 9, 0, tzinfo=DEFAULT_TZ)
    
    return None


def parse_time_input(text: str) -> tuple[Optional[datetime], Optional[str], str]:
    """
    Parse time input - returns (fire_at, cron_schedule, type).
    
    Returns:
        (datetime, None, "once") for one-time reminders
        (None, cron_expr, "recurring") for recurring reminders
        (None, None, "error") if parsing failed
    """
    text = text.strip()
    
    # Check if it's a cron expression (5 parts)
    parts = text.split()
    if len(parts) == 5 and all(
        re.match(r'^[\d\*\-,/]+$', p) for p in parts
    ):
        return (None, text, "recurring")
    
    # Try relative time first
    fire_at = parse_relative_time(text)
    if fire_at:
        return (fire_at, None, "once")
    
    # Try absolute time
    fire_at = parse_absolute_time(text)
    if fire_at:
        return (fire_at, None, "once")
    
    return (None, None, "error")


def format_reminder(r: Dict[str, Any], idx: int = None) -> str:
    """Format a reminder for display."""
    prefix = f"[{idx}] " if idx is not None else ""
    
    if r.get("type") == "recurring":
        schedule = r.get("schedule", "?")
        return f"{prefix}🔄 {r.get('label', 'Unnamed')} | Schedule: {schedule} | {r.get('message', '')[:50]}"
    else:
        fire_at = r.get("fire_at", "?")
        if isinstance(fire_at, str):
            # Parse and format nicely
            try:
                dt = datetime.fromisoformat(fire_at)
                fire_at = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass
        return f"{prefix}⏰ {r.get('label', 'Unnamed')} | Fire: {fire_at} | {r.get('message', '')[:50]}"


class AddReminderTool(Tool):
    """
    Create a reminder - supports one-time and recurring.
    
    Time formats:
    - Relative: "5 menit", "1 jam", "30 detik", "2 hari"
    - Absolute: "14:30", "2026-03-17 14:30"
    - Recurring (cron): "30 4 * * *" (daily at 04:30)
    """
    name = "add_reminder"
    description = (
        "Create a reminder. Supports one-time (relative/absolute time) and recurring (cron). "
        "Examples: '5 menit', '1 jam', '14:30', '30 4 * * *' for daily 04:30"
    )
    parameters = {
        "time": "string - when to fire: '5 menit', '1 jam', '14:30', or cron '30 4 * * *'",
        "message": "string - reminder message",
        "label": "string - optional label for easy reference"
    }
    
    async def execute(
        self,
        time: str = "",
        message: str = "",
        label: str = "",
        **kwargs
    ) -> ToolResult:
        if not time or not message:
            return ToolResult(False, "", "Both 'time' and 'message' are required")
        
        # Get user_id from context
        user_id = getattr(self, 'user_id', None)
        if not user_id:
            return ToolResult(False, "", "User ID not available")
        
        # Parse time input
        fire_at, schedule, reminder_type = parse_time_input(time)
        
        if reminder_type == "error":
            return ToolResult(
                False, "",
                f"Could not parse time '{time}'. Use: '5 menit', '1 jam', '14:30', or cron '30 4 * * *'"
            )
        
        # Generate ID and label
        reminder_id = str(uuid.uuid4())[:8]
        if not label:
            label = message[:20].replace(" ", "_")
        
        # Build reminder object
        reminder = {
            "id": reminder_id,
            "type": reminder_type,
            "user_id": user_id,
            "message": message,
            "label": label,
            "created_at": datetime.now(DEFAULT_TZ).isoformat(),
            "active": True,
        }
        
        if reminder_type == "once":
            reminder["fire_at"] = fire_at.isoformat()
            time_desc = fire_at.strftime("%Y-%m-%d %H:%M WIB")
        else:
            reminder["schedule"] = schedule
            time_desc = f"Recurring: {schedule}"
        
        # Load and save
        reminders = load_reminders()
        reminders.append(reminder)
        
        if not save_reminders(reminders):
            return ToolResult(False, "", "Failed to save reminder")
        
        logger.info(f"Created reminder {reminder_id} for {user_id}: {message[:30]}...")
        
        return ToolResult(
            True,
            f"✅ Reminder created!\n"
            f"ID: {reminder_id}\n"
            f"Type: {reminder_type}\n"
            f"Time: {time_desc}\n"
            f"Message: {message}\n"
            f"Label: {label}"
        )


class ListRemindersTool(Tool):
    """List all active reminders for the current user."""
    name = "list_reminders"
    description = "List all active reminders"
    parameters = {
        "all": "boolean - show all reminders including inactive (default: false)"
    }
    
    async def execute(self, all: bool = False, **kwargs) -> ToolResult:
        user_id = getattr(self, 'user_id', None)
        reminders = load_reminders()
        
        # Filter by user and active status
        if user_id:
            reminders = [r for r in reminders if r.get("user_id") == user_id]
        if not all:
            reminders = [r for r in reminders if r.get("active", True)]
        
        if not reminders:
            return ToolResult(True, "No reminders found.")
        
        lines = ["📋 Your reminders:\n"]
        for i, r in enumerate(reminders, 1):
            lines.append(format_reminder(r, i))
        
        return ToolResult(True, "\n".join(lines))


class EditReminderTool(Tool):
    """Edit an existing reminder."""
    name = "edit_reminder"
    description = "Edit an existing reminder by ID or label"
    parameters = {
        "id": "string - reminder ID or label",
        "time": "string - new time (optional)",
        "message": "string - new message (optional)",
        "label": "string - new label (optional)"
    }
    
    async def execute(
        self,
        id: str = "",
        time: str = "",
        message: str = "",
        label: str = "",
        **kwargs
    ) -> ToolResult:
        if not id:
            return ToolResult(False, "", "Reminder ID or label required")
        
        if not time and not message and not label:
            return ToolResult(False, "", "Nothing to update. Provide time, message, or label.")
        
        user_id = getattr(self, 'user_id', None)
        reminders = load_reminders()
        
        # Find the reminder
        found_idx = None
        for i, r in enumerate(reminders):
            if r.get("id") == id or r.get("label") == id:
                if not user_id or r.get("user_id") == user_id:
                    found_idx = i
                    break
        
        if found_idx is None:
            return ToolResult(False, "", f"Reminder '{id}' not found")
        
        reminder = reminders[found_idx]
        changes = []
        
        # Update fields
        if time:
            fire_at, schedule, reminder_type = parse_time_input(time)
            if reminder_type == "error":
                return ToolResult(False, "", f"Invalid time format: {time}")
            
            reminder["type"] = reminder_type
            if reminder_type == "once":
                reminder["fire_at"] = fire_at.isoformat()
                reminder.pop("schedule", None)
                changes.append(f"Time → {fire_at.strftime('%Y-%m-%d %H:%M')}")
            else:
                reminder["schedule"] = schedule
                reminder.pop("fire_at", None)
                changes.append(f"Schedule → {schedule}")
        
        if message:
            reminder["message"] = message
            changes.append(f"Message → {message[:30]}...")
        
        if label:
            reminder["label"] = label
            changes.append(f"Label → {label}")
        
        reminder["updated_at"] = datetime.now(DEFAULT_TZ).isoformat()
        reminders[found_idx] = reminder
        
        if not save_reminders(reminders):
            return ToolResult(False, "", "Failed to save changes")
        
        return ToolResult(True, f"✅ Reminder updated!\n" + "\n".join(changes))


class DeleteReminderTool(Tool):
    """Delete a reminder."""
    name = "delete_reminder"
    description = "Delete a reminder by ID or label"
    parameters = {
        "id": "string - reminder ID or label to delete"
    }
    
    async def execute(self, id: str = "", **kwargs) -> ToolResult:
        if not id:
            return ToolResult(False, "", "Reminder ID or label required")
        
        user_id = getattr(self, 'user_id', None)
        reminders = load_reminders()
        
        # Find and remove
        new_reminders = []
        removed = None
        
        for r in reminders:
            if (r.get("id") == id or r.get("label") == id) and \
               (not user_id or r.get("user_id") == user_id):
                removed = r
            else:
                new_reminders.append(r)
        
        if not removed:
            return ToolResult(False, "", f"Reminder '{id}' not found")
        
        if not save_reminders(new_reminders):
            return ToolResult(False, "", "Failed to delete reminder")
        
        return ToolResult(
            True,
            f"✅ Reminder deleted!\n"
            f"Label: {removed.get('label')}\n"
            f"Message: {removed.get('message', '')[:50]}"
        )
