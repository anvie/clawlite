#!/usr/bin/env python3
"""
ClawLite CLI - Send message or file to user via configured channels.

Usage:
    python -m src.cli.send --user tg_123456 --message "Hello!"
    python -m src.cli.send -u tg_123456 -m "Reminder: Time to ngaji!"
    python -m src.cli.send -u tg_123456 -f /workspace/photos/sunset.jpg -c "Beautiful sunset!"
"""

import os
import sys
import argparse
import asyncio
import mimetypes
from pathlib import Path
import httpx

# Load env
from ..env_loader import load_env
load_env()


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


async def send_telegram_file(user_id: str, file_path: str, caption: str = "") -> bool:
    """Send file via Telegram Bot API."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN not set", file=sys.stderr)
        return False
    
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return False
    
    # Determine file type and appropriate endpoint
    mime_type, _ = mimetypes.guess_type(str(path))
    mime_type = mime_type or "application/octet-stream"
    
    if mime_type.startswith("image/"):
        endpoint = "sendPhoto"
        file_key = "photo"
    elif mime_type.startswith("video/"):
        endpoint = "sendVideo"
        file_key = "video"
    elif mime_type.startswith("audio/"):
        endpoint = "sendAudio"
        file_key = "audio"
    else:
        endpoint = "sendDocument"
        file_key = "document"
    
    url = f"https://api.telegram.org/bot{token}/{endpoint}"
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            with open(path, "rb") as f:
                files = {file_key: (path.name, f, mime_type)}
                data = {"chat_id": user_id}
                if caption:
                    data["caption"] = caption
                
                response = await client.post(url, files=files, data=data)
            
            if response.status_code == 200:
                return True
            else:
                print(f"Telegram API error: {response.text}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"Error sending file: {e}", file=sys.stderr)
            return False


async def send_whatsapp(user_id: str, message: str) -> bool:
    """Send message via WhatsApp (placeholder - needs neonize client)."""
    # TODO: Implement WhatsApp sending
    print("WhatsApp sending not yet implemented", file=sys.stderr)
    return False


async def send_whatsapp_file(user_id: str, file_path: str, caption: str = "") -> bool:
    """Send file via WhatsApp (placeholder)."""
    # TODO: Implement WhatsApp file sending
    print("WhatsApp file sending not yet implemented", file=sys.stderr)
    return False


async def main():
    parser = argparse.ArgumentParser(description="Send message or file to ClawLite user")
    parser.add_argument("-u", "--user", required=True, help="User ID (e.g., tg_123456)")
    parser.add_argument("-m", "--message", help="Message to send")
    parser.add_argument("-f", "--file", help="File path to send")
    parser.add_argument("-c", "--caption", default="", help="Caption for file (optional)")
    
    args = parser.parse_args()
    
    # Validate: must have either message or file
    if not args.message and not args.file:
        print("Error: Must provide either --message or --file", file=sys.stderr)
        sys.exit(1)
    
    channel, raw_id = parse_user_id(args.user)
    
    success = True
    
    # Send message if provided
    if args.message:
        if channel == "telegram":
            success = await send_telegram(raw_id, args.message)
        elif channel == "whatsapp":
            success = await send_whatsapp(raw_id, args.message)
        else:
            print(f"Unknown channel: {channel}", file=sys.stderr)
            sys.exit(1)
    
    # Send file if provided
    if args.file and success:
        if channel == "telegram":
            success = await send_telegram_file(raw_id, args.file, args.caption)
        elif channel == "whatsapp":
            success = await send_whatsapp_file(raw_id, args.file, args.caption)
        else:
            print(f"Unknown channel: {channel}", file=sys.stderr)
            sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
