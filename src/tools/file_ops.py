"""File operation tools - read, write, edit, list."""

import os
from .base import Tool, ToolResult, WORKSPACE


class ReadFileTool(Tool):
    name = "read_file"
    description = """Read contents of a file with optional line range.
Regular users: workspace only. Admin/owner: any path.
For large files, use offset/limit to read specific sections."""
    parameters = {
        "path": "string - relative path to file (or absolute for admin)",
        "offset": "int - start line number, 1-indexed (optional, default: 1)",
        "limit": "int - max lines to read (optional, default: 200)"
    }
    
    async def execute(self, path: str = "", offset: int = 1, limit: int = 200, **kwargs) -> ToolResult:
        try:
            full_path = self.validate_path(path)
            
            if not os.path.exists(full_path):
                return ToolResult(False, "", f"File not found: {path}")
            
            if not os.path.isfile(full_path):
                return ToolResult(False, "", f"Not a file: {path}")
            
            # Size limit (1MB)
            file_size = os.path.getsize(full_path)
            if file_size > 1_000_000:
                return ToolResult(False, "", f"File too large (>1MB): {path}")
            
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            
            total_lines = len(all_lines)
            
            # Handle offset/limit
            offset = max(1, int(offset))  # 1-indexed
            limit = max(1, min(500, int(limit)))  # Cap at 500 lines
            
            start_idx = offset - 1
            end_idx = start_idx + limit
            
            selected_lines = all_lines[start_idx:end_idx]
            content = "".join(selected_lines)
            
            # Build output with metadata
            lines_shown = len(selected_lines)
            
            if offset == 1 and lines_shown >= total_lines:
                # Full file shown
                output = content
            else:
                # Partial file - add navigation hints
                header = f"[Lines {offset}-{offset + lines_shown - 1} of {total_lines}]\n"
                footer = ""
                if end_idx < total_lines:
                    remaining = total_lines - end_idx
                    footer = f"\n[{remaining} more lines. Use offset={end_idx + 1} to continue]"
                output = header + content + footer
            
            return ToolResult(True, output)
            
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"Error reading file: {e}")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create NEW files or OVERWRITE entire file. ⚠️ For UPDATES use edit_file instead! Regular users: workspace only. Admin/owner: any path."
    parameters = {
        "path": "string - relative path to file (or absolute for admin)",
        "content": "string - content to write (replaces entire file)"
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


class EditFileTool(Tool):
    name = "edit_file"
    description = """✅ PREFERRED for updating existing files (AGENTS.md, TOOLS.md, etc.). Safer than write_file - won't lose data!
Regular users: workspace only. Admin/owner: any path.

Modes:
1. Search/replace: provide old_text and new_text (old_text must match exactly once) - SAFEST
2. Append: set append=true to add content at end of file
3. Prepend: set prepend=true to add content at beginning of file

More token-efficient than write_file for small changes."""
    
    parameters = {
        "path": "string - relative path to file",
        "old_text": "string - exact text to find and replace (for search/replace mode)",
        "new_text": "string - replacement text (for search/replace mode)",
        "content": "string - content to add (for append/prepend mode)",
        "append": "boolean - if true, append content to end of file",
        "prepend": "boolean - if true, prepend content to beginning of file",
    }
    
    async def execute(
        self,
        path: str = "",
        old_text: str = "",
        new_text: str = "",
        content: str = "",
        append: bool = False,
        prepend: bool = False,
        **kwargs
    ) -> ToolResult:
        try:
            full_path = self.validate_path(path)
            
            if not os.path.exists(full_path):
                return ToolResult(False, "", f"File not found: {path}")
            
            if not os.path.isfile(full_path):
                return ToolResult(False, "", f"Not a file: {path}")
            
            # Read current content
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                file_content = f.read()
            
            # Determine mode and apply edit
            if append and content:
                # Append mode
                new_content = file_content + content
                mode_desc = f"Appended {len(content)} chars"
                
            elif prepend and content:
                # Prepend mode
                new_content = content + file_content
                mode_desc = f"Prepended {len(content)} chars"
                
            elif old_text and new_text is not None:
                # Search/replace mode
                if old_text not in file_content:
                    # Show context to help debug
                    preview = file_content[:500] + "..." if len(file_content) > 500 else file_content
                    return ToolResult(
                        False, "",
                        f"old_text not found in file. File preview:\n{preview}"
                    )
                
                # Count occurrences
                count = file_content.count(old_text)
                if count > 1:
                    return ToolResult(
                        False, "",
                        f"old_text found {count} times. Please provide more context to match exactly once."
                    )
                
                new_content = file_content.replace(old_text, new_text, 1)
                mode_desc = f"Replaced {len(old_text)} chars with {len(new_text)} chars"
                
            elif old_text and new_text == "":
                # Delete mode (replace with empty string)
                if old_text not in file_content:
                    return ToolResult(False, "", "old_text not found in file")
                
                count = file_content.count(old_text)
                if count > 1:
                    return ToolResult(
                        False, "",
                        f"old_text found {count} times. Please provide more context to match exactly once."
                    )
                
                new_content = file_content.replace(old_text, "", 1)
                mode_desc = f"Deleted {len(old_text)} chars"
                
            else:
                return ToolResult(
                    False, "",
                    "Invalid parameters. Use either: (1) old_text + new_text for replace, "
                    "(2) content + append=true, or (3) content + prepend=true"
                )
            
            # Size limit check
            if len(new_content.encode("utf-8")) > 1_000_000:
                return ToolResult(False, "", "Resulting file too large (>1MB)")
            
            # Write back
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return ToolResult(True, f"{mode_desc} in {path}")
            
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"Error editing file: {e}")


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
