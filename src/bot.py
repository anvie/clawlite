#!/usr/bin/env python3
"""
ClawLite - Telegram Bot
Lightweight agentic AI powered by Ollama with tool calling
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from .agent import run_agent

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
    if not is_allowed(update.effective_user.id):
        return
    
    from .tools import list_tools
    tools = list_tools()
    
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("⛔ Not authorized.")
        return
    
    user_message = update.message.text
    logger.info(f"📩 USER [{user.id}]: {user_message[:100]}...")
    
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
        # Run agent
        response, new_history = await run_agent(
            user_message,
            conversations[user.id],
            status_callback=update_status,
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


def main() -> None:
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN not set!")
        return
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("tools", tools_cmd))
    application.add_handler(CommandHandler("workspace", workspace_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    
    print(f"🚀 ClawLite started!")
    print(f"   Model: {ollama_model}")
    print(f"   Ollama: {ollama_host}")
    print(f"   Workspace: /workspace")
    print(f"   Tools: read_file, write_file, list_dir, exec, run_bash, run_python, list_processes, kill_process, search_files")
    logger.info("Bot ready")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
