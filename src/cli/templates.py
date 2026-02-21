"""Template resolution and fetching."""

import os
import shutil
import tempfile
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

from . import get_default_namespace, get_templates_dir

logger = logging.getLogger("clawlite.cli.templates")


def resolve_template(template_ref: str) -> Tuple[str, str, bool]:
    """
    Resolve template reference to source location.
    
    Args:
        template_ref: Template reference (name, namespace/name, or path)
    
    Returns:
        (source, resolved_name, is_local)
        - source: GitHub URL or local path
        - resolved_name: Template name for display
        - is_local: True if local path
    
    Examples:
        "customer-service" → ("github.com/anvie/customer-service-clawlite-tmpl", "customer-service", False)
        "aisyah/cs" → ("github.com/aisyah/cs-clawlite-tmpl", "cs", False)
        "./my-template" → ("./my-template", "my-template", True)
    """
    # Local path (starts with . or /)
    if template_ref.startswith(("./", "../", "/")):
        path = os.path.abspath(template_ref)
        name = os.path.basename(path)
        return path, name, True
    
    # GitHub namespace/name
    if "/" in template_ref:
        namespace, name = template_ref.split("/", 1)
        repo = f"{name}-clawlite-tmpl"
        url = f"https://github.com/{namespace}/{repo}"
        return url, name, False
    
    # Default namespace
    namespace = get_default_namespace()
    repo = f"{template_ref}-clawlite-tmpl"
    url = f"https://github.com/{namespace}/{repo}"
    return url, template_ref, False


def fetch_template(template_ref: str, dest_dir: str) -> bool:
    """
    Fetch template from GitHub or local path to destination.
    
    Args:
        template_ref: Template reference
        dest_dir: Destination directory
    
    Returns:
        True if successful
    """
    source, name, is_local = resolve_template(template_ref)
    
    if is_local:
        return copy_local_template(source, dest_dir)
    else:
        return clone_github_template(source, dest_dir)


def copy_local_template(source: str, dest_dir: str) -> bool:
    """Copy local template to destination."""
    try:
        if not os.path.isdir(source):
            logger.error(f"Template not found: {source}")
            return False
        
        # Copy contents
        for item in os.listdir(source):
            s = os.path.join(source, item)
            d = os.path.join(dest_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)
        
        logger.info(f"Copied template from {source}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to copy template: {e}")
        return False


def clone_github_template(url: str, dest_dir: str) -> bool:
    """Clone GitHub template repository."""
    try:
        # Clone to temp directory first
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", url, tmp],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"Git clone failed: {result.stderr}")
                return False
            
            # Remove .git directory
            git_dir = os.path.join(tmp, ".git")
            if os.path.exists(git_dir):
                shutil.rmtree(git_dir)
            
            # Copy contents to dest
            for item in os.listdir(tmp):
                s = os.path.join(tmp, item)
                d = os.path.join(dest_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
        
        logger.info(f"Cloned template from {url}")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Git clone timed out")
        return False
    except Exception as e:
        logger.error(f"Failed to clone template: {e}")
        return False


def list_cached_templates() -> list[str]:
    """List locally cached templates."""
    templates_dir = get_templates_dir()
    if not os.path.exists(templates_dir):
        return []
    
    return [d for d in os.listdir(templates_dir) 
            if os.path.isdir(os.path.join(templates_dir, d))]
