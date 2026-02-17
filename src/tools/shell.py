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
    ALLOWED = {"cat", "head", "tail", "wc", "grep", "rg", "find", "ls", "pwd", "echo", "date", "whoami", "curl", "pkill", "pgrep"}
    
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
                return ToolResult(False, "", f"Use run_bash or run_python for scripts. Allowed commands: {', '.join(sorted(self.ALLOWED))}")
            
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


class KillProcessTool(Tool):
    name = "kill_process"
    description = "Kill a process by PID. Use list_processes first to find PID."
    parameters = {"pid": "integer - process ID to kill", "signal": "string - signal name (default: TERM)"}
    
    async def execute(self, pid: int = 0, signal: str = "TERM", **kwargs) -> ToolResult:
        try:
            if not pid:
                return ToolResult(False, "", "PID required")
            
            # Validate PID is a number
            try:
                pid = int(pid)
            except (ValueError, TypeError):
                return ToolResult(False, "", f"Invalid PID: {pid}")
            
            # Don't allow killing PID 1 or system processes
            if pid <= 1:
                return ToolResult(False, "", "Cannot kill system processes")
            
            # Allowed signals
            allowed_signals = {"TERM", "KILL", "INT", "HUP", "9", "15"}
            signal = str(signal).upper()
            if signal not in allowed_signals:
                return ToolResult(False, "", f"Signal must be one of: {', '.join(allowed_signals)}")
            
            import os
            import signal as sig
            
            # Map signal names
            sig_map = {
                "TERM": sig.SIGTERM,
                "15": sig.SIGTERM,
                "KILL": sig.SIGKILL,
                "9": sig.SIGKILL,
                "INT": sig.SIGINT,
                "HUP": sig.SIGHUP,
            }
            
            try:
                os.kill(pid, sig_map.get(signal, sig.SIGTERM))
                return ToolResult(True, f"Sent {signal} to PID {pid}")
            except ProcessLookupError:
                return ToolResult(False, "", f"Process {pid} not found")
            except PermissionError:
                return ToolResult(False, "", f"Permission denied to kill PID {pid}")
                
        except Exception as e:
            return ToolResult(False, "", str(e))


class ListProcessesTool(Tool):
    name = "list_processes"
    description = "List running processes (user processes only)"
    parameters = {}
    
    async def execute(self, **kwargs) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ps", "aux",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace")
            
            if len(output) > 5000:
                output = output[:5000] + "\n... (truncated)"
            
            return ToolResult(True, output)
        except Exception as e:
            return ToolResult(False, "", str(e))


class RunPythonTool(Tool):
    name = "run_python"
    description = "Run a Python script. Write the full script content."
    parameters = {"script": "string - Python script content to execute"}
    
    async def execute(self, script: str = "", **kwargs) -> ToolResult:
        try:
            script = script.strip()
            if not script:
                return ToolResult(False, "", "Empty script")
            
            # Block dangerous imports/calls
            dangerous = ["os.system", "subprocess.call", "eval(", "exec(", "__import__"]
            for d in dangerous:
                if d in script:
                    return ToolResult(False, "", f"Blocked: {d}")
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='/tmp') as f:
                f.write(f"import os; os.chdir('{WORKSPACE}')\n")
                f.write(script)
                script_path = f.name
            
            try:
                proc = await asyncio.create_subprocess_exec(
                    "python3", script_path,
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
