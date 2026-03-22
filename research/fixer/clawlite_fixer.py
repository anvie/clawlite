"""ClawLite Core Fixer for AutoImprove.

Applies fixes to ClawLite core files (AGENTS.md, src/*.py, etc.)
in both production instance and dev repository.
"""

import logging
import subprocess
import re
import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger('autoimprove.fixer.clawlite')

# Load paths from config
RESEARCH_DIR = Path(__file__).parent.parent
CONFIG_PATH = RESEARCH_DIR / "config.yaml"


def load_fix_config() -> Dict[str, Any]:
    """Load fix targets from config.yaml."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('fix_targets', {})
    return {}


def get_production_workspace() -> str:
    """Get production workspace path from config."""
    config = load_fix_config()
    return config.get('production', {}).get('workspace', '')


def get_container_name() -> str:
    """Get container name from config."""
    config = load_fix_config()
    return config.get('production', {}).get('container', '')


def get_dev_repo() -> str:
    """Get dev repo path from config."""
    config = load_fix_config()
    return config.get('dev', {}).get('repo', '')


def get_dev_templates() -> str:
    """Get dev templates path from config."""
    config = load_fix_config()
    return config.get('dev', {}).get('templates', '')


def apply_to_production(file_path: str, content: str) -> bool:
    """Apply fix to production instance via docker cp.
    
    Args:
        file_path: Relative path within workspace (e.g., "AGENTS.md")
        content: New file content
        
    Returns:
        True if successful
    """
    container_name = get_container_name()
    if not container_name:
        logger.error("Container name not configured")
        return False
    
    container_path = f"/workspace/{file_path}"
    
    try:
        # Write to temp file
        temp_path = f"/tmp/autoimprove_{file_path.replace('/', '_')}"
        Path(temp_path).write_text(content)
        
        # Copy to container
        result = subprocess.run(
            ["docker", "cp", temp_path, f"{container_name}:{container_path}"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            logger.info(f"Applied fix to production: {container_path}")
            return True
        else:
            logger.error(f"Failed to apply to production: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error applying to production: {e}")
        return False


def apply_to_dev(file_path: str, content: str, is_template: bool = True) -> bool:
    """Apply fix to dev repository.
    
    Args:
        file_path: Relative path (e.g., "AGENTS.md" or "src/agent.py")
        content: New file content
        is_template: If True, apply to templates/ dir, else to repo root
        
    Returns:
        True if successful
    """
    dev_repo = get_dev_repo()
    dev_templates = get_dev_templates()
    
    if not dev_repo:
        logger.error("Dev repo path not configured")
        return False
    
    if is_template and not file_path.startswith("src/"):
        full_path = Path(dev_templates) / file_path if dev_templates else Path(dev_repo) / "templates" / file_path
    else:
        full_path = Path(dev_repo) / file_path
    
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        logger.info(f"Applied fix to dev: {full_path}")
        return True
    except Exception as e:
        logger.error(f"Error applying to dev: {e}")
        return False


def add_section_to_agents_md(section_title: str, section_content: str) -> Dict[str, Any]:
    """Add a new section to AGENTS.md if not exists.
    
    Args:
        section_title: Title of section (e.g., "## ⚠️ Reminder Rules")
        section_content: Full section content including title
        
    Returns:
        Dict with success status and details
    """
    result = {"success": False, "production": False, "dev": False}
    
    container_name = get_container_name()
    if not container_name:
        logger.error("Container name not configured")
        return result
    
    try:
        # Read from production
        proc = subprocess.run(
            ["docker", "exec", container_name, "cat", "/workspace/AGENTS.md"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            logger.error(f"Failed to read production AGENTS.md")
            return result
        
        current_content = proc.stdout
        
        # Check if section already exists
        if section_title in current_content:
            logger.info(f"Section already exists: {section_title}")
            result["success"] = True
            result["already_exists"] = True
            return result
        
        # Find insertion point (after Anti-Hallucination Rules or at top)
        insertion_marker = "## Memory System"
        if insertion_marker in current_content:
            new_content = current_content.replace(
                insertion_marker,
                f"{section_content}\n\n{insertion_marker}"
            )
        else:
            # Add after first heading
            lines = current_content.split('\n')
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('# '):
                    insert_idx = i + 1
                    break
            lines.insert(insert_idx, f"\n{section_content}\n")
            new_content = '\n'.join(lines)
        
        # Apply to both production and dev
        result["production"] = apply_to_production("AGENTS.md", new_content)
        result["dev"] = apply_to_dev("AGENTS.md", new_content)
        result["success"] = result["production"] and result["dev"]
        
        return result
        
    except Exception as e:
        logger.error(f"Error adding section to AGENTS.md: {e}")
        return result


def update_agent_py_constant(constant_name: str, new_value: Any) -> Dict[str, Any]:
    """Update a constant in src/agent.py.
    
    Args:
        constant_name: Name of constant (e.g., "MAX_CONSECUTIVE_SAME_TOOL")
        new_value: New value for the constant
        
    Returns:
        Dict with success status
    """
    result = {"success": False, "dev": False}
    
    dev_repo = get_dev_repo()
    if not dev_repo:
        logger.error("Dev repo path not configured")
        return result
    
    agent_path = Path(dev_repo) / "src" / "agent.py"
    
    try:
        content = agent_path.read_text()
        
        # Find and replace the constant
        pattern = rf'({constant_name}\s*=\s*)(\d+|"[^"]*"|\'[^\']*\')'
        
        if not re.search(pattern, content):
            logger.warning(f"Constant not found: {constant_name}")
            return result
        
        new_content = re.sub(pattern, rf'\g<1>{new_value}', content)
        
        agent_path.write_text(new_content)
        result["dev"] = True
        result["success"] = True
        
        logger.info(f"Updated {constant_name} = {new_value}")
        return result
        
    except Exception as e:
        logger.error(f"Error updating agent.py: {e}")
        return result


def add_thinking_pattern(pattern: str) -> Dict[str, Any]:
    """Add a new thinking pattern to strip in agent.py.
    
    Args:
        pattern: Regex pattern to add
        
    Returns:
        Dict with success status
    """
    result = {"success": False, "dev": False}
    
    dev_repo = get_dev_repo()
    if not dev_repo:
        logger.error("Dev repo path not configured")
        return result
    
    agent_path = Path(dev_repo) / "src" / "agent.py"
    
    try:
        content = agent_path.read_text()
        
        # Find prose_thinking_patterns list
        pattern_match = re.search(
            r'(prose_thinking_patterns\s*=\s*\[[\s\S]*?)(\])',
            content
        )
        
        if not pattern_match:
            logger.warning("prose_thinking_patterns not found in agent.py")
            return result
        
        # Check if pattern already exists
        if pattern in content:
            logger.info(f"Pattern already exists: {pattern}")
            result["success"] = True
            result["already_exists"] = True
            return result
        
        # Add new pattern before closing bracket
        old_list = pattern_match.group(0)
        new_list = old_list.replace(']', f',\n        r\'{pattern}\',\n    ]')
        
        new_content = content.replace(old_list, new_list)
        agent_path.write_text(new_content)
        
        result["dev"] = True
        result["success"] = True
        
        logger.info(f"Added thinking pattern: {pattern}")
        return result
        
    except Exception as e:
        logger.error(f"Error adding thinking pattern: {e}")
        return result


def git_commit_and_push(message: str) -> bool:
    """Commit and push changes to dev repo.
    
    Args:
        message: Commit message
        
    Returns:
        True if successful
    """
    dev_repo = get_dev_repo()
    if not dev_repo:
        logger.error("Dev repo path not configured")
        return False
    
    try:
        # Stage all changes
        subprocess.run(
            ["git", "add", "."],
            cwd=dev_repo,
            check=True,
            capture_output=True,
        )
        
        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", f"autoimprove: {message}"],
            cwd=dev_repo,
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            if "nothing to commit" in result.stdout:
                logger.info("Nothing to commit")
                return True
            logger.error(f"Commit failed: {result.stderr}")
            return False
        
        # Push
        result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=dev_repo,
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            logger.info(f"Pushed: {message}")
            return True
        else:
            logger.error(f"Push failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Git error: {e}")
        return False


def fix_issue(issue_type: str, issue_details: Dict[str, Any]) -> Dict[str, Any]:
    """Apply fix for a specific issue type.
    
    Args:
        issue_type: Type of issue (e.g., "hallucination", "loop_behavior")
        issue_details: Details about the issue including context
        
    Returns:
        Dict with fix results
    """
    result = {
        "issue_type": issue_type,
        "fixed": False,
        "actions": [],
    }
    
    if issue_type == "loop_behavior":
        # Reduce MAX_CONSECUTIVE_SAME_TOOL
        fix_result = update_agent_py_constant("MAX_CONSECUTIVE_SAME_TOOL", 3)
        result["fixed"] = fix_result["success"]
        result["actions"].append("Reduced MAX_CONSECUTIVE_SAME_TOOL to 3")
        
    elif issue_type == "thinking_leak":
        # Add detected pattern to strip list
        pattern = issue_details.get("pattern", "")
        if pattern:
            fix_result = add_thinking_pattern(pattern)
            result["fixed"] = fix_result["success"]
            result["actions"].append(f"Added thinking pattern: {pattern}")
            
    elif issue_type in ("hallucination", "user_correction"):
        # These need manual review - add to backlog with context
        result["requires_review"] = True
        result["actions"].append("Added to backlog for Aisyah review")
        
    return result
