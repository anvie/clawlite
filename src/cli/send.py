#!/usr/bin/env python3
"""
ClawLite CLI - Send message to user via configured channels.

Usage:
    python -m src.cli.send --user tg_123456 --message "Hello!"
    python -m src.cli.send -u tg_123456 -m "Reminder: Time to ngaji!"
"""

import os
import sys
import argparse
import asyncio
import httpx

# Load env
from dotenv import load_dotenv
load_dotenv()


def parse_user_id(user_id: str) -> tuple[str, str]:
    """Parse prefixed user ID into (channel, raw_id)."""
    if user_id.startswith("tg_"):
        return "telegram", user_id[3:]
    elif user_id.startswith("wa_"):
        return "whatsapp", user_id[3:]
    else:
        # Default to telegram if no prefix
        return "telegram", user_id


async def send_telegram(user_id: str, message: str) -> bool:
    """Send message via Telegram Bot API."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN not set", file=sys.stderr)
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json={
                "chat_id": user_id,
                "text": message,
            })
            
            if response.status_code == 200:
                return True
            else:
                print(f"Telegram API error: {response.text}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"Error sending message: {e}", file=sys.stderr)
            return False


async def send_whatsapp(user_id: str, message: str) -> bool:
    """Send message via WhatsApp (placeholder - needs neonize client)."""
    # TODO: Implement WhatsApp sending
    # This would need to connect to running neonize client
    print("WhatsApp sending not yet implemented", file=sys.stderr)
    return False


async def main():
    parser = argparse.ArgumentParser(description="Send message to ClawLite user")
    parser.add_argument("-u", "--user", required=True, help="User ID (e.g., tg_123456)")
    parser.add_argument("-m", "--message", required=True, help="Message to send")
    
    args = parser.parse_args()
    
    channel, raw_id = parse_user_id(args.user)
    
    if channel == "telegram":
        success = await send_telegram(raw_id, args.message)
    elif channel == "whatsapp":
        success = await send_whatsapp(raw_id, args.message)
    else:
        print(f"Unknown channel: {channel}", file=sys.stderr)
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
