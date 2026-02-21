#!/usr/bin/env python3
"""ClawLite CLI - Main Entry Point."""

import argparse
import sys
import logging

from . import get_instances_dir, get_default_namespace
from .instances import (
    create_instance,
    list_instances,
    start_instance,
    stop_instance,
    remove_instance,
    get_instance_path,
)
from .templates import resolve_template, list_cached_templates

# Configure logging
logging.basicConfig(
    format="%(message)s",
    level=logging.INFO
)
logger = logging.getLogger("clawlite.cli")


def cmd_new_instance(args):
    """Handle new-instance command."""
    template = args.template
    instance_name = args.name
    
    # Resolve template for display
    source, template_name, is_local = resolve_template(template)
    
    print(f"🦎 Creating new ClawLite instance")
    print(f"   Template: {template} → {source}")
    print(f"   Instance: {instance_name}")
    print(f"   Location: {get_instance_path(instance_name)}")
    print()
    
    if create_instance(template, instance_name, api_port=args.port):
        print()
        print(f"✅ Instance '{instance_name}' created successfully!")
        print()
        print(f"Next steps:")
        print(f"  1. Edit configuration:")
        print(f"     cd {get_instance_path(instance_name)}")
        print(f"     nano .env  # Add your API keys")
        print()
        print(f"  2. Customize your agent:")
        print(f"     nano workspace/SOUL.md")
        print(f"     nano workspace/AGENTS.md")
        print()
        print(f"  3. Start the instance:")
        print(f"     clawlite instances start {instance_name}")
        print()
        return 0
    else:
        print(f"❌ Failed to create instance")
        return 1


def cmd_instances_list(args):
    """Handle instances list command."""
    instances = list_instances()
    
    if not instances:
        print("No instances found.")
        print(f"Create one with: clawlite instances new <template> <name>")
        return 0
    
    print(f"{'Name':<20} {'Status':<12} {'Path'}")
    print("-" * 60)
    for inst in instances:
        status_icon = "🟢" if inst["status"] == "running" else "⚪"
        print(f"{inst['name']:<20} {status_icon} {inst['status']:<10} {inst['path']}")
    
    return 0


def cmd_instances_start(args):
    """Handle instances start command."""
    if start_instance(args.name):
        print(f"✅ Started instance '{args.name}'")
        return 0
    else:
        print(f"❌ Failed to start instance '{args.name}'")
        return 1


def cmd_instances_stop(args):
    """Handle instances stop command."""
    if stop_instance(args.name):
        print(f"✅ Stopped instance '{args.name}'")
        return 0
    else:
        print(f"❌ Failed to stop instance '{args.name}'")
        return 1


def cmd_instances_remove(args):
    """Handle instances remove command."""
    if remove_instance(args.name, force=args.force):
        print(f"✅ Removed instance '{args.name}'")
        return 0
    else:
        print(f"❌ Failed to remove instance '{args.name}'")
        return 1


def cmd_instances_path(args):
    """Handle instances path command."""
    path = get_instance_path(args.name)
    print(path)
    return 0


def cmd_templates_list(args):
    """Handle templates list command."""
    templates = list_cached_templates()
    
    print(f"Default namespace: {get_default_namespace()}")
    print()
    
    if templates:
        print("Cached templates:")
        for t in templates:
            print(f"  - {t}")
    else:
        print("No cached templates.")
    
    print()
    print("Usage:")
    print("  clawlite instances new <template> <name>")
    print()
    print("Examples:")
    print("  clawlite instances new customer-service my-cs-agent")
    print("  clawlite instances new aisyah/sales sales-bot")
    print("  clawlite instances new ./my-template custom-agent")
    
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="clawlite",
        description="ClawLite - Lightweight Agentic AI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # new-instance command
    new_parser = subparsers.add_parser(
        "new-instance",
        help="Create a new ClawLite instance from template"
    )
    new_parser.add_argument("template", help="Template reference (name, namespace/name, or path)")
    new_parser.add_argument("name", help="Instance name")
    new_parser.add_argument("--port", type=int, help="API port (auto-assigned if not specified)")
    new_parser.set_defaults(func=cmd_new_instance)
    
    # instances command
    instances_parser = subparsers.add_parser("instances", help="Manage instances")
    instances_sub = instances_parser.add_subparsers(dest="instances_cmd")
    
    # instances list
    list_parser = instances_sub.add_parser("list", help="List all instances")
    list_parser.set_defaults(func=cmd_instances_list)
    
    # instances start
    start_parser = instances_sub.add_parser("start", help="Start an instance")
    start_parser.add_argument("name", help="Instance name")
    start_parser.set_defaults(func=cmd_instances_start)
    
    # instances stop
    stop_parser = instances_sub.add_parser("stop", help="Stop an instance")
    stop_parser.add_argument("name", help="Instance name")
    stop_parser.set_defaults(func=cmd_instances_stop)
    
    # instances remove
    remove_parser = instances_sub.add_parser("remove", help="Remove an instance")
    remove_parser.add_argument("name", help="Instance name")
    remove_parser.add_argument("--force", "-f", action="store_true", help="Force remove even if running")
    remove_parser.set_defaults(func=cmd_instances_remove)
    
    # instances path
    path_parser = instances_sub.add_parser("path", help="Get instance path")
    path_parser.add_argument("name", help="Instance name")
    path_parser.set_defaults(func=cmd_instances_path)
    
    # templates command
    templates_parser = subparsers.add_parser("templates", help="Manage templates")
    templates_sub = templates_parser.add_subparsers(dest="templates_cmd")
    
    # templates list
    tlist_parser = templates_sub.add_parser("list", help="List templates")
    tlist_parser.set_defaults(func=cmd_templates_list)
    
    # Parse args
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
