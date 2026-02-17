"""Cron management tools."""

import os
import asyncio
import re
from .base import Tool, ToolResult, WORKSPACE


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
                return ToolResult(True, "No cron jobs configured")
            
            if proc.returncode != 0:
                return ToolResult(False, "", errors[:500])
            
            return ToolResult(True, output or "No cron jobs configured")
            
        except Exception as e:
            return ToolResult(False, "", str(e))


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
            
            # Validate schedule format (basic check)
            parts = schedule.split()
            if len(parts) != 5:
                return ToolResult(False, "", "Schedule must have 5 parts: minute hour day month weekday")
            
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
                return ToolResult(False, "", f"Failed to add cron: {errors[:500]}")
            
            return ToolResult(True, f"Added cron job: {schedule} {command}")
            
        except Exception as e:
            return ToolResult(False, "", str(e))


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
            
            return ToolResult(True, f"Removed {len(removed)} cron entry(s):\n" + "\n".join(removed))
            
        except Exception as e:
            return ToolResult(False, "", str(e))
