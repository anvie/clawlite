"""JSON Schema definitions for ClawLite tools.

Phase 1 of Function Calling Harness implementation.
These schemas are used for:
1. Validating LLM tool call arguments
2. Type coercion (string -> int, etc.)
3. Generating structured error feedback

Schema format follows JSON Schema Draft 7.
"""

from typing import Dict, Any

# =============================================================================
# Tool Schemas
# =============================================================================

TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # File Operations
    # -------------------------------------------------------------------------
    "read_file": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
                "minLength": 1
            },
            "offset": {
                "type": "integer",
                "description": "Start line number (1-indexed)",
                "minimum": 1,
                "default": 1
            },
            "limit": {
                "type": "integer",
                "description": "Maximum lines to read",
                "minimum": 1,
                "maximum": 500,
                "default": 200
            }
        },
        "required": ["path"]
    },
    
    "write_file": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to write the file",
                "minLength": 1
            },
            "content": {
                "type": "string",
                "description": "Content to write"
            }
        },
        "required": ["path", "content"]
    },
    
    "edit_file": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit",
                "minLength": 1
            },
            "old_text": {
                "type": "string",
                "description": "Exact text to find and replace",
                "minLength": 1
            },
            "new_text": {
                "type": "string",
                "description": "Replacement text"
            }
        },
        "required": ["path", "old_text", "new_text"]
    },
    
    "list_dir": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list",
                "default": "."
            },
            "recursive": {
                "type": "boolean",
                "description": "List subdirectories recursively",
                "default": False
            },
            "max_depth": {
                "type": "integer",
                "description": "Max recursion depth",
                "minimum": 1,
                "maximum": 10,
                "default": 3
            }
        },
        "required": []
    },
    
    "send_file": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to send",
                "minLength": 1
            },
            "caption": {
                "type": "string",
                "description": "Optional caption for the file"
            }
        },
        "required": ["path"]
    },
    
    "analyze_image": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the image file",
                "minLength": 1
            },
            "prompt": {
                "type": "string",
                "description": "What to analyze in the image",
                "default": "Describe this image in detail"
            }
        },
        "required": ["path"]
    },
    
    "extract_document": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the document (PDF, DOCX, etc.)",
                "minLength": 1
            }
        },
        "required": ["path"]
    },
    
    # -------------------------------------------------------------------------
    # Shell Operations
    # -------------------------------------------------------------------------
    "exec": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
                "minLength": 1
            }
        },
        "required": ["command"]
    },
    
    "run_bash": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "Bash script content to execute",
                "minLength": 1
            }
        },
        "required": ["script"]
    },
    
    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------
    "grep": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Text or regex pattern to search",
                "minLength": 1
            },
            "path": {
                "type": "string",
                "description": "File or directory to search",
                "default": "."
            },
            "flags": {
                "type": "string",
                "description": "Optional rg flags (-i, -w, -l, etc.)",
                "default": ""
            }
        },
        "required": ["pattern"]
    },
    
    "find_files": {
        "type": "object",
        "properties": {
            "name_pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., *.py, test_*)",
                "minLength": 1
            },
            "path": {
                "type": "string",
                "description": "Starting directory",
                "default": "."
            },
            "recursive": {
                "type": "boolean",
                "description": "Search subdirectories",
                "default": True
            },
            "type": {
                "type": "string",
                "description": "Filter by type",
                "enum": ["file", "dir", "all"],
                "default": "file"
            }
        },
        "required": ["name_pattern"]
    },
    
    # -------------------------------------------------------------------------
    # Web Operations
    # -------------------------------------------------------------------------
    "web_search": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
                "minLength": 1
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return",
                "minimum": 1,
                "maximum": 10,
                "default": 5
            }
        },
        "required": ["query"]
    },
    
    "web_fetch": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch",
                "minLength": 1,
                "pattern": "^https?://"
            },
            "max_chars": {
                "type": "integer",
                "description": "Max characters to return",
                "minimum": 500,
                "maximum": 50000,
                "default": 8000
            }
        },
        "required": ["url"]
    },
    
    # -------------------------------------------------------------------------
    # Memory Operations
    # -------------------------------------------------------------------------
    "memory_log": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to log to daily memory",
                "minLength": 10
            }
        },
        "required": ["content"]
    },
    
    "memory_read": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format (optional)",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$"
            }
        },
        "required": []
    },
    
    "memory_update": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "New content for MEMORY.md",
                "minLength": 1
            }
        },
        "required": ["content"]
    },
    
    "memory_search": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for memory files",
                "minLength": 1
            },
            "max_results": {
                "type": "integer",
                "description": "Max results to return",
                "minimum": 1,
                "maximum": 20,
                "default": 5
            }
        },
        "required": ["query"]
    },
    
    # -------------------------------------------------------------------------
    # Cron Operations
    # -------------------------------------------------------------------------
    "list_cron": {
        "type": "object",
        "properties": {},
        "required": []
    },
    
    "add_cron": {
        "type": "object",
        "properties": {
            "schedule": {
                "type": "string",
                "description": "Cron expression (e.g., '0 9 * * *' for 9 AM daily)",
                "minLength": 1
            },
            "command": {
                "type": "string",
                "description": "Command to execute",
                "minLength": 1
            },
            "description": {
                "type": "string",
                "description": "Description of the cron job"
            }
        },
        "required": ["schedule", "command"]
    },
    
    "remove_cron": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "ID of the cron job to remove",
                "minLength": 1
            }
        },
        "required": ["job_id"]
    },
    
    # -------------------------------------------------------------------------
    # Reminder Operations
    # -------------------------------------------------------------------------
    "add_reminder": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Reminder message",
                "minLength": 1
            },
            "time": {
                "type": "string",
                "description": "When to remind (e.g., '5 menit', '2 jam', '14:30', 'besok 09:00')",
                "minLength": 1
            },
            "recurring": {
                "type": "string",
                "description": "Recurrence pattern (e.g., 'daily', 'weekly', 'monthly')"
            }
        },
        "required": ["message", "time"]
    },
    
    "list_reminders": {
        "type": "object",
        "properties": {
            "show_completed": {
                "type": "boolean",
                "description": "Include completed reminders",
                "default": False
            }
        },
        "required": []
    },
    
    "edit_reminder": {
        "type": "object",
        "properties": {
            "reminder_id": {
                "type": "string",
                "description": "ID of the reminder to edit",
                "minLength": 1
            },
            "message": {
                "type": "string",
                "description": "New message (optional)"
            },
            "time": {
                "type": "string",
                "description": "New time (optional)"
            }
        },
        "required": ["reminder_id"]
    },
    
    "delete_reminder": {
        "type": "object",
        "properties": {
            "reminder_id": {
                "type": "string",
                "description": "ID of the reminder to delete",
                "minLength": 1
            }
        },
        "required": ["reminder_id"]
    },
}


def get_schema(tool_name: str) -> Dict[str, Any]:
    """Get schema for a tool by name.
    
    Returns empty dict if no schema defined (allows any args).
    """
    return TOOL_SCHEMAS.get(tool_name, {})


def list_schema_tools() -> list[str]:
    """List all tools that have schemas defined."""
    return list(TOOL_SCHEMAS.keys())
