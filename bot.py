# bot.py
import os
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Import and load environment variables ---
from dotenv import load_dotenv
load_dotenv()

import database as db

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
API_URL = "https://premium.medicobhai.workers.dev/api"
FREE_USER_LIMIT = 10
PORT = int(os.environ.get('PORT', 8080)) # Port for Render web service

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask Web Server Setup ---
# This part is to keep the Render service alive.
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    """Render health check endpoint."""
    return "Bot is alive and running!", 200

def run_web_server():
    """Starts the Flask web server."""
    web_app.run(host='0.0.0.0', port=PORT)

# --- Bot Command and Message Handlers ---
# ALL YOUR BOT HANDLERS (start_command, status_command, add_premium_command,
# remove_premium_command, handle_message) GO HERE.
# THEY ARE EXACTLY THE SAME AS THE PREVIOUS MONGODB VERSION.
# ... (Copy and paste all the async def functions from the previous response here) ...

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id)
    status = "Premium User ✨ (Unlimited)" if user_data.get('is_premium') else f"Free User 🆓 ({user_data.get('usage_count', 0)}/{FREE_USER_LIMIT} used)"
    welcome_message = (f"👋 Welcome!\n\nSend me any Terabox link.\n\n👤 **Status:** {status}")
    await update.message.reply_text(welcome_message)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id)
    if user_data.get('is_premium'):
        status_message = "✨ You are a **Premium User**.\nUnlimited conversions!"
    else:
        usage = user_data.get('usage_count', 0)
        remaining = FREE_USER_LIMIT - usage
        status_message = (f"🆓 You are a **Free User**.\nUsed: **{usage}/{FREE_USER_LIMIT}**\nRemaining: **{remaining}**")
    await update.message.reply_html(status_message)

async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_user_id = int(context.args[0])
        db.set_premium_status(target_user_id, True)
        await update.message.reply_text(f"✅ User {target_user_id} is now premium.")
        await context.bot.send_message(chat_id=target_user_id, text="Congratulations! You are now a Premium User ✨.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /addpremium <user_id>")

async def remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        target_user_id = int(context.args[0])
        db.set_premium_status(target_user_id, False)
        await update.message.reply_text(f"❌ Premium for user {target_user_id} revoked.")
        await context.bot.send_message(chat_id=target_user_id, text="Your premium access has been revoked.")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /removepremium <user_id>")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    user_id = update.effective_user.id
    if "terabox.com" not in message_text:
        await update.message.reply_text("Please send a valid Terabox link.")
        return
    user_data = db.get_or_create_user(user_id)
    if not user_data.get('is_premium') and user_data.get('usage_count', 0) >= FREE_USER_LIMIT:
        await update.message.reply_text("🚫 Free limit reached. Contact admin for premium.")
        return
    processing_message = await update.message.reply_text("🔎 Processing...")
    try:
        response = requests.get(API_URL, params={'url': message_text})
        response.raise_for_status()
        api_data = response.json()
        download_links = api_data[0]['links']
        if not download_links:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="❌ No files found.")
            return
        response_text = "✅ Success! Links:\n\n"
        for i, link_info in enumerate(download_links, 1):
            response_text += f"**{i}. {link_info.get('name', 'File')}**\n[Download]({link_info['url']})\n\n"
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
        await update.message.reply_markdown(response_text, disable_web_page_preview=True)
        if not user_data.get('is_premium'):
            db.increment_usage(user_id)
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="❌ An error occurred.")

# --- Main application runner ---
def main():
    """Set up and run the bot and web server."""
    if not BOT_TOKEN or not ADMIN_ID:
        logger.error("BOT_TOKEN and ADMIN_ID environment variables must be set!")
        return

    # Create the Telegram bot application
    application = Application.builder().token(BOT_TOKEN).build()

    # Register all command and message handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("addpremium", add_premium_command))
    application.add_handler(CommandHandler("removepremium", remove_premium_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # --- Run Bot and Web Server in parallel threads ---
    
    # Start the Flask web server in a separate thread
    web_thread = threading.Thread(target=run_web_server)
    web_thread.start()
    logger.info(f"Flask web server started on port {PORT}")

    # Start the bot's polling loop
    logger.info("Starting bot polling...")
    application.run_polling()


if __name__ == '__main__':
    main()