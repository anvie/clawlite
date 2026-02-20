"""
ClawLite - WhatsApp Channel
WhatsApp implementation using neonize library (sync client in thread)
"""

import os
import base64
import asyncio
import logging
import threading
from datetime import datetime
from typing import Optional, Callable, Any
from pathlib import Path
from queue import Queue

NEONIZE_AVAILABLE = False
NewClient = None
MessageEv = None
ConnectedEv = None
QREv = None
event = None
build_jid = None

try:
    from neonize.client import NewClient as _NewClient
    from neonize.events import MessageEv as _MessageEv, ConnectedEv as _ConnectedEv, QREv as _QREv, event as _event
    from neonize.utils import build_jid as _build_jid
    
    NewClient = _NewClient
    MessageEv = _MessageEv
    ConnectedEv = _ConnectedEv
    QREv = _QREv
    event = _event
    build_jid = _build_jid
    NEONIZE_AVAILABLE = True
except ImportError:
    pass

from .base import BaseChannel, WORKSPACE

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


class WhatsAppChannel(BaseChannel):
    """WhatsApp messaging channel using neonize (sync client in thread)."""
    
    name = "whatsapp"
    
    def __init__(self, agent_callback):
        if not NEONIZE_AVAILABLE:
            raise ImportError("neonize is not installed. Run: pip install neonize")
        
        super().__init__(agent_callback)
        
        # Configuration
        self.session_dir = os.getenv("WHATSAPP_SESSION_DIR", "/data/whatsapp")
        
        # Ensure session directory exists
        os.makedirs(self.session_dir, exist_ok=True)
        
        # Client instance
        self.client: Optional[Any] = None
        self.connected = False
        self.conversations: dict[str, list[dict]] = {}
        
        # Thread management
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._message_queue: Queue = Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    async def start(self) -> None:
        """Start the WhatsApp client in a background thread."""
        self.logger.info("Starting WhatsApp channel...")
        self._loop = asyncio.get_running_loop()
        
        # Start client in background thread
        self._thread = threading.Thread(target=self._run_client, daemon=True)
        self._thread.start()
        
        # Start message processor
        asyncio.create_task(self._process_messages())
        
        self.logger.info("WhatsApp channel started (running in background thread)")
    
    def _run_client(self) -> None:
        """Run the neonize client in a background thread."""
        try:
            # Change to session directory
            os.chdir(self.session_dir)
            
            self.logger.info("Creating WhatsApp client...")
            self.client = NewClient(name="clawlite")
            
            # Register event handlers
            @self.client.event(QREv)
            def on_qr(client, ev):
                self.logger.info("📱 QR Code received! Scan with WhatsApp on your phone:")
                # QR code is automatically printed to stdout by neonize
            
            @self.client.event(ConnectedEv)
            def on_connected(client, ev):
                self.connected = True
                self.logger.info("✅ WhatsApp connected!")
            
            @self.client.event(MessageEv)
            def on_message(client, ev):
                # Queue message for async processing
                self._message_queue.put(ev)
            
            self.logger.info("Connecting to WhatsApp...")
            self.logger.info("📱 Scan QR code if prompted (check container logs)")
            
            self.client.connect()
            
            # Keep running until stop event
            while not self._stop_event.is_set():
                event.wait(timeout=1)
                if self._stop_event.is_set():
                    break
                    
        except Exception as e:
            self.logger.error(f"WhatsApp client error: {e}")
    
    async def _process_messages(self) -> None:
        """Process messages from the queue."""
        while True:
            try:
                # Check queue with timeout
                await asyncio.sleep(0.1)
                
                while not self._message_queue.empty():
                    ev = self._message_queue.get_nowait()
                    await self._handle_message_event(ev)
                    
            except Exception as e:
                self.logger.error(f"Message processing error: {e}")
                await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the WhatsApp client."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.connected = False
        self.logger.info("WhatsApp channel stopped")
    
    async def send_message(self, user_id: str, text: str, **kwargs) -> bool:
        """Send a message to a user/group."""
        if not self.client or not self.connected:
            self.logger.error("WhatsApp not connected")
            return False
        
        try:
            jid = self._parse_jid(user_id)
            # Run sync send in thread
            await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.client.send_message(jid, text)
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message to {user_id}: {e}")
            return False
    
    def _parse_jid(self, user_id: str) -> str:
        """Parse user ID to WhatsApp JID format."""
        if "@" in user_id:
            return user_id
        phone = user_id.lstrip("+").replace("-", "").replace(" ", "")
        return build_jid(phone)
    
    def _extract_sender_id(self, ev: Any) -> str:
        """Extract sender ID from message event."""
        try:
            if hasattr(ev, 'Info') and hasattr(ev.Info, 'MessageSource'):
                source = ev.Info.MessageSource
                if hasattr(source, 'Sender'):
                    return str(source.Sender)
        except Exception:
            pass
        return "unknown"
    
    def _extract_chat_id(self, ev: Any) -> str:
        """Extract chat ID from message event."""
        try:
            if hasattr(ev, 'Info') and hasattr(ev.Info, 'MessageSource'):
                source = ev.Info.MessageSource
                if hasattr(source, 'Chat'):
                    return str(source.Chat)
        except Exception:
            pass
        return "unknown"
    
    def _extract_text(self, ev: Any) -> Optional[str]:
        """Extract text content from message event."""
        try:
            msg = ev.Message
            
            if hasattr(msg, 'conversation') and msg.conversation:
                return msg.conversation
            if hasattr(msg, 'extendedTextMessage') and msg.extendedTextMessage:
                return msg.extendedTextMessage.text
            if hasattr(msg, 'imageMessage') and msg.imageMessage:
                return msg.imageMessage.caption or ""
            if hasattr(msg, 'documentMessage') and msg.documentMessage:
                return msg.documentMessage.caption or ""
            if hasattr(msg, 'videoMessage') and msg.videoMessage:
                return msg.videoMessage.caption or ""
        except Exception as e:
            self.logger.debug(f"Error extracting text: {e}")
        return None
    
    async def _handle_message_event(self, ev: Any) -> None:
        """Handle incoming WhatsApp message."""
        try:
            sender_id = self._extract_sender_id(ev)
            chat_id = self._extract_chat_id(ev)
            text = self._extract_text(ev)
            
            if sender_id == "unknown":
                return
            
            if not self.is_allowed(sender_id):
                self.logger.debug(f"Ignoring message from unauthorized: {sender_id}")
                return
            
            user_id = chat_id if chat_id != "unknown" else sender_id
            
            self.logger.info(f"📩 [{user_id}]: {text[:100] if text else '(media)'}...")
            
            if not text:
                return
            
            # Get conversation history
            if user_id not in self.conversations:
                self.conversations[user_id] = []
            
            # Send thinking status
            await self.send_message(user_id, "🧠 _Thinking..._")
            
            try:
                from ..agent import run_agent
                
                response, new_history = await run_agent(
                    text,
                    self.conversations[user_id],
                    user_id=user_id,
                    status_callback=lambda x: None,
                    images=None,
                )
                
                self.conversations[user_id] = new_history
                
                import re
                final_text = re.sub(
                    r'<tool_?call>.*?</tool_?call>',
                    '',
                    response,
                    flags=re.DOTALL | re.IGNORECASE
                )
                final_text = final_text.strip()
                
                if final_text:
                    await self._send_long_message(user_id, final_text)
                else:
                    await self.send_message(user_id, "✅ Done!")
                    
            except Exception as e:
                self.logger.error(f"Error processing message: {e}")
                await self.send_message(user_id, f"❌ Error: {str(e)[:500]}")
                
        except Exception as e:
            self.logger.error(f"Error in message handler: {e}")
    
    async def _send_long_message(self, user_id: str, text: str, max_len: int = 4000) -> None:
        """Send long text in chunks."""
        while text:
            if len(text) <= max_len:
                await self.send_message(user_id, text)
                break
            
            break_point = text.rfind('\n', 0, max_len)
            if break_point < max_len // 2:
                break_point = text.rfind(' ', 0, max_len)
            if break_point < max_len // 2:
                break_point = max_len
            
            await self.send_message(user_id, text[:break_point])
            text = text[break_point:].strip()
            await asyncio.sleep(0.5)
