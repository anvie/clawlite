"""Base Tool class and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
import os

# Workspace path - all file operations are restricted to this
WORKSPACE = os.getenv("WORKSPACE_PATH", "/workspace")


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    output: str
    error: Optional[str] = None
    file_data: Optional[dict] = None  # For file responses (skills)


class Tool(ABC):
    """Base class for all tools."""
    
    name: str = ""
    description: str = ""
    parameters: dict = {}
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    def validate_path(self, path: str) -> str:
        """
        Validate and resolve a path to be within workspace.
        Raises ValueError if path escapes workspace.
        """
        # Handle relative paths
        if not path.startswith("/"):
            full_path = os.path.join(WORKSPACE, path)
        else:
            full_path = path
        
        # Resolve to absolute path
        resolved = os.path.realpath(full_path)
        
        # Check if within workspace
        workspace_resolved = os.path.realpath(WORKSPACE)
        if not resolved.startswith(workspace_resolved):
            raise ValueError(f"Path '{path}' is outside workspace")
        
        return resolved
