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


async def run_channels():
    """Run all enabled channels."""
    from .channels import get_enabled_channels, create_channel, get_available_channels
    from .agent import run_agent
    
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
    
    # Start all channels
    start_tasks = []
    for channel in active_channels:
        start_tasks.append(asyncio.create_task(channel.start()))
    
    # Print startup info
    print_startup_info()
    
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
        # Stop all channels
        logger.info("🔄 Stopping channels...")
        stop_tasks = [channel.stop() for channel in active_channels]
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        logger.info("✅ All channels stopped")


def print_startup_info():
    """Print startup information."""
    llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    
    print("\n" + "=" * 50)
    print("🦎 ClawLite - Lightweight Agentic AI")
    print("=" * 50)
    
    if llm_provider == "openrouter":
        model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-pro-preview-03-25")
        print(f"   Provider: OpenRouter")
        print(f"   Model: {model}")
    else:
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        print(f"   Provider: Ollama")
        print(f"   Model: {ollama_model}")
        print(f"   Host: {ollama_host}")
    
    print(f"   Workspace: {os.getenv('WORKSPACE_PATH', '/workspace')}")
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
    
    args = parser.parse_args()
    
    if args.command == "send":
        success = asyncio.run(send_message(args.user, args.message))
        sys.exit(0 if success else 1)
    else:
        # Default: run channels
        asyncio.run(run_channels())


if __name__ == "__main__":
    main()
