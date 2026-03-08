"""File operation tools - read, write, edit, list, send."""

import os
import base64
import mimetypes
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
    description = """✅ PREFERRED for updating existing files. Supports both text-based and line-based editing.

MODES:

1. SEARCH/REPLACE (text-based):
   old_text + new_text → find and replace exact text (must match once)

2. APPEND/PREPEND:
   content + append=true → add to end of file
   content + prepend=true → add to beginning of file

3. REPLACE LINES (line-based):
   start_line + end_line + content → replace lines with new content

4. INSERT LINES:
   after_line + content → insert content after specified line
   (use after_line=0 to insert at beginning)

5. DELETE LINES:
   start_line + end_line + delete=true → remove lines

⚠️ TIPS for search/replace:
- old_text must match EXACTLY (including whitespace)
- READ the file first to see actual content before editing
- For multiple similar patterns, edit one at a time
- Search for the KEYWORD in the file, don't assume full text format

Line numbers are 1-indexed. Regular users: workspace only. Admin: any path."""

    parameters = {
        "path": "string - relative path to file",
        # Text-based params
        "old_text": "string - exact text to find and replace",
        "new_text": "string - replacement text",
        # Append/prepend params
        "content": "string - content to add/insert",
        "append": "boolean - add content at end of file",
        "prepend": "boolean - add content at beginning of file",
        # Line-based params
        "start_line": "int - first line number (1-indexed, for replace/delete)",
        "end_line": "int - last line number (1-indexed, inclusive)",
        "after_line": "int - insert content after this line (0 = insert at beginning)",
        "delete": "boolean - if true with start_line/end_line, delete those lines",
    }

    async def execute(
        self,
        path: str = "",
        # Text-based
        old_text: str = "",
        new_text: str = "",
        # Append/prepend
        content: str = "",
        append: bool = False,
        prepend: bool = False,
        # Line-based
        start_line: int = 0,
        end_line: int = 0,
        after_line: int = -1,  # -1 means not set, 0 means insert at beginning
        delete: bool = False,
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

            lines = file_content.splitlines(keepends=True)
            total_lines = len(lines)

            # Determine mode and apply edit
            mode_desc = ""
            new_content = ""

            # === MODE 1: Search/Replace (text-based) ===
            if old_text:
                if old_text not in file_content:
                    preview = file_content[:500] + "..." if len(file_content) > 500 else file_content
                    return ToolResult(
                        False, "",
                        f"old_text not found in file. Preview:\n{preview}"
                    )

                count = file_content.count(old_text)
                if count > 1:
                    return ToolResult(
                        False, "",
                        f"old_text found {count} times. Provide more context to match exactly once."
                    )

                if new_text == "":
                    # Delete mode
                    new_content = file_content.replace(old_text, "", 1)
                    mode_desc = f"Deleted {len(old_text)} chars"
                else:
                    new_content = file_content.replace(old_text, new_text, 1)
                    mode_desc = f"Replaced {len(old_text)} chars with {len(new_text)} chars"

            # === MODE 2: Append ===
            elif append and content:
                new_content = file_content + content
                mode_desc = f"Appended {len(content)} chars"

            # === MODE 3: Prepend ===
            elif prepend and content:
                new_content = content + file_content
                mode_desc = f"Prepended {len(content)} chars"

            # === MODE 4: Replace Lines ===
            elif start_line > 0 and end_line > 0 and not delete:
                result = self._replace_lines(lines, start_line, end_line, content, total_lines)
                if not result[0]:
                    return ToolResult(False, "", result[1])
                new_content = result[1]
                mode_desc = result[2]

            # === MODE 5: Insert After Line ===
            elif after_line >= 0 and content:
                result = self._insert_after(lines, after_line, content, total_lines)
                if not result[0]:
                    return ToolResult(False, "", result[1])
                new_content = result[1]
                mode_desc = result[2]

            # === MODE 6: Delete Lines ===
            elif start_line > 0 and end_line > 0 and delete:
                result = self._delete_lines(lines, start_line, end_line, total_lines)
                if not result[0]:
                    return ToolResult(False, "", result[1])
                new_content = result[1]
                mode_desc = result[2]

            else:
                return ToolResult(
                    False, "",
                    "Invalid parameters. Use one of:\n"
                    "1. old_text + new_text (search/replace)\n"
                    "2. content + append=true (append)\n"
                    "3. content + prepend=true (prepend)\n"
                    "4. start_line + end_line + content (replace lines)\n"
                    "5. after_line + content (insert after line)\n"
                    "6. start_line + end_line + delete=true (delete lines)"
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

    def _replace_lines(self, lines: list, start: int, end: int, content: str, total: int) -> tuple:
        """Replace lines start through end (inclusive) with content.
        Returns: (success, result_or_error, description)
        """
        if start < 1:
            return (False, "start_line must be >= 1", "")
        if end < start:
            return (False, "end_line must be >= start_line", "")
        if start > total:
            return (False, f"start_line ({start}) exceeds file length ({total} lines)", "")

        # Clamp end to file length
        end = min(end, total)

        # Ensure content ends with newline
        if content and not content.endswith("\n"):
            content += "\n"

        before = lines[:start - 1]
        after = lines[end:]
        new_lines = content.splitlines(keepends=True) if content else []

        result = "".join(before) + "".join(new_lines) + "".join(after)
        old_count = end - start + 1
        new_count = len(new_lines)

        desc = f"Replaced lines {start}-{end} ({old_count} lines) with {new_count} lines"
        return (True, result, desc)

    def _insert_after(self, lines: list, after: int, content: str, total: int) -> tuple:
        """Insert content after specified line. after=0 means insert at beginning.
        Returns: (success, result_or_error, description)
        """
        if after < 0:
            return (False, "after_line must be >= 0", "")
        if after > total:
            return (False, f"after_line ({after}) exceeds file length ({total} lines)", "")

        # Ensure content ends with newline
        if content and not content.endswith("\n"):
            content += "\n"

        new_lines = content.splitlines(keepends=True)

        if after == 0:
            result = "".join(new_lines) + "".join(lines)
            desc = f"Inserted {len(new_lines)} lines at beginning"
        else:
            before = lines[:after]
            after_lines = lines[after:]
            result = "".join(before) + "".join(new_lines) + "".join(after_lines)
            desc = f"Inserted {len(new_lines)} lines after line {after}"

        return (True, result, desc)

    def _delete_lines(self, lines: list, start: int, end: int, total: int) -> tuple:
        """Delete lines start through end (inclusive).
        Returns: (success, result_or_error, description)
        """
        if start < 1:
            return (False, "start_line must be >= 1", "")
        if end < start:
            return (False, "end_line must be >= start_line", "")
        if start > total:
            return (False, f"start_line ({start}) exceeds file length ({total} lines)", "")

        # Clamp end to file length
        end = min(end, total)

        before = lines[:start - 1]
        after = lines[end:]

        result = "".join(before) + "".join(after)
        deleted_count = end - start + 1

        desc = f"Deleted lines {start}-{end} ({deleted_count} lines)"
        return (True, result, desc)


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


# Max file size for send_file (10MB)
SEND_FILE_MAX_SIZE = 10 * 1024 * 1024

# Common MIME types by extension (fallback if mimetypes module doesn't know)
_MIME_FALLBACKS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".zip": "application/zip",
    ".txt": "text/plain",
    ".json": "application/json",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
}


class SendFileTool(Tool):
    name = "send_file"
    description = (
        "Send a file from workspace to the user via the current chat channel "
        "(Telegram, WhatsApp, etc). Use this to deliver PDFs, images, documents, "
        "or any file that the user requested. The file must already exist in workspace."
    )
    parameters = {
        "path": "string - file path relative to /workspace (e.g. 'users/tg_123/invoice.pdf')",
        "caption": "string - (optional) caption/message to send with the file",
    }

    async def execute(self, path: str = "", caption: str = "", **kwargs) -> ToolResult:
        try:
            full_path = self.validate_path(path)

            if not os.path.exists(full_path):
                return ToolResult(False, "", f"File not found: {path}")

            if not os.path.isfile(full_path):
                return ToolResult(False, "", f"Not a file: {path}")

            file_size = os.path.getsize(full_path)
            if file_size > SEND_FILE_MAX_SIZE:
                size_mb = file_size / (1024 * 1024)
                return ToolResult(False, "", f"File too large ({size_mb:.1f}MB, max 10MB)")

            if file_size == 0:
                return ToolResult(False, "", f"File is empty: {path}")

            # Detect content type
            filename = os.path.basename(full_path)
            _, ext = os.path.splitext(filename.lower())
            content_type = mimetypes.guess_type(full_path)[0]
            if not content_type:
                content_type = _MIME_FALLBACKS.get(ext, "application/octet-stream")

            # Read and base64-encode
            with open(full_path, "rb") as f:
                data_b64 = base64.b64encode(f.read()).decode("ascii")

            return ToolResult(
                success=True,
                output="",
                file_data={
                    "__file__": True,
                    "filename": filename,
                    "data": data_b64,
                    "content_type": content_type,
                    "caption": caption,
                },
            )

        except ValueError as e:
            return ToolResult(False, "", str(e))
        except Exception as e:
            return ToolResult(False, "", f"Error sending file: {e}")
