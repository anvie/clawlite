"""
ClawLite - WhatsApp Channel
WhatsApp implementation using neonize library
"""

import os
import base64
import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path

try:
    from neonize.aioze.client import NewAClient
    from neonize.aioze.events import MessageEv, ConnectedEv, DisconnectedEv
    from neonize.utils import build_jid
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import (
        Message as WAMessage,
        ExtendedTextMessage,
        ImageMessage,
        DocumentMessage,
    )
    NEONIZE_AVAILABLE = True
except ImportError:
    NEONIZE_AVAILABLE = False

from .base import BaseChannel, WORKSPACE

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


class WhatsAppChannel(BaseChannel):
    """WhatsApp messaging channel using neonize."""
    
    name = "whatsapp"
    
    def __init__(self, agent_callback):
        if not NEONIZE_AVAILABLE:
            raise ImportError("neonize is not installed. Run: pip install neonize")
        
        super().__init__(agent_callback)
        
        # Configuration
        self.session_dir = os.getenv("WHATSAPP_SESSION_DIR", "/data/whatsapp")
        self.db_path = os.path.join(self.session_dir, "neonize.db")
        
        # Ensure session directory exists
        os.makedirs(self.session_dir, exist_ok=True)
        
        # Client instance
        self.client: Optional[NewAClient] = None
        self.connected = False
        self.conversations: dict[str, list[dict]] = {}
        
        # Status message tracking (for editing)
        self._status_messages: dict[str, str] = {}
    
    async def start(self) -> None:
        """Start the WhatsApp client."""
        self.logger.info("Starting WhatsApp channel...")
        
        # Initialize client
        self.client = NewAClient(
            name="clawlite",
            database=self.db_path,
        )
        
        # Register event handlers
        @self.client.event(ConnectedEv)
        async def on_connected(client: NewAClient, event: ConnectedEv):
            self.connected = True
            self.logger.info("✅ WhatsApp connected!")
            if hasattr(event, 'device'):
                self.logger.info(f"📱 Device: {event.device}")
        
        @self.client.event(DisconnectedEv)
        async def on_disconnected(client: NewAClient, event: DisconnectedEv):
            self.connected = False
            self.logger.warning("⚠️ WhatsApp disconnected")
        
        @self.client.event(MessageEv)
        async def on_message(client: NewAClient, event: MessageEv):
            await self._handle_message_event(event)
        
        # Connect (will show QR code if not logged in)
        self.logger.info("Connecting to WhatsApp...")
        self.logger.info("📱 Scan QR code with your phone if prompted")
        
        await self.client.connect()
    
    async def stop(self) -> None:
        """Stop the WhatsApp client."""
        if self.client:
            # neonize handles cleanup automatically
            self.connected = False
            self.logger.info("WhatsApp channel stopped")
    
    async def send_message(self, user_id: str, text: str, **kwargs) -> bool:
        """Send a message to a user/group."""
        if not self.client or not self.connected:
            self.logger.error("WhatsApp not connected")
            return False
        
        try:
            jid = self._parse_jid(user_id)
            await self.client.send_message(jid, text=text)
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message to {user_id}: {e}")
            return False
    
    def _parse_jid(self, user_id: str) -> str:
        """Parse user ID to WhatsApp JID format."""
        # Already a JID
        if "@" in user_id:
            return user_id
        
        # Phone number - convert to JID
        phone = user_id.lstrip("+").replace("-", "").replace(" ", "")
        return build_jid(phone)
    
    def _extract_sender_id(self, event: MessageEv) -> str:
        """Extract sender ID from message event."""
        try:
            if hasattr(event, 'Info') and hasattr(event.Info, 'MessageSource'):
                source = event.Info.MessageSource
                if hasattr(source, 'Sender'):
                    return str(source.Sender)
            # Fallback
            if hasattr(event, 'info') and hasattr(event.info, 'message_source'):
                source = event.info.message_source
                if hasattr(source, 'sender'):
                    return str(source.sender)
        except Exception:
            pass
        return "unknown"
    
    def _extract_chat_id(self, event: MessageEv) -> str:
        """Extract chat ID from message event."""
        try:
            if hasattr(event, 'Info') and hasattr(event.Info, 'MessageSource'):
                source = event.Info.MessageSource
                if hasattr(source, 'Chat'):
                    return str(source.Chat)
            # Fallback
            if hasattr(event, 'info') and hasattr(event.info, 'message_source'):
                source = event.info.message_source
                if hasattr(source, 'chat'):
                    return str(source.chat)
        except Exception:
            pass
        return "unknown"
    
    def _extract_text(self, event: MessageEv) -> Optional[str]:
        """Extract text content from message event."""
        try:
            msg = event.Message if hasattr(event, 'Message') else event.message
            
            # Plain text conversation
            if hasattr(msg, 'conversation') and msg.conversation:
                return msg.conversation
            
            # Extended text message
            if hasattr(msg, 'extendedTextMessage') and msg.extendedTextMessage:
                return msg.extendedTextMessage.text
            
            # Image caption
            if hasattr(msg, 'imageMessage') and msg.imageMessage:
                return msg.imageMessage.caption or ""
            
            # Document caption
            if hasattr(msg, 'documentMessage') and msg.documentMessage:
                return msg.documentMessage.caption or ""
            
            # Video caption
            if hasattr(msg, 'videoMessage') and msg.videoMessage:
                return msg.videoMessage.caption or ""
                
        except Exception as e:
            self.logger.debug(f"Error extracting text: {e}")
        
        return None
    
    async def _download_media(self, event: MessageEv, user_id: str) -> Optional[tuple[str, bytes]]:
        """Download media from message, return (relative_path, data)."""
        try:
            msg = event.Message if hasattr(event, 'Message') else event.message
            
            media_data = None
            filename = None
            
            # Image
            if hasattr(msg, 'imageMessage') and msg.imageMessage:
                media_data = await self.client.download_any(msg)
                filename = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            
            # Document
            elif hasattr(msg, 'documentMessage') and msg.documentMessage:
                media_data = await self.client.download_any(msg)
                filename = msg.documentMessage.fileName or f"doc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Video
            elif hasattr(msg, 'videoMessage') and msg.videoMessage:
                media_data = await self.client.download_any(msg)
                filename = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            
            # Audio
            elif hasattr(msg, 'audioMessage') and msg.audioMessage:
                media_data = await self.client.download_any(msg)
                filename = f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg"
            
            if media_data and filename:
                # Save to workspace
                upload_dir = os.path.join(WORKSPACE, "uploads", user_id)
                os.makedirs(upload_dir, exist_ok=True)
                
                file_path = os.path.join(upload_dir, filename)
                with open(file_path, "wb") as f:
                    f.write(media_data)
                
                relative_path = os.path.relpath(file_path, WORKSPACE)
                return relative_path, media_data
                
        except Exception as e:
            self.logger.error(f"Error downloading media: {e}")
        
        return None
    
    async def _handle_message_event(self, event: MessageEv) -> None:
        """Handle incoming WhatsApp message."""
        try:
            sender_id = self._extract_sender_id(event)
            chat_id = self._extract_chat_id(event)
            text = self._extract_text(event)
            
            # Skip if no sender
            if sender_id == "unknown":
                return
            
            # Check authorization
            if not self.is_allowed(sender_id):
                self.logger.debug(f"Ignoring message from unauthorized user: {sender_id}")
                return
            
            # Use chat_id as the user identifier for conversation context
            user_id = chat_id if chat_id != "unknown" else sender_id
            
            self.logger.info(f"📩 [{user_id}]: {text[:100] if text else '(media)'}...")
            
            # Check for media
            images = None
            file_context = None
            
            media_result = await self._download_media(event, user_id)
            if media_result:
                relative_path, media_data = media_result
                
                # Check if it's an image
                _, ext = os.path.splitext(relative_path.lower())
                if ext in IMAGE_EXTENSIONS:
                    images = [base64.b64encode(media_data).decode("utf-8")]
                    file_context = f"[User sent an image which is now visible to you. Saved at: {relative_path}]"
                else:
                    file_context = f"[User sent a file: {relative_path}]\nThe file has been saved to workspace."
            
            # Combine text with file context
            full_message = ""
            if file_context:
                full_message = file_context
                if text:
                    full_message += f"\n\n{text}"
            else:
                full_message = text or ""
            
            if not full_message:
                return  # Nothing to process
            
            # Get conversation history
            if user_id not in self.conversations:
                self.conversations[user_id] = []
            
            # Send "thinking" status
            await self.send_message(user_id, "🧠 _Thinking..._")
            
            # Status callback for updates
            async def update_status(status_text: str):
                # WhatsApp doesn't support editing, so we just log
                self.logger.debug(f"Status update: {status_text[:50]}...")
            
            try:
                # Import agent
                from ..agent import run_agent
                
                response, new_history = await run_agent(
                    full_message,
                    self.conversations[user_id],
                    user_id=user_id,
                    status_callback=update_status,
                    images=images,
                )
                
                self.conversations[user_id] = new_history
                
                # Clean up response
                import re
                final_text = re.sub(
                    r'<tool_?call>.*?</tool_?call>',
                    '',
                    response,
                    flags=re.DOTALL | re.IGNORECASE
                )
                final_text = final_text.strip()
                
                if final_text:
                    # Send response (split if too long)
                    await self._send_long_message(user_id, final_text)
                else:
                    await self.send_message(user_id, "✅ Done!")
                    
            except Exception as e:
                self.logger.error(f"Error processing message from {user_id}: {e}")
                await self.send_message(user_id, f"❌ Error: {str(e)[:500]}")
                
        except Exception as e:
            self.logger.error(f"Error in message handler: {e}")
    
    async def _send_long_message(self, user_id: str, text: str, max_len: int = 4000) -> None:
        """Send long text in chunks."""
        while text:
            if len(text) <= max_len:
                await self.send_message(user_id, text)
                break
            
            # Find break point
            break_point = text.rfind('\n', 0, max_len)
            if break_point < max_len // 2:
                break_point = text.rfind(' ', 0, max_len)
            if break_point < max_len // 2:
                break_point = max_len
            
            await self.send_message(user_id, text[:break_point])
            text = text[break_point:].strip()
            
            # Small delay between chunks
            await asyncio.sleep(0.5)
