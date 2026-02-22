#!/usr/bin/env python3
"""
ClawLite - Main Entry Point
Unified entry point for all messaging channels
"""

import os
import sys
import asyncio
import signal
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("clawlite")

# Reduce noise from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("neonize").setLevel(logging.WARNING)


# Global channel registry for API access
_active_channels: list = []


async def send_to_user(user_id: str, message: str) -> bool:
    """Send a message to a user via their channel (used by API server)."""
    # Parse channel from user_id prefix
    if user_id.startswith("tg_"):
        channel_name = "telegram"
    elif user_id.startswith("wa_"):
        channel_name = "whatsapp"
    else:
        channel_name = "telegram"
    
    # Find matching channel
    for channel in _active_channels:
        if channel.name == channel_name:
            try:
                await channel.send_message(user_id, message)
                logger.info(f"Message sent to {user_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to send to {user_id}: {e}")
                return False
    
    logger.error(f"No active channel for {channel_name}")
    return False


async def run_channels():
    """Run all enabled channels."""
    global _active_channels
    
    from .channels import get_enabled_channels, create_channel, get_available_channels
    from .agent import run_agent
    from .api import APIServer
    from .config import get as config_get
    
    enabled = get_enabled_channels()
    available = get_available_channels()
    
    logger.info(f"📋 Available channels: {', '.join(available)}")
    logger.info(f"✅ Enabled channels: {', '.join(enabled)}")
    
    # Filter to only available channels
    channels_to_start = [c for c in enabled if c in available]
    
    if not channels_to_start:
        logger.error("❌ No channels available to start!")
        logger.error(f"   Requested: {enabled}")
        logger.error(f"   Available: {available}")
        return
    
    # Agent callback wrapper
    conversations: dict[str, list[dict]] = {}
    
    async def agent_callback(user_id: str, message: str, images: list[str] = None, status_callback=None):
        """Process message through agent."""
        if user_id not in conversations:
            conversations[user_id] = []
        
        response, new_history = await run_agent(
            message,
            conversations[user_id],
            user_id=user_id,
            status_callback=status_callback or (lambda x: None),
            images=images,
        )
        
        conversations[user_id] = new_history
        return response
    
    # Create channel instances
    active_channels = []
    for name in channels_to_start:
        try:
            channel = create_channel(name, agent_callback)
            active_channels.append(channel)
            logger.info(f"📱 Created {name} channel")
        except Exception as e:
            logger.error(f"❌ Failed to create {name} channel: {e}")
    
    if not active_channels:
        logger.error("❌ No channels could be created!")
        return
    
    # Store globally for API access
    _active_channels = active_channels
    
    # Prompt callback for API (runs agent and returns response)
    async def prompt_and_respond(user_id: str, prompt: str) -> str:
        """Run agent with prompt and return response."""
        if user_id not in conversations:
            conversations[user_id] = []
        
        result = await run_agent(
            prompt,
            conversations[user_id],
            user_id=user_id,
        )
        
        conversations[user_id] = result.history
        return result.response
    
    # Setup API server
    api_port = int(os.getenv("API_PORT", config_get("api.port", 8080)))
    api_server = APIServer(send_to_user, prompt_callback=prompt_and_respond, port=api_port)
    
    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler():
        logger.info("🛑 Shutdown signal received...")
        shutdown_event.set()
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    # Start API server
    await api_server.start()
    
    # Start all channels
    start_tasks = []
    for channel in active_channels:
        start_tasks.append(asyncio.create_task(channel.start()))
    
    # Print startup info
    print_startup_info(api_port)
    
    try:
        # Wait for channels to start
        results = await asyncio.gather(*start_tasks, return_exceptions=True)
        
        # Log any errors from channel starts
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ Channel {active_channels[i].name} failed to start: {result}")
        
        # Keep running until shutdown
        logger.info("🚀 All channels started! Waiting for messages...")
        await shutdown_event.wait()
        
    except KeyboardInterrupt:
        logger.info("🛑 Keyboard interrupt received...")
    finally:
        # Stop API server
        await api_server.stop()
        
        # Stop all channels
        logger.info("🔄 Stopping channels...")
        stop_tasks = [channel.stop() for channel in active_channels]
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        logger.info("✅ All channels stopped")


def print_startup_info(api_port: int = 8080):
    """Print startup information."""
    llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    
    print("\n" + "=" * 50)
    print("🦎 ClawLite - Lightweight Agentic AI")
    print("=" * 50)
    
    if llm_provider == "anthropic":
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        print(f"   Provider: Anthropic")
        print(f"   Model: {model}")
    elif llm_provider == "openrouter":
        model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        print(f"   Provider: OpenRouter")
        print(f"   Model: {model}")
    else:
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        print(f"   Provider: Ollama")
        print(f"   Model: {ollama_model}")
        print(f"   Host: {ollama_host}")
    
    print(f"   Workspace: {os.getenv('WORKSPACE_PATH', '/workspace')}")
    print(f"   API: http://127.0.0.1:{api_port}")
    print("=" * 50 + "\n")


async def send_message(user_id: str, message: str) -> bool:
    """Send a message to a user via their channel."""
    import httpx
    
    # Parse channel from user_id prefix
    if user_id.startswith("tg_"):
        channel = "telegram"
        raw_id = user_id[3:]
    elif user_id.startswith("wa_"):
        channel = "whatsapp"
        raw_id = user_id[3:]
    else:
        # Default to telegram
        channel = "telegram"
        raw_id = user_id
    
    if channel == "telegram":
        token = os.getenv("TELEGRAM_TOKEN")
        if not token:
            logger.error("TELEGRAM_TOKEN not set")
            return False
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json={
                    "chat_id": raw_id,
                    "text": message,
                })
                if response.status_code == 200:
                    logger.info(f"Message sent to {user_id}")
                    return True
                else:
                    logger.error(f"Telegram API error: {response.text}")
                    return False
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                return False
    else:
        logger.error(f"Channel {channel} send not implemented yet")
        return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ClawLite - Lightweight Agentic AI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Send subcommand
    send_parser = subparsers.add_parser("send", help="Send a message to a user")
    send_parser.add_argument("-u", "--user", required=True, help="User ID (e.g., tg_123456)")
    send_parser.add_argument("-m", "--message", required=True, help="Message to send")
    
    # Import CLI commands
    from .cli.main import (
        cmd_new_instance, cmd_instances_list, cmd_instances_start,
        cmd_instances_stop, cmd_instances_remove, cmd_instances_path,
        cmd_templates_list
    )
    from .cli import get_instances_dir
    
    # instances command
    instances_parser = subparsers.add_parser("instances", help="Manage instances")
    instances_sub = instances_parser.add_subparsers(dest="instances_cmd")
    
    new_parser = instances_sub.add_parser("new", help="Create a new instance from template")
    new_parser.add_argument("template", help="Template reference (name, namespace/name, or path)")
    new_parser.add_argument("name", help="Instance name")
    new_parser.add_argument("--port", type=int, help="API port (auto-assigned if not specified)")
    
    list_parser = instances_sub.add_parser("list", help="List all instances")
    start_parser = instances_sub.add_parser("start", help="Start an instance")
    start_parser.add_argument("name", help="Instance name")
    stop_parser = instances_sub.add_parser("stop", help="Stop an instance")
    stop_parser.add_argument("name", help="Instance name")
    remove_parser = instances_sub.add_parser("remove", help="Remove an instance")
    remove_parser.add_argument("name", help="Instance name")
    remove_parser.add_argument("--force", "-f", action="store_true", help="Force remove")
    path_parser = instances_sub.add_parser("path", help="Get instance path")
    path_parser.add_argument("name", help="Instance name")
    
    # templates command
    templates_parser = subparsers.add_parser("templates", help="Manage templates")
    templates_sub = templates_parser.add_subparsers(dest="templates_cmd")
    tlist_parser = templates_sub.add_parser("list", help="List templates")
    
    args = parser.parse_args()
    
    if args.command == "send":
        success = asyncio.run(send_message(args.user, args.message))
        sys.exit(0 if success else 1)
    elif args.command == "instances":
        if args.instances_cmd == "new":
            sys.exit(cmd_new_instance(args))
        elif args.instances_cmd == "list":
            sys.exit(cmd_instances_list(args))
        elif args.instances_cmd == "start":
            sys.exit(cmd_instances_start(args))
        elif args.instances_cmd == "stop":
            sys.exit(cmd_instances_stop(args))
        elif args.instances_cmd == "remove":
            sys.exit(cmd_instances_remove(args))
        elif args.instances_cmd == "path":
            sys.exit(cmd_instances_path(args))
        else:
            instances_parser.print_help()
            sys.exit(0)
    elif args.command == "templates":
        if args.templates_cmd == "list":
            sys.exit(cmd_templates_list(args))
        else:
            templates_parser.print_help()
            sys.exit(0)
    else:
        # Default: run channels
        asyncio.run(run_channels())


if __name__ == "__main__":
    main()
