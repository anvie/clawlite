"""File operation tools - read, write, list."""

import os
from .base import Tool, ToolResult, WORKSPACE


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read contents of a file from workspace"
    parameters = {"path": "string - relative path to file"}
    
    async def execute(self, path: str = "", **kwargs) -> ToolResult:
        try:
            full_path = self.validate_path(path)
            
            if not os.path.exists(full_path):
                return ToolResult(False, "", f"File not found: {path}")
            
            if not os.path.isfile(full_path):
                return ToolResult(False, "", f"Not a file: {path}")
            
            # Size limit (1MB)
            if os.path.getsize(full_path) > 1_000_000:
                return ToolResult(False, "", f"File too large (>1MB): {path}")
            
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            return ToolResult(True, content)
            
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"Error reading file: {e}")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write or create a file in workspace"
    parameters = {
        "path": "string - relative path to file",
        "content": "string - content to write"
    }
    
    async def execute(self, path: str = "", content: str = "", **kwargs) -> ToolResult:
        try:
            full_path = self.validate_path(path)
            
            # Create parent directories if needed
            parent = os.path.dirname(full_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            
            # Size limit (1MB)
            if len(content.encode("utf-8")) > 1_000_000:
                return ToolResult(False, "", "Content too large (>1MB)")
            
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return ToolResult(True, f"Written {len(content)} chars to {path}")
            
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"Error writing file: {e}")


class ListDirTool(Tool):
    name = "list_dir"
    description = "List contents of a directory in workspace"
    parameters = {"path": "string - relative path to directory (default: root)"}
    
    async def execute(self, path: str = ".", **kwargs) -> ToolResult:
        try:
            full_path = self.validate_path(path)
            
            if not os.path.exists(full_path):
                return ToolResult(False, "", f"Directory not found: {path}")
            
            if not os.path.isdir(full_path):
                return ToolResult(False, "", f"Not a directory: {path}")
            
            entries = []
            for entry in sorted(os.listdir(full_path)):
                entry_path = os.path.join(full_path, entry)
                if os.path.isdir(entry_path):
                    entries.append(f"📁 {entry}/")
                else:
                    size = os.path.getsize(entry_path)
                    entries.append(f"📄 {entry} ({size} bytes)")
            
            if not entries:
                return ToolResult(True, "(empty directory)")
            
            return ToolResult(True, "\n".join(entries))
            
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"Error listing directory: {e}")
