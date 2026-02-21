"""Instance management for ClawLite."""

import os
import yaml
import subprocess
import logging
from pathlib import Path
from typing import Optional

from . import get_instances_dir
from .templates import resolve_template, fetch_template

logger = logging.getLogger("clawlite.cli.instances")

# Shared image name
CLAWLITE_IMAGE = "clawlite:latest"

# Docker compose template
DOCKER_COMPOSE_TEMPLATE = """version: '3.8'

services:
  clawlite:
    image: clawlite:latest
    container_name: clawlite-{instance_name}
    restart: unless-stopped
    
    ports:
      - "${{API_PORT:-{api_port}}}:8080"
    
    env_file:
      - .env
    
    volumes:
      - ./workspace:/workspace:rw
      - ./config.yaml:/app/config.yaml:ro
      - ./skills:/app/skills:ro
      - ./owner:/app/.owner:rw
    
    tmpfs:
      - /tmp:size=100m,mode=1777
"""


def get_clawlite_source() -> str:
    """Get path to ClawLite source directory."""
    candidates = [
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        os.path.expanduser("~/dev/clawlite"),
        os.environ.get("CLAWLITE_SOURCE", ""),
    ]
    
    for path in candidates:
        if path and os.path.exists(os.path.join(path, "Dockerfile")):
            return os.path.abspath(path)
    
    return ""


def ensure_clawlite_image() -> bool:
    """Build clawlite:latest image if not exists."""
    # Check if image exists
    result = subprocess.run(
        ["docker", "image", "inspect", CLAWLITE_IMAGE],
        capture_output=True,
        timeout=10
    )
    
    if result.returncode == 0:
        logger.info(f"Image {CLAWLITE_IMAGE} already exists")
        return True
    
    # Build image
    source = get_clawlite_source()
    if not source:
        logger.error("ClawLite source not found. Set CLAWLITE_SOURCE env var.")
        return False
    
    logger.info(f"Building {CLAWLITE_IMAGE} from {source}...")
    print(f"🔨 Building {CLAWLITE_IMAGE}...")
    
    result = subprocess.run(
        ["docker", "build", "-t", CLAWLITE_IMAGE, source],
        timeout=300
    )
    
    if result.returncode == 0:
        logger.info(f"Built {CLAWLITE_IMAGE} successfully")
        print(f"✅ Built {CLAWLITE_IMAGE}")
        return True
    else:
        logger.error(f"Failed to build {CLAWLITE_IMAGE}")
        return False

# Default config template
CONFIG_TEMPLATE = """# ClawLite Configuration - {instance_name}

access:
  allowed_users: []
  admins: []

llm:
  provider: openrouter
  timeout: 60

agent:
  max_iterations: 10
  tool_timeout: 30
  total_timeout: 300

tools:
  allowed: []

channels:
  telegram:
    enabled: true
  whatsapp:
    enabled: false

conversation:
  record: true
  retention_days: 7

logging:
  level: INFO
"""

# Default .env template
ENV_TEMPLATE = """# ClawLite Instance: {instance_name}
# Generated from template: {template_name}

# === LLM Provider ===
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-api-key-here
OPENROUTER_MODEL=google/gemini-2.0-flash-001

# === Telegram ===
TELEGRAM_TOKEN=your-telegram-bot-token
ALLOWED_USERS=

# === API Server ===
API_PORT={api_port}

# === Workspace ===
WORKSPACE_PATH=/workspace
"""


def get_instance_path(instance_name: str) -> str:
    """Get full path to instance directory."""
    return os.path.join(get_instances_dir(), instance_name)


def instance_exists(instance_name: str) -> bool:
    """Check if instance already exists."""
    return os.path.exists(get_instance_path(instance_name))


def list_instances() -> list[dict]:
    """List all instances with their status."""
    instances_dir = get_instances_dir()
    if not os.path.exists(instances_dir):
        return []
    
    instances = []
    for name in os.listdir(instances_dir):
        path = os.path.join(instances_dir, name)
        if not os.path.isdir(path):
            continue
        
        # Check if it's a valid instance
        compose_file = os.path.join(path, "docker-compose.yml")
        if not os.path.exists(compose_file):
            continue
        
        # Get container status
        status = get_instance_status(name)
        
        instances.append({
            "name": name,
            "path": path,
            "status": status,
        })
    
    return instances


def get_instance_status(instance_name: str) -> str:
    """Get container status for instance."""
    container_name = f"clawlite-{instance_name}"
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "not created"
    except:
        return "unknown"


def find_available_port(start_port: int = 8081) -> int:
    """Find an available port starting from start_port."""
    import socket
    
    port = start_port
    while port < 65535:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            port += 1
    
    return start_port  # fallback


def load_template_config(instance_path: str) -> dict:
    """Load template.yaml if exists."""
    template_file = os.path.join(instance_path, "template.yaml")
    if os.path.exists(template_file):
        try:
            with open(template_file) as f:
                return yaml.safe_load(f) or {}
        except:
            pass
    return {}


def prompt_template_variables(template_config: dict) -> dict:
    """Prompt user for template variables."""
    variables = template_config.get("variables", [])
    values = {}
    
    if not variables:
        return values
    
    print("\n📝 Template configuration:")
    print("-" * 40)
    
    for var in variables:
        name = var.get("name", "")
        prompt_text = var.get("prompt", name)
        default = var.get("default", "")
        required = var.get("required", False)
        
        if default:
            prompt_text = f"{prompt_text} [{default}]"
        
        while True:
            try:
                value = input(f"   {prompt_text}: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n   Cancelled.")
                return None
            
            if not value and default:
                value = default
            
            if not value and required:
                print(f"   ⚠️  This field is required.")
                continue
            
            values[name] = value
            break
    
    print("-" * 40)
    return values


def apply_template_variables(instance_path: str, variables: dict):
    """Replace placeholders in workspace files with variable values."""
    if not variables:
        return
    
    workspace_path = os.path.join(instance_path, "workspace")
    
    # Files to process
    files_to_process = []
    for root, dirs, files in os.walk(workspace_path):
        for f in files:
            if f.endswith((".md", ".txt", ".yaml", ".yml")):
                files_to_process.append(os.path.join(root, f))
    
    # Also process .env and .env.example
    for env_file in [".env", ".env.example"]:
        env_path = os.path.join(instance_path, env_file)
        if os.path.exists(env_path):
            files_to_process.append(env_path)
    
    # Replace placeholders
    for filepath in files_to_process:
        try:
            with open(filepath, "r") as f:
                content = f.read()
            
            modified = False
            for name, value in variables.items():
                # Replace {{VARIABLE_NAME}} and [VARIABLE_NAME] patterns
                for pattern in [f"{{{{{name}}}}}", f"[{name}]", f"${{{name}}}"]:
                    if pattern in content:
                        content = content.replace(pattern, value)
                        modified = True
            
            if modified:
                with open(filepath, "w") as f:
                    f.write(content)
                logger.debug(f"Updated variables in {filepath}")
        except Exception as e:
            logger.warning(f"Failed to process {filepath}: {e}")


def create_instance(
    template_ref: str,
    instance_name: str,
    api_port: Optional[int] = None,
    interactive: bool = True,
) -> bool:
    """
    Create a new ClawLite instance from template.
    
    Args:
        template_ref: Template reference (name, namespace/name, or path)
        instance_name: Name for the new instance
        api_port: API port (auto-assigned if None)
        interactive: Whether to prompt for template variables
    
    Returns:
        True if successful
    """
    # Check if instance already exists
    if instance_exists(instance_name):
        logger.error(f"Instance '{instance_name}' already exists")
        return False
    
    # Resolve template
    source, template_name, is_local = resolve_template(template_ref)
    logger.info(f"Resolving template: {template_ref} → {source}")
    
    # Create instance directory
    instance_path = get_instance_path(instance_name)
    os.makedirs(instance_path, exist_ok=True)
    
    # Fetch template first (may include workspace, skills, etc.)
    if not fetch_template(template_ref, instance_path):
        # Cleanup on failure
        import shutil
        shutil.rmtree(instance_path, ignore_errors=True)
        return False
    
    # Load template config and prompt for variables
    template_config = load_template_config(instance_path)
    
    if interactive and template_config.get("variables"):
        variables = prompt_template_variables(template_config)
        if variables is None:  # Cancelled
            import shutil
            shutil.rmtree(instance_path, ignore_errors=True)
            return False
        
        # Apply variables to files
        apply_template_variables(instance_path, variables)
    
    # Create subdirectories if not from template
    workspace_path = os.path.join(instance_path, "workspace")
    skills_path = os.path.join(instance_path, "skills")
    os.makedirs(workspace_path, exist_ok=True)
    os.makedirs(skills_path, exist_ok=True)
    
    # Find available port if not specified
    if api_port is None:
        api_port = find_available_port()
    
    # Ensure clawlite:latest image exists
    if not ensure_clawlite_image():
        import shutil
        shutil.rmtree(instance_path, ignore_errors=True)
        return False
    
    # Generate docker-compose.yml if not from template
    compose_file = os.path.join(instance_path, "docker-compose.yml")
    if not os.path.exists(compose_file):
        with open(compose_file, "w") as f:
            f.write(DOCKER_COMPOSE_TEMPLATE.format(
                instance_name=instance_name,
                api_port=api_port,
            ))
    
    # Generate config.yaml if not from template
    config_file = os.path.join(instance_path, "config.yaml")
    if not os.path.exists(config_file):
        with open(config_file, "w") as f:
            f.write(CONFIG_TEMPLATE.format(instance_name=instance_name))
    
    # Generate .env if not from template
    env_file = os.path.join(instance_path, ".env")
    env_example = os.path.join(instance_path, ".env.example")
    if not os.path.exists(env_file):
        content = ENV_TEMPLATE.format(
            instance_name=instance_name,
            template_name=template_name,
            api_port=api_port,
        )
        with open(env_file, "w") as f:
            f.write(content)
        # Also create .env.example
        with open(env_example, "w") as f:
            f.write(content)
    
    # Create default workspace files if not from template
    soul_file = os.path.join(workspace_path, "SOUL.md")
    if not os.path.exists(soul_file):
        with open(soul_file, "w") as f:
            f.write(f"# SOUL.md - {instance_name}\n\nDefine your agent's personality here.\n")
    
    agents_file = os.path.join(workspace_path, "AGENTS.md")
    if not os.path.exists(agents_file):
        with open(agents_file, "w") as f:
            f.write(f"# AGENTS.md - {instance_name}\n\nDefine agent rules and behaviors here.\n")
    
    tools_file = os.path.join(workspace_path, "TOOLS.md")
    if not os.path.exists(tools_file):
        with open(tools_file, "w") as f:
            f.write(f"# TOOLS.md - {instance_name}\n\nDocument available tools here.\n")
    
    logger.info(f"Created instance '{instance_name}' at {instance_path}")
    logger.info(f"API port: {api_port}")
    
    return True


def start_instance(instance_name: str) -> bool:
    """Start an instance."""
    path = get_instance_path(instance_name)
    if not os.path.exists(path):
        logger.error(f"Instance '{instance_name}' not found")
        return False
    
    try:
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            logger.info(f"Started instance '{instance_name}'")
            return True
        else:
            logger.error(f"Failed to start: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Failed to start instance: {e}")
        return False


def stop_instance(instance_name: str) -> bool:
    """Stop an instance."""
    path = get_instance_path(instance_name)
    if not os.path.exists(path):
        logger.error(f"Instance '{instance_name}' not found")
        return False
    
    try:
        result = subprocess.run(
            ["docker", "compose", "down"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            logger.info(f"Stopped instance '{instance_name}'")
            return True
        else:
            logger.error(f"Failed to stop: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Failed to stop instance: {e}")
        return False


def remove_instance(instance_name: str, force: bool = False) -> bool:
    """Remove an instance."""
    import shutil
    
    path = get_instance_path(instance_name)
    if not os.path.exists(path):
        logger.error(f"Instance '{instance_name}' not found")
        return False
    
    # Stop first if running
    status = get_instance_status(instance_name)
    if status == "running":
        if not force:
            logger.error(f"Instance is running. Use --force to remove anyway.")
            return False
        stop_instance(instance_name)
    
    try:
        shutil.rmtree(path)
        logger.info(f"Removed instance '{instance_name}'")
        return True
    except Exception as e:
        logger.error(f"Failed to remove instance: {e}")
        return False
