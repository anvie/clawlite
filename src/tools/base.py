"""Base Tool class and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import os
import logging

_logger = logging.getLogger("clawlite.tools.base")

# Workspace path - all file operations are restricted to this (for non-admin users)
WORKSPACE = os.getenv("WORKSPACE_PATH", "/workspace")


def _is_admin_user(user_id: Optional[str]) -> bool:
    """Check if user is owner or admin."""
    if not user_id:
        return False
    try:
        from ..access import is_admin
        return is_admin(user_id)
    except ImportError:
        return False


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    file_data: Optional[dict] = None  # For file responses (skills)
    exit_code: Optional[int] = None  # For shell tools (exec, run_bash)


class Tool(ABC):
    """Base class for all tools."""
    
    name: str = ""
    description: str = ""
    parameters: dict = {}
    user_id: Optional[str] = None  # Set by agent for access control
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    def validate_path(self, path: str, user_id: Optional[str] = None) -> str:
        """
        Validate and resolve a path.
        
        Security rules:
        - Owner/Admin users: can access any path
        - Regular users: restricted to workspace only
        
        Args:
            path: The path to validate
            user_id: Optional user ID for access check (falls back to self.user_id)
        
        Raises:
            ValueError: If path escapes workspace (for non-admin users)
        """
        # Use provided user_id or fall back to instance user_id
        effective_user_id = user_id or self.user_id
        
        # Handle relative paths
        if not path.startswith("/"):
            full_path = os.path.join(WORKSPACE, path)
        else:
            full_path = path
        
        # Resolve to absolute path
        resolved = os.path.realpath(full_path)
        
        # Admin/owner can access any path
        if _is_admin_user(effective_user_id):
            _logger.debug(f"Admin user {effective_user_id}: allowing path {resolved}")
            return resolved
        
        # Regular users: check if within workspace
        workspace_resolved = os.path.realpath(WORKSPACE)
        if not resolved.startswith(workspace_resolved):
            raise ValueError(f"Path '{path}' is outside workspace (admin access required)")
        
        return resolved
