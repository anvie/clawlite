"""Shell and script execution tools."""

import os
import asyncio
import shlex
import tempfile
from .base import Tool, ToolResult, WORKSPACE

# Timeout in seconds
EXEC_TIMEOUT = 60


class ExecTool(Tool):
    name = "exec"
    description = "Execute a shell command (cat, ls, grep, find, echo, date, pwd, head, tail, wc)"
    parameters = {"command": "string - the command to execute"}
    
    # Allowed commands
    ALLOWED = {"cat", "head", "tail", "wc", "grep", "rg", "find", "ls", "pwd", "echo", "date", "whoami", "curl", "pkill", "pgrep", "sed"}
    
    async def execute(self, command: str = "", **kwargs) -> ToolResult:
        try:
            command = command.strip()
            if not command:
                return ToolResult(False, "", "Empty command")
            
            # Block dangerous patterns
            dangerous = ["rm ", "sudo", "chmod", "chown", "> /dev", ">> /dev"]
            for d in dangerous:
                if d in command:
                    return ToolResult(False, "", f"Blocked: {d}")
            
            # Check allowlist
            try:
                parts = shlex.split(command)
                base_cmd = os.path.basename(parts[0]) if parts else ""
            except:
                base_cmd = command.split()[0] if command.split() else ""
            
            if base_cmd not in self.ALLOWED:
                return ToolResult(False, "", f"Use run_bash for scripts. Allowed commands: {', '.join(sorted(self.ALLOWED))}")
            
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=WORKSPACE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=EXEC_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(False, "", f"Timeout ({EXEC_TIMEOUT}s)")
            
            output = stdout.decode("utf-8", errors="replace")
            if len(output) > 10000:
                output = output[:10000] + "\n... (truncated)"
            
            if proc.returncode != 0:
                errors = stderr.decode("utf-8", errors="replace")
                return ToolResult(False, output, f"Exit {proc.returncode}: {errors[:500]}")
            
            return ToolResult(True, output or "(no output)")
        except Exception as e:
            return ToolResult(False, "", str(e))


class RunBashTool(Tool):
    name = "run_bash"
    description = "Run a bash script. Write the full script content."
    parameters = {"script": "string - bash script content to execute"}
    
    async def execute(self, script: str = "", **kwargs) -> ToolResult:
        try:
            script = script.strip()
            if not script:
                return ToolResult(False, "", "Empty script")
            
            # Block dangerous commands
            dangerous = ["rm -rf", "sudo", "chmod 777", "> /dev/sd", "mkfs", "dd if="]
            for d in dangerous:
                if d in script:
                    return ToolResult(False, "", f"Blocked pattern: {d}")
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, dir='/tmp') as f:
                f.write("#!/bin/bash\nset -e\n")
                f.write(f"cd {WORKSPACE}\n")
                f.write(script)
                script_path = f.name
            
            try:
                proc = await asyncio.create_subprocess_exec(
                    "bash", script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=WORKSPACE,
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=EXEC_TIMEOUT)
                except asyncio.TimeoutError:
                    proc.kill()
                    return ToolResult(False, "", f"Timeout ({EXEC_TIMEOUT}s)")
                
                output = stdout.decode("utf-8", errors="replace")
                errors = stderr.decode("utf-8", errors="replace")
                
                if len(output) > 10000:
                    output = output[:10000] + "\n... (truncated)"
                
                if proc.returncode != 0:
                    return ToolResult(False, output, f"Exit {proc.returncode}: {errors[:500]}")
                
                return ToolResult(True, output or "(no output)")
            finally:
                os.unlink(script_path)
                
        except Exception as e:
            return ToolResult(False, "", str(e))


