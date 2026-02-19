"""Search tools - content search (ripgrep) and file finder."""

import os
import asyncio
import fnmatch
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


class FindFilesTool(Tool):
    name = "find_files"
    description = "Find files/directories by name pattern. Like 'find' command."
    parameters = {
        "name_pattern": "string - glob pattern for filename (e.g., *.py, test_*, config.json)",
        "path": "string - starting directory (default: root)",
        "recursive": "bool - search subdirectories (default: true)",
        "type": "string - 'file', 'dir', or 'all' (default: file)"
    }
    
    async def execute(
        self,
        name_pattern: str = "",
        path: str = ".",
        recursive: bool = True,
        type: str = "file",
        **kwargs
    ) -> ToolResult:
        try:
            if not name_pattern:
                return ToolResult(False, "", "name_pattern required (e.g., *.py, test_*)")
            
            search_path = self.validate_path(path)
            
            if not os.path.exists(search_path):
                return ToolResult(False, "", f"Path not found: {path}")
            
            if not os.path.isdir(search_path):
                return ToolResult(False, "", f"Not a directory: {path}")
            
            # Normalize type
            find_type = type.lower() if type else "file"
            if find_type not in ("file", "dir", "all"):
                find_type = "file"
            
            matches = []
            max_results = 500  # Limit to prevent huge outputs
            
            if recursive:
                for root, dirs, files in os.walk(search_path):
                    # Skip hidden directories
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    
                    rel_root = os.path.relpath(root, WORKSPACE)
                    if rel_root == ".":
                        rel_root = ""
                    
                    # Check directories
                    if find_type in ("dir", "all"):
                        for d in dirs:
                            if fnmatch.fnmatch(d, name_pattern) or fnmatch.fnmatch(d.lower(), name_pattern.lower()):
                                match_path = os.path.join(rel_root, d) if rel_root else d
                                matches.append(f"📁 {match_path}/")
                                if len(matches) >= max_results:
                                    break
                    
                    # Check files
                    if find_type in ("file", "all"):
                        for f in files:
                            if f.startswith('.'):
                                continue
                            if fnmatch.fnmatch(f, name_pattern) or fnmatch.fnmatch(f.lower(), name_pattern.lower()):
                                match_path = os.path.join(rel_root, f) if rel_root else f
                                size = os.path.getsize(os.path.join(root, f))
                                matches.append(f"📄 {match_path} ({size} bytes)")
                                if len(matches) >= max_results:
                                    break
                    
                    if len(matches) >= max_results:
                        break
            else:
                # Non-recursive: only search in the specified directory
                try:
                    entries = os.listdir(search_path)
                except PermissionError:
                    return ToolResult(False, "", f"Permission denied: {path}")
                
                rel_path = os.path.relpath(search_path, WORKSPACE)
                if rel_path == ".":
                    rel_path = ""
                
                for entry in sorted(entries):
                    if entry.startswith('.'):
                        continue
                    
                    full_entry = os.path.join(search_path, entry)
                    is_dir = os.path.isdir(full_entry)
                    
                    # Check type filter
                    if find_type == "file" and is_dir:
                        continue
                    if find_type == "dir" and not is_dir:
                        continue
                    
                    # Check pattern match (case-insensitive)
                    if fnmatch.fnmatch(entry, name_pattern) or fnmatch.fnmatch(entry.lower(), name_pattern.lower()):
                        match_path = os.path.join(rel_path, entry) if rel_path else entry
                        if is_dir:
                            matches.append(f"📁 {match_path}/")
                        else:
                            size = os.path.getsize(full_entry)
                            matches.append(f"📄 {match_path} ({size} bytes)")
                        
                        if len(matches) >= max_results:
                            break
            
            if not matches:
                return ToolResult(True, f"No matches found for pattern: {name_pattern}")
            
            result = "\n".join(matches)
            if len(matches) >= max_results:
                result += f"\n... (truncated at {max_results} results)"
            
            return ToolResult(True, f"Found {len(matches)} match(es):\n{result}")
            
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"Error finding files: {e}")
