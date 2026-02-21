"""Skill Manager - Install, remove, and manage ClawLite skills."""

import os
import sys
import json
import shutil
import subprocess
import argparse
import re
from pathlib import Path

# Default skills directory (can be overridden via env)
SKILLS_DIR = Path(os.getenv("SKILLS_DIR", "./skills"))

# ============================================================================
# Scaffold Templates
# ============================================================================

TEMPLATE_MAIN_PY = '''"""
{name} skill for ClawLite.

This is the main entry point. The execute() function is called
when the LLM invokes this skill's tool.
"""


def execute(args: dict) -> str:
    """
    Execute the {name} skill.
    
    Args:
        args: Dictionary of arguments as defined in schema.json
        
    Returns:
        String result to show to user
    """
    # TODO: Implement your skill logic here
    example_param = args.get("example_param", "default")
    
    return f"{name} executed with: {{example_param}}"
'''

TEMPLATE_SCHEMA_JSON = '''{{
  "tool": "{tool_name}",
  "description": "{description}",
  "args": {{
    "example_param": "string"
  }}
}}
'''

TEMPLATE_PROMPT_MD = '''# {title} Skill

{description}

## Usage
Use the `{tool_name}` tool when you need to {description_lower}.

## Examples
- "Please {description_lower}"
'''

TEMPLATE_README_MD = '''# {title} Skill

{description}

## Installation

This skill is part of ClawLite. Place in `skills/{name}/` directory.

## Schema

| Argument | Type | Description |
|----------|------|-------------|
| example_param | string | Example parameter |

## Development

Edit `main.py` to implement your skill logic.
The `execute(args)` function receives arguments as defined in `schema.json`.
'''


def slugify(name: str) -> str:
    """Convert name to valid skill slug (lowercase, underscores)."""
    # Replace spaces and hyphens with underscores
    slug = re.sub(r'[\s\-]+', '_', name.lower())
    # Remove invalid characters
    slug = re.sub(r'[^a-z0-9_]', '', slug)
    # Remove leading/trailing underscores
    slug = slug.strip('_')
    return slug


def title_case(name: str) -> str:
    """Convert slug to Title Case."""
    return ' '.join(word.capitalize() for word in name.replace('_', ' ').split())


def get_skills_dir() -> Path:
    """Get and ensure skills directory exists."""
    skills_dir = SKILLS_DIR
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def validate_skill(skill_path: Path) -> tuple[bool, str]:
    """Validate skill structure. Returns (is_valid, error_message)."""
    if not skill_path.is_dir():
        return False, "Not a directory"
    
    main_py = skill_path / "main.py"
    if not main_py.exists():
        return False, "Missing main.py"
    
    # Check for execute function
    content = main_py.read_text()
    if "def execute(" not in content:
        return False, "main.py missing execute() function"
    
    # Optional but recommended files
    schema_json = skill_path / "schema.json"
    if schema_json.exists():
        try:
            json.loads(schema_json.read_text())
        except json.JSONDecodeError as e:
            return False, f"Invalid schema.json: {e}"
    
    return True, ""


def list_skills() -> None:
    """List all installed skills."""
    skills_dir = get_skills_dir()
    
    skills = []
    for item in skills_dir.iterdir():
        if item.is_dir() and not item.name.startswith((".", "_")):
            is_valid, error = validate_skill(item)
            
            # Get tool name from schema
            tool_name = item.name
            description = ""
            schema_file = item / "schema.json"
            if schema_file.exists():
                try:
                    schema = json.loads(schema_file.read_text())
                    tool_name = schema.get("tool", item.name)
                    description = schema.get("description", "")
                except:
                    pass
            
            skills.append({
                "name": item.name,
                "tool": tool_name,
                "description": description,
                "valid": is_valid,
                "error": error if not is_valid else None
            })
    
    if not skills:
        print("No skills installed.")
        print(f"\nSkills directory: {skills_dir.absolute()}")
        return
    
    print(f"Installed skills ({len(skills)}):\n")
    for skill in skills:
        status = "✓" if skill["valid"] else "✗"
        print(f"  {status} {skill['name']}")
        print(f"    Tool: {skill['tool']}")
        if skill["description"]:
            print(f"    Desc: {skill['description']}")
        if skill["error"]:
            print(f"    Error: {skill['error']}")
        print()


def install_skill(source: str, name: str = None) -> bool:
    """
    Install a skill from git URL or local path.
    
    Args:
        source: Git URL or local path
        name: Optional name override for the skill
    
    Returns:
        True if successful
    """
    skills_dir = get_skills_dir()
    
    # Determine if source is git URL or local path
    is_git = source.startswith(("http://", "https://", "git@"))
    
    if is_git:
        # Clone from git
        skill_name = name or source.rstrip("/").split("/")[-1].replace(".git", "")
        target_path = skills_dir / skill_name
        
        if target_path.exists():
            print(f"Error: Skill '{skill_name}' already exists. Remove it first.")
            return False
        
        print(f"Cloning {source}...")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", source, str(target_path)],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error cloning repository: {e.stderr}")
            return False
        
        # Remove .git directory to save space
        git_dir = target_path / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)
            
    else:
        # Copy from local path
        source_path = Path(source).resolve()
        
        if not source_path.exists():
            print(f"Error: Source path does not exist: {source}")
            return False
        
        if not source_path.is_dir():
            print(f"Error: Source must be a directory: {source}")
            return False
        
        skill_name = name or source_path.name
        target_path = skills_dir / skill_name
        
        if target_path.exists():
            print(f"Error: Skill '{skill_name}' already exists. Remove it first.")
            return False
        
        print(f"Copying {source_path}...")
        shutil.copytree(source_path, target_path)
    
    # Validate installed skill
    is_valid, error = validate_skill(target_path)
    if not is_valid:
        print(f"Warning: Installed skill has issues: {error}")
        print("The skill may not work correctly.")
    else:
        print(f"✓ Skill '{skill_name}' installed successfully!")
        
        # Show skill info
        schema_file = target_path / "schema.json"
        if schema_file.exists():
            try:
                schema = json.loads(schema_file.read_text())
                print(f"  Tool: {schema.get('tool', skill_name)}")
                print(f"  Description: {schema.get('description', 'N/A')}")
            except:
                pass
    
    return True


def remove_skill(name: str, force: bool = False) -> bool:
    """
    Remove an installed skill.
    
    Args:
        name: Skill name to remove
        force: Skip confirmation
    
    Returns:
        True if successful
    """
    skills_dir = get_skills_dir()
    skill_path = skills_dir / name
    
    if not skill_path.exists():
        print(f"Error: Skill '{name}' not found.")
        return False
    
    if not skill_path.is_dir():
        print(f"Error: '{name}' is not a skill directory.")
        return False
    
    if not force:
        confirm = input(f"Remove skill '{name}'? [y/N] ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return False
    
    shutil.rmtree(skill_path)
    print(f"✓ Skill '{name}' removed.")
    return True


def show_skill_info(name: str) -> None:
    """Show detailed info about a skill."""
    skills_dir = get_skills_dir()
    skill_path = skills_dir / name
    
    if not skill_path.exists():
        print(f"Error: Skill '{name}' not found.")
        return
    
    print(f"Skill: {name}")
    print(f"Path: {skill_path.absolute()}")
    print()
    
    # Validation status
    is_valid, error = validate_skill(skill_path)
    print(f"Status: {'✓ Valid' if is_valid else f'✗ Invalid - {error}'}")
    print()
    
    # Schema info
    schema_file = skill_path / "schema.json"
    if schema_file.exists():
        print("Schema (schema.json):")
        try:
            schema = json.loads(schema_file.read_text())
            print(f"  Tool name: {schema.get('tool', 'N/A')}")
            print(f"  Description: {schema.get('description', 'N/A')}")
            args = schema.get('args', {})
            if args:
                print(f"  Arguments:")
                for arg_name, arg_type in args.items():
                    print(f"    - {arg_name}: {arg_type}")
        except json.JSONDecodeError as e:
            print(f"  Error parsing: {e}")
    else:
        print("Schema: Not found (optional)")
    print()
    
    # Prompt info
    prompt_file = skill_path / "prompt.md"
    if prompt_file.exists():
        print("Prompt (prompt.md):")
        content = prompt_file.read_text().strip()
        # Show first 200 chars
        if len(content) > 200:
            print(f"  {content[:200]}...")
        else:
            print(f"  {content}")
    else:
        print("Prompt: Not found (optional)")
    print()
    
    # List files
    print("Files:")
    for item in sorted(skill_path.iterdir()):
        if not item.name.startswith((".", "_")):
            print(f"  - {item.name}")


def create_skill(name: str, description: str = None) -> bool:
    """
    Create a new skill with scaffold files.
    
    Args:
        name: Skill name (will be slugified)
        description: Optional description
    
    Returns:
        True if successful
    """
    skills_dir = get_skills_dir()
    
    # Normalize name
    skill_slug = slugify(name)
    if not skill_slug:
        print(f"Error: Invalid skill name '{name}'")
        return False
    
    skill_path = skills_dir / skill_slug
    
    if skill_path.exists():
        print(f"Error: Skill '{skill_slug}' already exists at {skill_path}")
        return False
    
    # Prepare template variables
    title = title_case(skill_slug)
    tool_name = f"{skill_slug}_tool"
    desc = description or f"A skill for {title.lower()}"
    desc_lower = desc.lower().rstrip('.')
    
    # Create directory
    skill_path.mkdir(parents=True, exist_ok=True)
    
    # Create files
    files = {
        "main.py": TEMPLATE_MAIN_PY.format(name=title),
        "schema.json": TEMPLATE_SCHEMA_JSON.format(
            tool_name=tool_name,
            description=desc
        ),
        "prompt.md": TEMPLATE_PROMPT_MD.format(
            title=title,
            tool_name=tool_name,
            description=desc,
            description_lower=desc_lower
        ),
        "README.md": TEMPLATE_README_MD.format(
            title=title,
            name=skill_slug,
            description=desc
        )
    }
    
    for filename, content in files.items():
        file_path = skill_path / filename
        file_path.write_text(content.strip() + "\n")
    
    print(f"✓ Created skill '{skill_slug}' at {skill_path}")
    print()
    print("Files created:")
    for filename in files:
        print(f"  - {filename}")
    print()
    print("Next steps:")
    print(f"  1. Edit {skill_path}/main.py to implement your logic")
    print(f"  2. Update {skill_path}/schema.json with your parameters")
    print(f"  3. Restart the bot to load the skill")
    
    return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="clawlite skill",
        description="Manage ClawLite skills"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # list
    subparsers.add_parser("list", help="List installed skills")
    
    # install
    install_parser = subparsers.add_parser("install", help="Install a skill")
    install_parser.add_argument("source", help="Git URL or local path")
    install_parser.add_argument("--name", "-n", help="Override skill name")
    
    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove a skill")
    remove_parser.add_argument("name", help="Skill name to remove")
    remove_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")
    
    # info
    info_parser = subparsers.add_parser("info", help="Show skill info")
    info_parser.add_argument("name", help="Skill name")
    
    # new
    new_parser = subparsers.add_parser("new", help="Create a new skill")
    new_parser.add_argument("name", help="Skill name")
    new_parser.add_argument("--description", "-d", help="Skill description")
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_skills()
    elif args.command == "install":
        success = install_skill(args.source, args.name)
        sys.exit(0 if success else 1)
    elif args.command == "remove":
        success = remove_skill(args.name, args.force)
        sys.exit(0 if success else 1)
    elif args.command == "info":
        show_skill_info(args.name)
    elif args.command == "new":
        success = create_skill(args.name, args.description)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
