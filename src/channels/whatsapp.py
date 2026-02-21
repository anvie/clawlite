"""
ClawLite - WhatsApp Channel
WhatsApp implementation using neonize library (sync client in thread)
"""

import os
import base64
import asyncio
import logging
import threading
import re
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
    from neonize.client import NewClient as _NewClient, ChatPresence, ChatPresenceMedia
    from neonize.events import MessageEv as _MessageEv, ConnectedEv as _ConnectedEv, QREv as _QREv, event as _event
    from neonize.utils import build_jid as _build_jid
    from neonize.proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 import DeviceProps
    from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message, ExtendedTextMessage, ContextInfo
    
    NewClient = _NewClient
    MessageEv = _MessageEv
    ConnectedEv = _ConnectedEv
    QREv = _QREv
    event = _event
    build_jid = _build_jid
    NEONIZE_AVAILABLE = True
except ImportError:
    ChatPresence = None
    ChatPresenceMedia = None
    DeviceProps = None
    Message = None
    ExtendedTextMessage = None
    ContextInfo = None

from .base import BaseChannel, WORKSPACE

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


class WhatsAppChannel(BaseChannel):
    """WhatsApp messaging channel using neonize (sync client in thread)."""
    
    name = "whatsapp"
    prefix = "wa"  # User IDs will be prefixed as wa_<id>
    
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
        
        self.logger.info("WhatsApp channel started")
    
    def _run_client(self) -> None:
        """Run the neonize client in a background thread."""
        try:
            # Change to session directory for session persistence
            os.chdir(self.session_dir)
            
            self.logger.info("Creating WhatsApp client...")
            # Set device props to look like Chrome browser to avoid AI labeling
            props = DeviceProps(
                os="Windows",
                platformType=DeviceProps.PlatformType.CHROME,
            )
            self.client = NewClient(name="Browser", props=props)
            
            # Register event handlers
            @self.client.event(QREv)
            def on_qr(client, ev):
                self.logger.info("📱 QR Code received! Scan with WhatsApp on your phone:")
            
            @self.client.event(ConnectedEv)
            def on_connected(client, ev):
                self.connected = True
                self.logger.info("✅ WhatsApp connected!")
            
            @self.client.event(MessageEv)
            def on_message(client, ev):
                try:
                    # Ignore our own messages
                    info = ev.Info if hasattr(ev, 'Info') else getattr(ev, 'info', None)
                    if info:
                        is_from_me = getattr(info, 'IsFromMe', False) or getattr(info, 'is_from_me', False)
                        if is_from_me:
                            return
                    
                    text = self._extract_text(ev)
                    if text:
                        sender = self._extract_sender_id(ev)
                        self.logger.info(f"📨 [{sender}]: {text[:50]}...")
                        self._message_queue.put(ev)
                        
                except Exception as e:
                    self.logger.error(f"Error processing message event: {e}")
            
            self.logger.info("Connecting to WhatsApp...")
            self.logger.info("📱 Scan QR code if prompted")
            
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
            await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.client.send_message(jid, text)
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message to {user_id}: {e}")
            return False
    
    async def send_sanitized_reply(self, ev: Any, text: str) -> bool:
        """
        Send a reply without inheriting AI metadata flags.
        Constructs a clean quoted reply using only stanzaId and participant.
        """
        if not self.client or not self.connected:
            self.logger.error("WhatsApp not connected")
            return False
        
        try:
            # Extract identifiers from event
            info = ev.Info if hasattr(ev, 'Info') else getattr(ev, 'info', None)
            message_id = info.ID if hasattr(info, 'ID') else getattr(info, 'id', '')
            
            # Get sender JID
            source = info.MessageSource if hasattr(info, 'MessageSource') else getattr(info, 'message_source', None)
            sender = source.Sender if hasattr(source, 'Sender') else getattr(source, 'sender', None)
            chat = source.Chat if hasattr(source, 'Chat') else getattr(source, 'chat', None)
            
            # Convert to string JID
            if hasattr(sender, 'ToNonAD'):
                sender_jid = sender.ToNonAD().String()
            else:
                sender_jid = str(sender)
            
            # Build clean ContextInfo (without quotedMessage to avoid AI metadata)
            clean_context = ContextInfo(
                stanzaId=message_id,
                participant=sender_jid
            )
            
            # Create ExtendedTextMessage with clean context
            extended_text = ExtendedTextMessage(
                text=text,
                contextInfo=clean_context
            )
            
            # Create final Message
            clean_msg = Message(
                extendedTextMessage=extended_text
            )
            
            # Send sanitized message
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.send_message(chat, message=clean_msg)
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to send sanitized reply: {e}")
            return False
    
    async def send_typing(self, user_id: str, typing: bool = True) -> bool:
        """Send typing indicator (composing/paused)."""
        if not self.client or not self.connected:
            return False
        
        try:
            jid = self._parse_jid(user_id)
            state = ChatPresence.CHAT_PRESENCE_COMPOSING if typing else ChatPresence.CHAT_PRESENCE_PAUSED
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.send_chat_presence(jid, state, ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
            )
            return True
        except Exception as e:
            self.logger.debug(f"Failed to send typing indicator: {e}")
            return False
    
    def _parse_jid(self, user_id: str) -> str:
        """Parse user ID to WhatsApp JID format."""
        if "@" in user_id:
            return user_id
        phone = user_id.lstrip("+").replace("-", "").replace(" ", "")
        return build_jid(phone)
    
    def _extract_sender_id(self, ev: Any) -> str:
        """Extract sender ID (phone number) from message event."""
        try:
            if hasattr(ev, 'Info') and hasattr(ev.Info, 'MessageSource'):
                source = ev.Info.MessageSource
                if hasattr(source, 'Sender'):
                    sender = source.Sender
                    if hasattr(sender, 'User'):
                        return str(sender.User)
                    return str(sender).split('@')[0].split(':')[0]
        except Exception:
            pass
        return "unknown"
    
    def _extract_chat_id(self, ev: Any) -> str:
        """Extract chat ID (phone number or group) from message event."""
        try:
            if hasattr(ev, 'Info') and hasattr(ev.Info, 'MessageSource'):
                source = ev.Info.MessageSource
                if hasattr(source, 'Chat'):
                    chat = source.Chat
                    if hasattr(chat, 'User'):
                        return str(chat.User)
                    return str(chat).split('@')[0].split(':')[0]
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
        except Exception:
            pass
        return None
    
    async def _handle_message_event(self, ev: Any) -> None:
        """Handle incoming WhatsApp message."""
        try:
            raw_sender_id = self._extract_sender_id(ev)
            raw_chat_id = self._extract_chat_id(ev)
            text = self._extract_text(ev)
            
            if raw_sender_id == "unknown" or not text:
                return
            
            # Use prefixed user ID for access control and storage
            raw_user_id = raw_chat_id if raw_chat_id != "unknown" else raw_sender_id
            user_id = self.format_user_id(raw_user_id)
            
            if not self.is_allowed(user_id):
                self.logger.debug(f"Ignoring unauthorized: {user_id}")
                return
            
            self.logger.info(f"📩 Processing [{user_id}]: {text[:50]}...")
            
            # Get conversation history
            if user_id not in self.conversations:
                self.conversations[user_id] = []
            
            # Show typing indicator (use raw ID for WhatsApp API)
            await self.send_typing(raw_user_id, True)
            
            try:
                from ..agent import run_agent
                
                async def noop_status(x): pass
                
                result = await run_agent(
                    text,
                    self.conversations[user_id],
                    user_id=user_id,  # Pass prefixed user_id
                    status_callback=noop_status,
                    images=None,
                )
                
                self.conversations[user_id] = result.history
                
                # Stop typing indicator (use raw ID for WhatsApp API)
                await self.send_typing(raw_user_id, False)
                
                # Handle file response from skills
                if result.file_data:
                    await self._send_file(raw_user_id, result.file_data)
                    return
                
                # Clean tool calls from response
                final_text = re.sub(
                    r'<tool_?call>.*?</tool_?call>',
                    '',
                    result.response,
                    flags=re.DOTALL | re.IGNORECASE
                )
                final_text = final_text.strip()
                
                if final_text:
                    await self._send_long_message(raw_user_id, final_text)
                else:
                    await self.send_message(raw_user_id, "✅ Done!")
                    
            except Exception as e:
                await self.send_typing(raw_user_id, False)
                self.logger.error(f"Agent error: {e}")
                await self.send_message(raw_user_id, f"❌ Error: {str(e)[:500]}")
                
        except Exception as e:
            self.logger.error(f"Message handler error: {e}")
    
    async def _send_file(self, user_id: str, file_data: dict) -> None:
        """Send a file to the user."""
        if not self.client or not self.connected:
            self.logger.error("WhatsApp not connected")
            return
        
        try:
            import io
            import tempfile
            
            filename = file_data.get("filename", "file")
            caption = file_data.get("caption", "")
            data_b64 = file_data.get("data", "")
            content_type = file_data.get("content_type", "application/octet-stream")
            
            # Decode base64 data
            file_bytes = base64.b64decode(data_b64)
            
            # Save to temp file (neonize needs file path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            
            try:
                jid = self._parse_jid(user_id)
                
                # Send document
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.send_document(
                        jid,
                        tmp_path,
                        caption=caption,
                        filename=filename,
                        mimetype=content_type,
                    )
                )
                
                self.logger.info(f"📤 Sent file: {filename} ({len(file_bytes)} bytes)")
                
            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except:
                    pass
                    
        except Exception as e:
            self.logger.error(f"Failed to send file: {e}")
            await self.send_message(user_id, f"❌ Failed to send file: {str(e)[:200]}")
    
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
