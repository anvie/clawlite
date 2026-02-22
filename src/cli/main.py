#!/usr/bin/env python3
"""ClawLite CLI - Main Entry Point."""

import argparse
import asyncio
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
from .auth import setup_auth_parser

# Configure logging
logging.basicConfig(
    format="%(message)s",
    level=logging.INFO
)
logger = logging.getLogger("clawlite.cli")


# =============================================================================
# run command
# =============================================================================

def cmd_run(args):
    """Handle run command - start the bot."""
    from main import main as run_main
    asyncio.run(run_main())
    return 0


# =============================================================================
# send command
# =============================================================================

def cmd_send(args):
    """Handle send command - send a message to a user."""
    from main import send_message
    success = asyncio.run(send_message(args.user, args.message))
    return 0 if success else 1


# =============================================================================
# skill command
# =============================================================================

def cmd_skill_new(args):
    """Handle skill new command."""
    from .skill_manager import create_skill
    return create_skill(args.name, args.description)


def cmd_skill_list(args):
    """Handle skill list command."""
    from .skill_manager import list_skills
    return list_skills()


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


def cmd_instances_restart(args):
    """Handle instances restart command."""
    from .instances import restart_instance
    
    if restart_instance(args.name):
        print(f"✅ Restarted instance '{args.name}'")
        return 0
    else:
        print(f"❌ Failed to restart instance '{args.name}'")
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


def cmd_instances_skill_list(args):
    """Handle instances skill list command."""
    from .instances import list_instance_skills, get_instance_path
    import os
    
    instance_path = get_instance_path(args.instance)
    if not os.path.exists(instance_path):
        print(f"❌ Instance '{args.instance}' not found")
        return 1
    
    skills = list_instance_skills(args.instance)
    
    if not skills:
        print(f"No skills installed in '{args.instance}'")
        return 0
    
    print(f"Skills in '{args.instance}':")
    print()
    for skill in skills:
        tool_name = skill.get("tool_name", skill["name"])
        desc = skill.get("description", "No description")
        print(f"  📦 {skill['name']}")
        print(f"     Tool: {tool_name}")
        print(f"     {desc}")
        print()
    
    return 0


def cmd_instances_skill_install(args):
    """Handle instances skill install command."""
    from .instances import install_skill
    
    success = install_skill(args.instance, args.source)
    return 0 if success else 1


def cmd_instances_skill_remove(args):
    """Handle instances skill remove command."""
    from .instances import remove_skill
    
    success = remove_skill(args.instance, args.skill_name)
    return 0 if success else 1


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
    
    # run command
    run_parser = subparsers.add_parser("run", help="Start the bot")
    run_parser.set_defaults(func=cmd_run)
    
    # send command
    send_parser = subparsers.add_parser("send", help="Send a message to a user")
    send_parser.add_argument("-u", "--user", required=True, help="User ID (e.g., tg_123456)")
    send_parser.add_argument("-m", "--message", required=True, help="Message to send")
    send_parser.set_defaults(func=cmd_send)
    
    # skill command
    skill_parser = subparsers.add_parser("skill", help="Manage skills")
    skill_sub = skill_parser.add_subparsers(dest="skill_cmd")
    
    skill_new = skill_sub.add_parser("new", help="Create a new skill")
    skill_new.add_argument("name", help="Skill name")
    skill_new.add_argument("-d", "--description", help="Skill description")
    skill_new.set_defaults(func=cmd_skill_new)
    
    skill_list = skill_sub.add_parser("list", help="List installed skills")
    skill_list.set_defaults(func=cmd_skill_list)
    
    # instances command
    instances_parser = subparsers.add_parser("instances", help="Manage instances")
    instances_sub = instances_parser.add_subparsers(dest="instances_cmd")
    
    # instances new
    inst_new = instances_sub.add_parser("new", help="Create a new instance from template")
    inst_new.add_argument("template", help="Template reference (name, namespace/name, or path)")
    inst_new.add_argument("name", help="Instance name")
    inst_new.add_argument("--port", type=int, help="API port (auto-assigned if not specified)")
    inst_new.set_defaults(func=cmd_new_instance)
    
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
    
    # instances restart
    restart_parser = instances_sub.add_parser("restart", help="Restart an instance")
    restart_parser.add_argument("name", help="Instance name")
    restart_parser.set_defaults(func=cmd_instances_restart)
    
    # instances remove
    remove_parser = instances_sub.add_parser("remove", help="Remove an instance")
    remove_parser.add_argument("name", help="Instance name")
    remove_parser.add_argument("--force", "-f", action="store_true", help="Force remove even if running")
    remove_parser.set_defaults(func=cmd_instances_remove)
    
    # instances path
    path_parser = instances_sub.add_parser("path", help="Get instance path")
    path_parser.add_argument("name", help="Instance name")
    path_parser.set_defaults(func=cmd_instances_path)
    
    # instances skill subcommand
    inst_skill = instances_sub.add_parser("skill", help="Manage instance skills")
    inst_skill_sub = inst_skill.add_subparsers(dest="skill_action")
    
    inst_skill_list = inst_skill_sub.add_parser("list", help="List installed skills")
    inst_skill_list.add_argument("instance", help="Instance name")
    inst_skill_list.set_defaults(func=cmd_instances_skill_list)
    
    inst_skill_install = inst_skill_sub.add_parser("install", help="Install a skill")
    inst_skill_install.add_argument("instance", help="Instance name")
    inst_skill_install.add_argument("source", help="Skill source (local path or github user/repo)")
    inst_skill_install.set_defaults(func=cmd_instances_skill_install)
    
    inst_skill_remove = inst_skill_sub.add_parser("remove", help="Remove a skill")
    inst_skill_remove.add_argument("instance", help="Instance name")
    inst_skill_remove.add_argument("skill_name", help="Skill name to remove")
    inst_skill_remove.set_defaults(func=cmd_instances_skill_remove)
    
    # templates command
    templates_parser = subparsers.add_parser("templates", help="Manage templates")
    templates_sub = templates_parser.add_subparsers(dest="templates_cmd")
    
    # templates list
    tlist_parser = templates_sub.add_parser("list", help="List templates")
    tlist_parser.set_defaults(func=cmd_templates_list)
    
    # auth command
    setup_auth_parser(subparsers)
    
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
