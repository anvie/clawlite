"""Skill-based tools - dynamically loaded from workspace/skills/."""

import asyncio
from typing import Any
from .base import Tool, ToolResult


class SkillTool(Tool):
    """Wrapper that turns a skill module into a Tool."""
    
    def __init__(self, skill_name: str, skill_data: dict):
        self.skill_name = skill_name
        self.skill_data = skill_data
        
        # Extract from schema.json
        schema = skill_data.get('schema') or {}
        self.name = schema.get('tool', skill_name)
        self.description = schema.get('description', f"Skill: {skill_name}")
        self.parameters = schema.get('args', {})
        
        # The entrypoint module with execute(args) function
        self.module = skill_data.get('entrypoint')
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the skill's main.py execute() function."""
        if not self.module:
            return ToolResult(
                success=False,
                output="",
                error=f"Skill '{self.skill_name}' has no entrypoint (main.py)"
            )
        
        if not hasattr(self.module, 'execute'):
            return ToolResult(
                success=False,
                output="",
                error=f"Skill '{self.skill_name}' main.py has no execute() function"
            )
        
        try:
            # Run skill execute - may be sync or async
            result = self.module.execute(kwargs)
            
            # Handle async results
            if asyncio.iscoroutine(result):
                result = await result
            
            # Handle file responses (dict with __file__: True)
            if isinstance(result, dict) and result.get("__file__"):
                return ToolResult(
                    success=True,
                    output="",  # Empty output, file data in metadata
                    file_data=result,
                )
            
            return ToolResult(
                success=True,
                output=str(result) if result else "Done"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Skill error: {e}"
            )


def load_skill_tools() -> dict[str, SkillTool]:
    """Load all skills and return as Tool instances."""
    from ..core.skill_loader import discover_and_load_skills
    
    skill_tools = {}
    skills = discover_and_load_skills()
    
    for skill_name, skill_data in skills.items():
        tool = SkillTool(skill_name, skill_data)
        skill_tools[tool.name] = tool
    
    return skill_tools
