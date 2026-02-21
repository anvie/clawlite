#!/usr/bin/env python3
"""
ClawLite - Telegram Bot
Lightweight agentic AI powered by Ollama with tool calling
"""

import os
import base64
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from .agent import run_agent

# Workspace path for file operations
WORKSPACE = os.getenv("WORKSPACE_PATH", "/workspace")

load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# Conversation history per user
conversations: dict[int, list[dict]] = {}

# Supported image extensions for vision
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


async def download_telegram_file(file_obj, user_id: int, filename: str) -> str:
    """Download a Telegram file to workspace/uploads/{user_id}/"""
    # Create upload directory
    upload_dir = os.path.join(WORKSPACE, "uploads", str(user_id))
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(filename)
    unique_filename = f"{name}_{timestamp}{ext}"
    
    file_path = os.path.join(upload_dir, unique_filename)
    
    # Download file
    await file_obj.download_to_drive(file_path)
    
    # Return relative path from workspace root
    return os.path.relpath(file_path, WORKSPACE)


def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS or ALLOWED_USERS == [""]:
        return True
    return str(user_id) in ALLOWED_USERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    
    logger.info(f"👋 /start from {user.id} ({user.username})")
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


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return
    conversations[user_id] = []
    logger.info(f"🗑️ Cleared history for {user_id}")
    await update.message.reply_text("🗑️ History cleared.")


async def tools_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return
    
    from .tools import list_tools
    tools = list_tools(user_id=user_id)
    
    text = "🔧 *Available Tools:*\n\n"
    for t in tools:
        text += f"• `{t['name']}` - {t['description']}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def workspace_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        return
    
    from .tools import get_tool
    tool = get_tool("list_dir")
    result = await tool.execute(path=".")
    
    if result.success:
        await update.message.reply_text(f"📁 *Workspace:*\n```\n{result.output}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Error: {result.error}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, file_context: str = None, images: list[str] = None) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    
    user_message = update.message.text or update.message.caption or ""
    
    # Prepend file context if provided
    if file_context:
        user_message = f"{file_context}\n\n{user_message}" if user_message else file_context
    
    if not user_message:
        await update.message.reply_text("❓ No message received.")
        return
    
    logger.info(f"📩 USER [{user.id}]: {user_message[:100]}{'(+image)' if images else ''}...")
    
    # Get or create history
    if user.id not in conversations:
        conversations[user.id] = []
    
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
    
    try:
        # Run agent with user_id for context and memory tools
        response, new_history = await run_agent(
            user_message,
            conversations[user.id],
            user_id=user.id,
            status_callback=update_status,
            images=images,
        )
        
        # Update history
        conversations[user.id] = new_history
        
        # Clean up response for display
        import re
        final_text = re.sub(r'<tool_?call>.*?</tool_?call>', '', response, flags=re.DOTALL | re.IGNORECASE)
        final_text = final_text.strip()
        
        if not final_text:
            await status_msg.edit_text("✅ Done!")
            return
        
        # Split into chunks if too long (Telegram limit is 4096)
        MAX_LEN = 4000
        chunks = []
        
        while final_text:
            if len(final_text) <= MAX_LEN:
                chunks.append(final_text)
                break
            
            # Find a good break point (newline or space)
            break_point = final_text.rfind('\n', 0, MAX_LEN)
            if break_point < MAX_LEN // 2:
                break_point = final_text.rfind(' ', 0, MAX_LEN)
            if break_point < MAX_LEN // 2:
                break_point = MAX_LEN
            
            chunks.append(final_text[:break_point])
            final_text = final_text[break_point:].strip()
        
        # Send first chunk by editing status message
        first_chunk = chunks[0]
        try:
            await status_msg.edit_text(first_chunk, parse_mode="Markdown")
        except Exception:
            await status_msg.edit_text(first_chunk)
        
        # Send remaining chunks as new messages
        for chunk in chunks[1:]:
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                await update.message.reply_text(chunk)
            
    except Exception as e:
        logger.error(f"Error for user {user.id}: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)[:500]}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages."""
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    
    # Get the largest photo (best quality)
    photo = update.message.photo[-1]
    
    try:
        # Download photo
        file_obj = await context.bot.get_file(photo.file_id)
        filename = f"photo_{photo.file_unique_id}.jpg"
        relative_path = await download_telegram_file(file_obj, user.id, filename)
        
        logger.info(f"📷 Photo from [{user.id}] saved to: {relative_path}")
        
        # Read image as base64 for multimodal LLM
        full_path = os.path.join(WORKSPACE, relative_path)
        with open(full_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
        
        # Create file context for the agent
        file_context = f"[User sent an image which is now visible to you. The image is also saved at: {relative_path}]"
        
        # Process with agent (with image for vision)
        await handle_message(update, context, file_context=file_context, images=[image_base64])
        
    except Exception as e:
        logger.error(f"Error handling photo from {user.id}: {e}")
        await update.message.reply_text(f"❌ Failed to process image: {str(e)[:200]}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document/file messages."""
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    
    doc = update.message.document
    
    # Size limit: 20MB
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File too large (max 20MB).")
        return
    
    try:
        # Download document
        file_obj = await context.bot.get_file(doc.file_id)
        filename = doc.file_name or f"file_{doc.file_unique_id}"
        relative_path = await download_telegram_file(file_obj, user.id, filename)
        
        logger.info(f"📎 Document from [{user.id}] saved to: {relative_path} ({doc.mime_type})")
        
        # Check if it's an image
        _, ext = os.path.splitext(filename.lower())
        is_image = ext in IMAGE_EXTENSIONS
        
        images = None
        if is_image:
            # Read image as base64 for multimodal LLM
            full_path = os.path.join(WORKSPACE, relative_path)
            with open(full_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            images = [image_base64]
            file_context = f"[User sent an image file which is now visible to you. The image is also saved at: {relative_path}]"
        else:
            file_context = f"[User sent a file: {relative_path}]\nFile type: {doc.mime_type or 'unknown'}\nSize: {doc.file_size} bytes\nThe file has been saved to workspace. You can read it with read_file tool at path: {relative_path}"
        
        # Process with agent
        await handle_message(update, context, file_context=file_context, images=images)
        
    except Exception as e:
        logger.error(f"Error handling document from {user.id}: {e}")
        await update.message.reply_text(f"❌ Failed to process file: {str(e)[:200]}")


def main() -> None:
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN not set!")
        return
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("tools", tools_cmd))
    application.add_handler(CommandHandler("workspace", workspace_cmd))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    
    print(f"🚀 ClawLite started!")
    if llm_provider == "openrouter":
        model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        print(f"   Provider: OpenRouter")
        print(f"   Model: {model}")
    else:
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        print(f"   Provider: Ollama")
        print(f"   Model: {ollama_model}")
        print(f"   Host: {ollama_host}")
    print(f"   Workspace: /workspace")
    logger.info("Bot ready")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
