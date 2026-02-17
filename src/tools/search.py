"""Search tools using ripgrep."""

import os
import asyncio
from .base import Tool, ToolResult, WORKSPACE


class GrepTool(Tool):
    name = "grep"
    description = "Search for text/pattern in files using ripgrep. Fast and recursive."
    parameters = {
        "pattern": "string - text or regex pattern to search",
        "path": "string - file or directory to search (default: workspace root)",
        "flags": "string - optional rg flags like -i (ignore case), -w (word), -l (files only)"
    }
    
    async def execute(
        self, 
        pattern: str = "", 
        path: str = ".",
        flags: str = "",
        **kwargs
    ) -> ToolResult:
        try:
            if not pattern:
                return ToolResult(False, "", "Pattern required")
            
            search_path = self.validate_path(path)
            
            # Build command
            cmd = ["rg", "--color=never", "-n"]  # no color, line numbers
            
            # Add safe flags
            safe_flags = {"-i", "-w", "-l", "-c", "-v", "-F", "-e", "--hidden"}
            if flags:
                for flag in flags.split():
                    if flag in safe_flags or flag.startswith("--type=") or flag.startswith("-g"):
                        cmd.append(flag)
            
            cmd.append(pattern)
            cmd.append(search_path)
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=WORKSPACE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(False, "", "Search timeout (30s)")
            
            output = stdout.decode("utf-8", errors="replace")
            
            if len(output) > 10000:
                output = output[:10000] + "\n... (truncated)"
            
            if proc.returncode == 0:
                return ToolResult(True, output or "No matches found")
            elif proc.returncode == 1:
                return ToolResult(True, "No matches found")
            else:
                errors = stderr.decode("utf-8", errors="replace")
                return ToolResult(False, "", f"rg error: {errors[:500]}")
                
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", str(e))


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Alias for grep. Search text in files using ripgrep."
    parameters = {
        "pattern": "string - text or regex pattern",
        "path": "string - directory to search (default: root)"
    }
    
    async def execute(self, pattern: str = "", path: str = ".", **kwargs) -> ToolResult:
        grep = GrepTool()
        return await grep.execute(pattern=pattern, path=path, flags="-i")
