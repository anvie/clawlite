"""
ClawLite - Telegram Channel
Telegram bot implementation using python-telegram-bot
"""

import os
import base64
import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from .base import BaseChannel, WORKSPACE
from ..errors import sanitize_error

logger = logging.getLogger(__name__)

# Supported image extensions for vision
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


class TelegramChannel(BaseChannel):
    """Telegram messaging channel."""
    
    name = "telegram"
    prefix = "tg"  # User IDs will be prefixed as tg_<id>
    
    def __init__(self, agent_callback):
        super().__init__(agent_callback)
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.application: Optional[Application] = None
        self.conversations: dict[str, list[dict]] = {}  # Now keyed by prefixed user_id
    
    async def start(self) -> None:
        """Start the Telegram bot."""
        if not self.token:
            raise ValueError("TELEGRAM_TOKEN not set!")
        
        self.application = Application.builder().token(self.token).build()
        
        # Register handlers
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("clear", self._cmd_clear))
        self.application.add_handler(CommandHandler("tools", self._cmd_tools))
        self.application.add_handler(CommandHandler("workspace", self._cmd_workspace))
        self.application.add_handler(CommandHandler("dump", self._cmd_dump))
        self.application.add_handler(MessageHandler(filters.PHOTO, self._handle_photo))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self._handle_document))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        
        self.logger.info("Telegram channel starting...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            self.logger.info("Telegram channel stopped")
    
    async def send_message(self, user_id: str, text: str, **kwargs) -> bool:
        """Send a message to a user."""
        try:
            # Strip prefix if present (e.g., tg_123456 -> 123456)
            raw_id = self.strip_prefix(user_id)
            await self.application.bot.send_message(
                chat_id=int(raw_id),
                text=text,
                parse_mode=kwargs.get("parse_mode", "Markdown")
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message to {user_id}: {e}")
            return False
    
    async def _download_file(self, file_obj, user_id: int, filename: str) -> str:
        """Download a Telegram file to workspace/uploads/{user_id}/"""
        upload_dir = os.path.join(WORKSPACE, "uploads", str(user_id))
        os.makedirs(upload_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name, ext = os.path.splitext(filename)
        unique_filename = f"{name}_{timestamp}{ext}"
        
        file_path = os.path.join(upload_dir, unique_filename)
        await file_obj.download_to_drive(file_path)
        
        return os.path.relpath(file_path, WORKSPACE)
    
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user = update.effective_user
        user_id = self.format_user_id(user.id)
        
        if not self.is_allowed(user_id):
            await update.message.reply_text("⛔ Not authorized.")
            return
        
        self.logger.info(f"👋 /start from {user_id} ({user.username})")
        await update.message.reply_text(
            f"👋 Halo {user.first_name}!\n\n"
            f"Saya *ClawLite* — AI assistant ringan dengan Ollama.\n\n"
            f"Saya bisa:\n"
            f"• 📁 Membaca/menulis file di workspace\n"
            f"• 🔍 Mencari dalam file\n"
            f"• 💻 Menjalankan command (terbatas)\n"
            f"• 🧠 Berpikir step-by-step\n\n"
            f"Commands:\n"
            f"/clear - Hapus history\n"
            f"/tools - List available tools\n"
            f"/workspace - Lihat isi workspace",
            parse_mode="Markdown"
        )
    
    async def _cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /clear command."""
        user_id = self.format_user_id(update.effective_user.id)
        if not self.is_allowed(user_id):
            return
        
        # Clear in-memory history
        self.conversations[user_id] = []
        
        # Clear persisted conversation
        try:
            from ..conversation import clear_today, is_enabled
            if is_enabled():
                clear_today(user_id)
                await self._handle_clear(user_id)

        except Exception as e:
            self.logger.warning(f"Failed to clear persisted conversation: {e}")
        
        self.logger.info(f"🗑️ Cleared history for {user_id}")
        await update.message.reply_text("🗑️ History cleared.")
    
    async def _cmd_tools(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /tools command."""
        user_id = self.format_user_id(update.effective_user.id)
        if not self.is_allowed(user_id):
            return
        
        from ..tools import list_tools
        tools = list_tools(user_id=user_id)
        
        text = "🔧 Available Tools:\n\n"
        for t in tools:
            # Keep description short to avoid Telegram message limits
            desc = t['description'][:80] + "..." if len(t['description']) > 80 else t['description']
            text += f"• {t['name']} — {desc}\n"
        
        # Try Markdown first, fallback to plain text
        try:
            await update.message.reply_text(text)
        except Exception as e:
            self.logger.error(f"Failed to send tools list: {e}")
            await update.message.reply_text("Error listing tools")
    
    async def _cmd_workspace(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /workspace command."""
        user_id = self.format_user_id(update.effective_user.id)
        if not self.is_allowed(user_id):
            return
        
        from ..tools import get_tool
        tool = get_tool("list_dir")
        result = await tool.execute(path=".")
        
        if result.success:
            await update.message.reply_text(
                f"📁 *Workspace:*\n```\n{result.output}\n```",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"❌ Error: {result.error}")
    
    async def _cmd_dump(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /dump command - dump full context to file."""
        user_id = self.format_user_id(update.effective_user.id)
        if not self.is_allowed(user_id):
            return
        
        # Use the base class handler
        result = await self._handle_dump(user_id)
        await update.message.reply_text(result)
    
    async def _handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        file_context: str = None,
        images: list[str] = None
    ) -> None:
        """Handle text messages."""
        user = update.effective_user
        user_id = self.format_user_id(user.id)
        
        if not self.is_allowed(user_id):
            await update.message.reply_text("⛔ Not authorized.")
            return
        
        user_message = update.message.text or update.message.caption or ""
        
        if file_context:
            user_message = f"{file_context}\n\n{user_message}" if user_message else file_context
        
        if not user_message:
            await update.message.reply_text("❓ No message received.")
            return
        
        self.logger.info(f"📩 [{user_id}]: {user_message[:100]}{'(+image)' if images else ''}...")
        
        # Send initial status
        status_msg = await update.message.reply_text("🧠 _Thinking..._", parse_mode="Markdown")
        
        async def update_status(text):
            try:
                if len(text) > 4000:
                    text = text[:4000] + "..."
                await status_msg.edit_text(text, parse_mode="Markdown")
            except Exception:
                try:
                    await status_msg.edit_text(text[:4000])
                except Exception:
                    pass
        
        # Get conversation history
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        try:
            # Import agent here to avoid circular imports
            from ..agent import run_agent
            
            result = await run_agent(
                user_message,
                self.conversations[user_id],
                user_id=user_id,
                status_callback=update_status,
                images=images,
            )
            
            self.conversations[user_id] = result.history
            
            # Handle file response from skills
            if result.file_data:
                await self._send_file(update, status_msg, result.file_data)
                return
            
            # Clean up response
            import re
            final_text = re.sub(
                r'<tool_?call>.*?</tool_?call>',
                '',
                result.response,
                flags=re.DOTALL | re.IGNORECASE
            )
            final_text = final_text.strip()
            
            if not final_text:
                await status_msg.edit_text("✅ Done!")
                return
            
            # Send response in chunks
            await self._send_chunked(update, status_msg, final_text)
            
        except Exception as e:
            self.logger.error(f"Error for user {user_id}: {e}")
            await status_msg.edit_text(f"❌ {sanitize_error(e)}")
    
    async def _send_file(
        self,
        update: Update,
        status_msg,
        file_data: dict,
    ) -> None:
        """Send a file to the user."""
        try:
            import io
            
            filename = file_data.get("filename", "file")
            caption = file_data.get("caption", "")
            data_b64 = file_data.get("data", "")
            content_type = file_data.get("content_type", "application/octet-stream")
            
            # Decode base64 data
            file_bytes = base64.b64decode(data_b64)
            file_obj = io.BytesIO(file_bytes)
            file_obj.name = filename
            
            # Delete status message
            try:
                await status_msg.delete()
            except Exception:
                pass
            
            # Send based on content type
            if "pdf" in content_type:
                await update.message.reply_document(
                    document=file_obj,
                    filename=filename,
                    caption=caption,
                )
            elif content_type.startswith("image/"):
                await update.message.reply_photo(
                    photo=file_obj,
                    caption=caption,
                )
            else:
                await update.message.reply_document(
                    document=file_obj,
                    filename=filename,
                    caption=caption,
                )
            
            self.logger.info(f"📤 Sent file: {filename} ({len(file_bytes)} bytes)")
            
        except Exception as e:
            self.logger.error(f"Failed to send file: {e}")
            await status_msg.edit_text("❌ Gagal mengirim file. Coba lagi.")
    
    async def _send_chunked(
        self,
        update: Update,
        status_msg,
        text: str,
        max_len: int = 4000
    ) -> None:
        """Send long text in chunks."""
        chunks = []
        
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            
            break_point = text.rfind('\n', 0, max_len)
            if break_point < max_len // 2:
                break_point = text.rfind(' ', 0, max_len)
            if break_point < max_len // 2:
                break_point = max_len
            
            chunks.append(text[:break_point])
            text = text[break_point:].strip()
        
        # First chunk: edit status message
        first_chunk = chunks[0]
        try:
            await status_msg.edit_text(first_chunk, parse_mode="Markdown")
        except Exception:
            await status_msg.edit_text(first_chunk)
        
        # Remaining chunks: new messages
        for chunk in chunks[1:]:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(chunk)
    
    async def _handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle photo messages."""
        user = update.effective_user
        user_id = self.format_user_id(user.id)
        
        if not self.is_allowed(user_id):
            await update.message.reply_text("⛔ Not authorized.")
            return
        
        photo = update.message.photo[-1]  # Best quality
        
        try:
            file_obj = await context.bot.get_file(photo.file_id)
            filename = f"photo_{photo.file_unique_id}.jpg"
            relative_path = await self._download_file(file_obj, user_id, filename)
            
            self.logger.info(f"📷 Photo from [{user_id}] saved to: {relative_path}")
            
            # Read as base64
            full_path = os.path.join(WORKSPACE, relative_path)
            with open(full_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            file_context = f"[User sent an image which is now visible to you. The image is also saved at: {relative_path}]"
            await self._handle_message(update, context, file_context=file_context, images=[image_base64])
            
        except Exception as e:
            self.logger.error(f"Error handling photo from {user_id}: {e}")
            await update.message.reply_text("❌ Gagal memproses gambar. Coba lagi.")
    
    async def _handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle document messages."""
        user = update.effective_user
        user_id = self.format_user_id(user.id)
        
        if not self.is_allowed(user_id):
            await update.message.reply_text("⛔ Not authorized.")
            return
        
        doc = update.message.document
        
        if doc.file_size and doc.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("❌ File too large (max 20MB).")
            return
        
        try:
            file_obj = await context.bot.get_file(doc.file_id)
            filename = doc.file_name or f"file_{doc.file_unique_id}"
            relative_path = await self._download_file(file_obj, user_id, filename)
            
            self.logger.info(f"📎 Document from [{user_id}]: {relative_path} ({doc.mime_type})")
            
            # Check if image
            _, ext = os.path.splitext(filename.lower())
            is_image = ext in IMAGE_EXTENSIONS
            
            images = None
            if is_image:
                full_path = os.path.join(WORKSPACE, relative_path)
                with open(full_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
                images = [image_base64]
                file_context = f"[User sent an image file which is now visible to you. The image is also saved at: {relative_path}]"
            else:
                file_context = (
                    f"[User sent a file: {relative_path}]\n"
                    f"File type: {doc.mime_type or 'unknown'}\n"
                    f"Size: {doc.file_size} bytes\n"
                    f"The file has been saved to workspace. You can read it with read_file tool at path: {relative_path}"
                )
            
            await self._handle_message(update, context, file_context=file_context, images=images)
            
        except Exception as e:
            self.logger.error(f"Error handling document from {user_id}: {e}")
            await update.message.reply_text("❌ Gagal memproses file. Coba lagi.")
