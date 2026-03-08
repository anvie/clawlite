# TOOLS.md — Tool Guide & Notes

## File Editing Guide

### edit_file — Unified File Editor

**Text-based modes:**

1. **Search/Replace** — find and replace exact text (must match once)
```json
{"tool": "edit_file", "args": {"path": "file.md", "old_text": "find this", "new_text": "replace with"}}
```

2. **Append** — add content at end of file
```json
{"tool": "edit_file", "args": {"path": "file.md", "content": "\n## New Section\n", "append": true}}
```

3. **Prepend** — add content at beginning of file
```json
{"tool": "edit_file", "args": {"path": "file.md", "content": "# Header\n\n", "prepend": true}}
```

4. **Delete text** — remove exact text
```json
{"tool": "edit_file", "args": {"path": "file.md", "old_text": "remove this", "new_text": ""}}
```

**Line-based modes:**

5. **Replace lines** — replace specific line range with new content
```json
{"tool": "edit_file", "args": {"path": "file.py", "start_line": 10, "end_line": 15, "content": "def new_function():\n    pass\n"}}
```

6. **Insert after line** — insert content after a specific line (use `after_line: 0` for beginning)
```json
{"tool": "edit_file", "args": {"path": "file.py", "after_line": 5, "content": "# inserted comment\n"}}
```

7. **Delete lines** — remove specific line range
```json
{"tool": "edit_file", "args": {"path": "file.py", "start_line": 10, "end_line": 15, "delete": true}}
```

**When to use which mode:**
- Text unique in file → search/replace (fastest, no read needed)
- Text appears multiple times → line-based (read file first to get line numbers)
- Adding to end/beginning → append/prepend
- Code changes → line-based (more reliable)

---

## Tool Tips

- `read_file` supports `offset` and `limit` for large files
- `run_bash` for multi-line scripts
- `grep` supports flags: `-i` (ignore case), `-w` (word), `-l` (files only), `-c` (count)
- `find_files` for glob patterns: `*.py`, `**/*.md`

---

## Servers & Services

*Document your server details:*

```
### Example Server
- Host: 192.168.1.100
- SSH: ssh user@192.168.1.100
- Services: nginx, postgres
```

## API Endpoints

*APIs you frequently use:*

```
### Example API
- URL: https://api.example.com/v1
- Auth: API key in header
```

## Cron Job Notes

*Track your scheduled tasks:*

| Schedule | Purpose | Notes |
|----------|---------|-------|
| `0 9 * * *` | Daily reminder | Via clawlite-send |

---

*This file is loaded into agent context. Keep it concise.*
