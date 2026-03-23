#!/usr/bin/env python3
"""
Reminder daemon for ClawLite.

Run via cron every minute:
* * * * * /path/to/clawlite/.venv/bin/python /path/to/clawlite/scripts/reminder-daemon.py

Checks reminders.json and fires any due reminders.
"""

import os
import sys
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add parent dir to path for imports
SCRIPT_DIR = Path(__file__).parent.resolve()
CLAWLITE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(CLAWLITE_DIR))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("reminder-daemon")

DEFAULT_TZ = ZoneInfo("Asia/Jakarta")


def get_workspace_dir() -> Path:
    """Get workspace directory from env or default."""
    return Path(os.environ.get("WORKSPACE_DIR", "/workspace"))


def get_reminders_file() -> Path:
    """Get reminders file path."""
    return get_workspace_dir() / "reminders.json"


def load_reminders() -> list:
    """Load reminders from JSON."""
    path = get_reminders_file()
    if not path.exists():
        return []
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load reminders: {e}")
        return []


def save_reminders(reminders: list) -> bool:
    """Save reminders to JSON."""
    path = get_reminders_file()
    try:
        with open(path, 'w') as f:
            json.dump(reminders, f, indent=2, default=str)
        return True
    except IOError as e:
        logger.error(f"Failed to save reminders: {e}")
        return False


def get_python_path() -> str:
    """Get the appropriate python path."""
    venv_python = CLAWLITE_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def send_message(user_id: str, message: str) -> bool:
    """Send message to user via ClawLite CLI."""
    import subprocess
    
    try:
        python_path = get_python_path()
        
        result = subprocess.run(
            [python_path, "-m", "src.cli.send", "-u", user_id, "-m", message],
            cwd=str(CLAWLITE_DIR),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info(f"Sent reminder to {user_id}: {message[:50]}...")
            return True
        else:
            logger.error(f"Failed to send: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Send command timed out")
        return False
    except Exception as e:
        logger.error(f"Send error: {e}")
        return False


def send_file(user_id: str, file_path: str, caption: str = "") -> bool:
    """Send file to user via ClawLite CLI."""
    import subprocess
    
    try:
        python_path = get_python_path()
        workspace = get_workspace_dir()
        
        # Resolve file path relative to workspace
        full_path = workspace / file_path
        if not full_path.exists():
            logger.error(f"Attachment not found: {full_path}")
            return False
        
        args = [python_path, "-m", "src.cli.send", "-u", user_id, "-f", str(full_path)]
        if caption:
            args.extend(["-c", caption])
        
        result = subprocess.run(
            args,
            cwd=str(CLAWLITE_DIR),
            capture_output=True,
            text=True,
            timeout=60  # Longer timeout for file uploads
        )
        
        if result.returncode == 0:
            logger.info(f"Sent file to {user_id}: {file_path}")
            return True
        else:
            logger.error(f"Failed to send file: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Send file command timed out")
        return False
    except Exception as e:
        logger.error(f"Send file error: {e}")
        return False


def check_cron_match(schedule: str, now: datetime) -> bool:
    """Check if cron schedule matches current time."""
    try:
        from croniter import croniter
        cron = croniter(schedule, now)
        prev_time = cron.get_prev(datetime)
        # Match if previous fire time is within the last minute
        diff = (now - prev_time).total_seconds()
        return 0 <= diff < 60
    except ImportError:
        # Fallback: simple pattern matching
        parts = schedule.split()
        if len(parts) != 5:
            return False
        
        minute, hour, dom, month, dow = parts
        
        def matches(pattern: str, value: int) -> bool:
            if pattern == "*":
                return True
            if pattern.isdigit():
                return int(pattern) == value
            if "/" in pattern:
                # */5 means every 5
                _, step = pattern.split("/")
                return value % int(step) == 0
            if "-" in pattern:
                # 1-5 means range
                start, end = pattern.split("-")
                return int(start) <= value <= int(end)
            if "," in pattern:
                # 1,3,5 means list
                return value in [int(x) for x in pattern.split(",")]
            return False
        
        return (
            matches(minute, now.minute) and
            matches(hour, now.hour) and
            matches(dom, now.day) and
            matches(month, now.month) and
            matches(dow, now.weekday())  # Note: cron uses 0=Sunday, Python uses 0=Monday
        )
    except Exception as e:
        logger.error(f"Cron check error: {e}")
        return False


def process_reminders():
    """Process all due reminders."""
    reminders = load_reminders()
    if not reminders:
        logger.debug("No reminders to process")
        return
    
    now = datetime.now(DEFAULT_TZ)
    updated = False
    new_reminders = []
    
    for r in reminders:
        if not r.get("active", True):
            new_reminders.append(r)
            continue
        
        should_fire = False
        remove_after = False
        
        if r.get("type") == "once":
            # One-time reminder
            fire_at_str = r.get("fire_at")
            if fire_at_str:
                try:
                    fire_at = datetime.fromisoformat(fire_at_str)
                    # Fire if time has passed (within last 2 minutes to avoid missing)
                    diff = (now - fire_at).total_seconds()
                    if 0 <= diff < 120:  # Within 2 minutes of fire time
                        should_fire = True
                        remove_after = True
                except Exception as e:
                    logger.error(f"Invalid fire_at: {fire_at_str}: {e}")
        
        elif r.get("type") == "recurring":
            # Recurring reminder - check cron schedule
            schedule = r.get("schedule")
            if schedule and check_cron_match(schedule, now):
                should_fire = True
                # Don't remove recurring reminders
        
        # Fire the reminder
        if should_fire:
            user_id = r.get("user_id")
            message = r.get("message", "Reminder!")
            label = r.get("label", "")
            attachment = r.get("attachment")
            
            # Add label prefix if exists
            full_message = f"🔔 {label}: {message}" if label else f"🔔 {message}"
            
            if user_id:
                # Send message first
                msg_success = send_message(user_id, full_message)
                
                # Send attachment if exists
                file_success = True
                if attachment:
                    file_success = send_file(user_id, attachment)
                    if not file_success:
                        logger.warning(f"Failed to send attachment for reminder {r.get('id')}")
                
                if msg_success:
                    logger.info(f"Fired reminder: {r.get('id')} - {label}" + 
                               (f" (with attachment: {attachment})" if attachment else ""))
                    r["last_fired"] = now.isoformat()
                    updated = True
        
        # Keep or remove
        if not remove_after:
            new_reminders.append(r)
        else:
            logger.info(f"Removed one-time reminder: {r.get('id')}")
            updated = True
    
    # Save if any changes
    if updated:
        save_reminders(new_reminders)


def main():
    """Main entry point."""
    logger.info("Reminder daemon started")
    
    # Check workspace exists
    workspace = get_workspace_dir()
    if not workspace.exists():
        logger.warning(f"Workspace not found: {workspace}")
        return
    
    process_reminders()
    logger.info("Reminder daemon finished")


if __name__ == "__main__":
    main()
