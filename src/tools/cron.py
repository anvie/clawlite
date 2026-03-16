"""Cron management tools with built-in reminder support."""

import os
import sys
import asyncio
import re
import logging
from pathlib import Path
from .base import Tool, ToolResult, WORKSPACE

logger = logging.getLogger("clawlite.tools.cron")

# ClawLite installation directory (for send-message functionality)
CLAWLITE_DIR = Path(__file__).parent.parent.parent.resolve()


def get_send_command(user_id: str, message: str) -> str:
    """
    Build the command to send a message to a user.
    
    Uses ClawLite's internal send mechanism via Python CLI.
    
    Args:
        user_id: Prefixed user ID (e.g., "tg_123456")
        message: Message text to send
    
    Returns:
        Shell command string
    """
    # Escape message for shell
    escaped_msg = message.replace("'", "'\\''")
    
    # Use ClawLite's venv python to call send CLI
    venv_python = CLAWLITE_DIR / ".venv" / "bin" / "python"
    if not venv_python.exists():
        # Fallback to system python
        venv_python = sys.executable
    
    return f"cd {CLAWLITE_DIR} && {venv_python} -m src.cli.send -u '{user_id}' -m '{escaped_msg}'"


def validate_cron_schedule(schedule: str) -> tuple[bool, str]:
    """Validate cron expression using croniter."""
    try:
        from croniter import croniter
        # croniter validates by trying to create an iterator
        croniter(schedule)
        return True, ""
    except ImportError:
        # Fallback to basic validation if croniter not installed
        parts = schedule.split()
        if len(parts) != 5:
            return False, "Schedule must have 5 parts: minute hour day month weekday"
        return True, ""
    except (ValueError, KeyError) as e:
        return False, f"Invalid cron expression: {e}"
    except Exception as e:
        return False, f"Cron validation error: {e}"


class ListCronTool(Tool):
    name = "list_cron"
    description = "List current cron jobs"
    parameters = {}
    
    async def execute(self, **kwargs) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "crontab", "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace")
            errors = stderr.decode("utf-8", errors="replace")
            
            if "no crontab" in errors.lower():
                logger.debug("No crontab found for current user")
                return ToolResult(True, "No cron jobs configured")
            
            if proc.returncode != 0:
                logger.warning(f"crontab -l failed: {errors[:200]}")
                return ToolResult(False, "", f"Failed to list cron jobs: {errors[:500]}")
            
            logger.debug(f"Listed cron jobs: {len(output.splitlines())} lines")
            return ToolResult(True, output or "No cron jobs configured")
            
        except asyncio.TimeoutError:
            logger.error("crontab -l timed out")
            return ToolResult(False, "", "Timed out listing cron jobs")
        except Exception as e:
            logger.exception("Error listing cron jobs")
            return ToolResult(False, "", f"Error listing cron jobs: {str(e)}")


class AddCronTool(Tool):
    name = "add_cron"
    description = "Add a cron job. Schedule format: minute hour day month weekday"
    parameters = {
        "schedule": "string - cron schedule (e.g., '*/5 * * * *' for every 5 min, '0 9 * * *' for 9am daily)",
        "command": "string - command to run",
        "comment": "string - optional comment/label for the job"
    }
    
    async def execute(
        self, 
        schedule: str = "", 
        command: str = "",
        comment: str = "",
        **kwargs
    ) -> ToolResult:
        try:
            if not schedule or not command:
                return ToolResult(False, "", "Both schedule and command required")
            
            # Validate schedule format using croniter
            valid, error = validate_cron_schedule(schedule)
            if not valid:
                return ToolResult(False, "", error)
            
            # Block dangerous commands
            dangerous = ["rm -rf", "sudo", "chmod 777", "> /dev/sd", "mkfs", "dd if="]
            for d in dangerous:
                if d in command:
                    return ToolResult(False, "", f"Blocked pattern in command: {d}")
            
            # Get current crontab
            proc = await asyncio.create_subprocess_exec(
                "crontab", "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            
            current = stdout.decode("utf-8", errors="replace")
            if "no crontab" in stderr.decode().lower():
                current = ""
            
            # Ensure PATH is set at the top of crontab
            path_line = "PATH=/usr/local/bin:/usr/bin:/bin"
            if path_line not in current:
                if current:
                    current = path_line + "\n" + current
                else:
                    current = path_line + "\n"
            
            # Build new entry
            if comment:
                new_entry = f"# {comment}\n{schedule} {command}"
            else:
                new_entry = f"{schedule} {command}"
            
            # Append new entry
            if current and not current.endswith("\n"):
                current += "\n"
            new_crontab = current + new_entry + "\n"
            
            # Install new crontab
            proc = await asyncio.create_subprocess_exec(
                "crontab", "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=new_crontab.encode()),
                timeout=10
            )
            
            if proc.returncode != 0:
                errors = stderr.decode("utf-8", errors="replace")
                logger.warning(f"Failed to add cron job: {errors[:200]}")
                return ToolResult(False, "", f"Failed to add cron: {errors[:500]}")
            
            logger.info(f"Added cron job: {schedule} {command[:50]}...")
            return ToolResult(True, f"Added cron job: {schedule} {command}")
            
        except asyncio.TimeoutError:
            logger.error("crontab command timed out")
            return ToolResult(False, "", "Timed out adding cron job")
        except Exception as e:
            logger.exception("Error adding cron job")
            return ToolResult(False, "", f"Error adding cron job: {str(e)}")


class RemoveCronTool(Tool):
    name = "remove_cron"
    description = "Remove a cron job by pattern match (matches command or comment)"
    parameters = {
        "pattern": "string - text to match in the cron entry (command or comment)"
    }
    
    async def execute(self, pattern: str = "", **kwargs) -> ToolResult:
        try:
            if not pattern:
                return ToolResult(False, "", "Pattern required to identify cron job")
            
            # Get current crontab
            proc = await asyncio.create_subprocess_exec(
                "crontab", "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            
            current = stdout.decode("utf-8", errors="replace")
            if "no crontab" in stderr.decode().lower() or not current.strip():
                return ToolResult(False, "", "No cron jobs to remove")
            
            # Filter out matching lines (and their comment lines)
            lines = current.split("\n")
            new_lines = []
            removed = []
            skip_next = False
            
            for i, line in enumerate(lines):
                if pattern in line:
                    removed.append(line)
                    # If previous line is a comment, remove it too
                    if new_lines and new_lines[-1].startswith("#"):
                        removed.insert(0, new_lines.pop())
                    continue
                new_lines.append(line)
            
            if not removed:
                return ToolResult(False, "", f"No cron jobs matching '{pattern}'")
            
            # Install new crontab
            new_crontab = "\n".join(new_lines)
            if new_crontab.strip():
                proc = await asyncio.create_subprocess_exec(
                    "crontab", "-",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=new_crontab.encode()),
                    timeout=10
                )
            else:
                # Remove crontab entirely if empty
                proc = await asyncio.create_subprocess_exec(
                    "crontab", "-r",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
            
            logger.info(f"Removed {len(removed)} cron entry(s)")
            return ToolResult(True, f"Removed {len(removed)} cron entry(s):\n" + "\n".join(removed))
            
        except asyncio.TimeoutError:
            logger.error("crontab command timed out")
            return ToolResult(False, "", "Timed out removing cron job")
        except Exception as e:
            logger.exception("Error removing cron job")
            return ToolResult(False, "", f"Error removing cron job: {str(e)}")
