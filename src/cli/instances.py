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

# Default config template (all non-secret config)
CONFIG_TEMPLATE = """# ClawLite Configuration - {instance_name}
# Secrets (API keys, tokens) go in .env file

# LLM settings
llm:
  provider: openrouter
  model: google/gemini-2.0-flash-001
  # host: http://localhost:11434  # for ollama
  timeout: 60

# Access control
access:
  allowed_users: []
  admins: []

# Channel settings
channels:
  telegram:
    enabled: true
  whatsapp:
    enabled: false

# Agent behavior
agent:
  max_iterations: 10
  tool_timeout: 30
  total_timeout: 300

# Tool settings
tools:
  allowed: []

# Conversation persistence
conversation:
  record: true
  retention_days: 7

# API server
api:
  port: {api_port}

# Logging
logging:
  level: INFO
"""

# Default .env template (secrets only)
ENV_TEMPLATE = """# ClawLite Instance: {instance_name}
# Secrets only - all other config in config.yaml

# === API Keys ===
OPENROUTER_API_KEY=
# ANTHROPIC_API_KEY=
# ANTHROPIC_AUTH_TOKEN=

# === Bot Tokens ===
TELEGRAM_TOKEN=
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


def restart_instance(instance_name: str) -> bool:
    """Restart an instance (down + up to reload env/config)."""
    path = get_instance_path(instance_name)
    if not os.path.exists(path):
        logger.error(f"Instance '{instance_name}' not found")
        return False
    
    try:
        # Use down + up instead of restart to reload env vars
        result = subprocess.run(
            ["docker", "compose", "down"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            logger.error(f"Failed to stop: {result.stderr}")
            return False
        
        result = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            logger.info(f"Restarted instance '{instance_name}'")
            return True
        else:
            logger.error(f"Failed to start: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Failed to restart instance: {e}")
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


# === Skill Management ===

def get_instance_skills_path(instance_name: str) -> str:
    """Get the skills directory path for an instance."""
    return os.path.join(get_instance_path(instance_name), "skills")


def list_instance_skills(instance_name: str) -> list[dict]:
    """List skills installed in an instance."""
    skills_path = get_instance_skills_path(instance_name)
    
    if not os.path.exists(skills_path):
        return []
    
    skills = []
    for name in os.listdir(skills_path):
        skill_dir = os.path.join(skills_path, name)
        if not os.path.isdir(skill_dir):
            continue
        
        # Read schema.json for skill info
        schema_file = os.path.join(skill_dir, "schema.json")
        skill_info = {"name": name, "description": ""}
        
        if os.path.exists(schema_file):
            try:
                import json
                with open(schema_file) as f:
                    schema = json.load(f)
                    skill_info["description"] = schema.get("description", "")
                    skill_info["tool_name"] = schema.get("name", name)
            except Exception:
                pass
        
        skills.append(skill_info)
    
    return skills


def install_skill(instance_name: str, source: str) -> bool:
    """
    Install a skill into an instance.
    
    Args:
        instance_name: Target instance name
        source: Skill source - can be:
            - Local path (./my-skill or /absolute/path)
            - GitHub repo (user/repo-name)
    
    Returns:
        True if installed successfully
    """
    import shutil
    import tempfile
    
    instance_path = get_instance_path(instance_name)
    if not os.path.exists(instance_path):
        logger.error(f"Instance '{instance_name}' not found")
        return False
    
    skills_path = get_instance_skills_path(instance_name)
    os.makedirs(skills_path, exist_ok=True)
    
    # Determine source type
    if source.startswith("./") or source.startswith("/") or os.path.exists(source):
        # Local path
        source_path = os.path.abspath(os.path.expanduser(source))
        if not os.path.exists(source_path):
            logger.error(f"Source path not found: {source_path}")
            return False
        
        skill_name = os.path.basename(source_path.rstrip("/"))
        dest_path = os.path.join(skills_path, skill_name)
        
        if os.path.exists(dest_path):
            logger.warning(f"Skill '{skill_name}' already exists, replacing...")
            shutil.rmtree(dest_path)
        
        shutil.copytree(source_path, dest_path)
        logger.info(f"Installed skill '{skill_name}' from local path")
        
    else:
        # GitHub repo
        repo = source
        if "/" not in repo:
            logger.error(f"Invalid GitHub repo format. Use: user/repo")
            return False
        
        # Clone to temp dir first
        with tempfile.TemporaryDirectory() as tmp_dir:
            clone_url = f"https://github.com/{repo}.git"
            logger.info(f"Cloning {clone_url}...")
            
            try:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", clone_url, tmp_dir],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.error(f"Git clone failed: {result.stderr}")
                    return False
            except Exception as e:
                logger.error(f"Git clone failed: {e}")
                return False
            
            # Determine skill name from repo or schema
            skill_name = repo.split("/")[-1]
            # Remove common suffixes
            for suffix in ["-clawlite-skill", "-skill", "-clawlite"]:
                if skill_name.endswith(suffix):
                    skill_name = skill_name[:-len(suffix)]
                    break
            
            # Check if it's a skill directory (has schema.json or main.py)
            if not (os.path.exists(os.path.join(tmp_dir, "schema.json")) or 
                    os.path.exists(os.path.join(tmp_dir, "main.py"))):
                logger.error(f"Invalid skill: missing schema.json or main.py")
                return False
            
            dest_path = os.path.join(skills_path, skill_name)
            
            if os.path.exists(dest_path):
                logger.warning(f"Skill '{skill_name}' already exists, replacing...")
                shutil.rmtree(dest_path)
            
            # Copy without .git
            shutil.copytree(tmp_dir, dest_path, ignore=shutil.ignore_patterns('.git'))
            
            # Fix permissions (git clone creates dirs with restricted perms)
            os.chmod(dest_path, 0o755)
            for root, dirs, files in os.walk(dest_path):
                for d in dirs:
                    os.chmod(os.path.join(root, d), 0o755)
                for f in files:
                    os.chmod(os.path.join(root, f), 0o644)
            
            logger.info(f"Installed skill '{skill_name}' from GitHub")
    
    # Check for required env vars in schema.json
    schema_file = os.path.join(dest_path, "schema.json")
    if os.path.exists(schema_file):
        try:
            import json
            with open(schema_file) as f:
                schema = json.load(f)
            
            env_vars = schema.get("env", {})
            if env_vars:
                configured = configure_skill_env(instance_name, env_vars)
                if not configured:
                    print(f"⚠️  Skill installed but not configured. Add required env vars to .env manually.")
        except Exception as e:
            logger.warning(f"Failed to read skill schema: {e}")
    
    print(f"✅ Skill installed. Restart instance to load: ./clawlite instances restart {instance_name}")
    return True


def configure_skill_env(instance_name: str, env_vars: dict) -> bool:
    """
    Prompt user for required environment variables and add to instance .env.
    
    Args:
        instance_name: Instance name
        env_vars: Dict of env var definitions from schema.json
            {
                "VAR_NAME": {
                    "description": "What this var is for",
                    "required": true/false,
                    "secret": true/false,
                    "default": "optional default value"
                }
            }
    
    Returns:
        True if all required vars configured
    """
    import getpass
    
    instance_path = get_instance_path(instance_name)
    env_file = os.path.join(instance_path, ".env")
    
    # Read existing env vars
    existing_vars = {}
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    existing_vars[key.strip()] = value.strip()
    
    # Determine which vars need to be configured
    vars_to_configure = []
    for var_name, var_def in env_vars.items():
        if var_name in existing_vars and existing_vars[var_name]:
            continue  # Already configured
        vars_to_configure.append((var_name, var_def))
    
    if not vars_to_configure:
        logger.info("All required env vars already configured")
        return True
    
    print(f"\n📋 Skill requires configuration:\n")
    
    new_vars = {}
    for var_name, var_def in vars_to_configure:
        description = var_def.get("description", var_name)
        required = var_def.get("required", False)
        secret = var_def.get("secret", False)
        default = var_def.get("default", "")
        
        prompt = f"  {var_name}"
        if description:
            prompt += f" ({description})"
        if default:
            prompt += f" [{default}]"
        if not required:
            prompt += " (optional)"
        prompt += ": "
        
        if secret:
            value = getpass.getpass(prompt)
        else:
            value = input(prompt)
        
        if not value and default:
            value = default
        
        if not value and required:
            print(f"    ⚠️  {var_name} is required but not provided")
            continue
        
        if value:
            new_vars[var_name] = value
    
    # Append to .env file
    if new_vars:
        with open(env_file, "a") as f:
            f.write(f"\n# Skill configuration\n")
            for var_name, value in new_vars.items():
                f.write(f"{var_name}={value}\n")
        print(f"\n✅ Configuration saved to .env")
    
    # Check if all required vars are now configured
    all_configured = True
    for var_name, var_def in env_vars.items():
        if var_def.get("required", False):
            if var_name not in existing_vars and var_name not in new_vars:
                all_configured = False
                break
    
    return all_configured


def remove_skill(instance_name: str, skill_name: str) -> bool:
    """Remove a skill from an instance."""
    import shutil
    
    skills_path = get_instance_skills_path(instance_name)
    skill_path = os.path.join(skills_path, skill_name)
    
    if not os.path.exists(skill_path):
        logger.error(f"Skill '{skill_name}' not found in instance '{instance_name}'")
        return False
    
    try:
        shutil.rmtree(skill_path)
        logger.info(f"Removed skill '{skill_name}' from instance '{instance_name}'")
        print(f"✅ Skill removed. Restart instance to apply: ./clawlite instances restart {instance_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to remove skill: {e}")
        return False
