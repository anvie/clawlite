"""ClawLite CLI - Instance and Template Management."""

import os

# Default paths
DEFAULT_INSTANCES_DIR = os.path.expanduser("~/.clawlite/instances")
DEFAULT_TEMPLATES_DIR = os.path.expanduser("~/.clawlite/templates")
DEFAULT_NAMESPACE = "anvie"

def get_instances_dir() -> str:
    """Get instances directory from env or default."""
    return os.environ.get("CLAWLITE_INSTANCES_DIR", DEFAULT_INSTANCES_DIR)

def get_templates_dir() -> str:
    """Get templates cache directory."""
    return os.environ.get("CLAWLITE_TEMPLATES_DIR", DEFAULT_TEMPLATES_DIR)

def get_default_namespace() -> str:
    """Get default GitHub namespace for templates."""
    return os.environ.get("CLAWLITE_TEMPLATE_NAMESPACE", DEFAULT_NAMESPACE)
