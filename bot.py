# bot.py
import os
import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Import and load environment variables ---
from dotenv import load_dotenv
load_dotenv() # Loads variables from .env file for local development

import database as db # Our new MongoDB database handler

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
API_URL = "https://premium.medicobhai.workers.dev/api"
FREE_USER_LIMIT = 10

# --- Logging Setup ---
# (Same as before)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Command Handlers ---
# (ALL COMMAND HANDLERS - start, status, add_premium, remove_premium - ARE EXACTLY THE SAME)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message when the /start command is issued."""
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id)
    
    status = "Premium User ✨ (Unlimited links)" if user_data.get('is_premium') else f"Free User 🆓 ({user_data.get('usage_count', 0)}/{FREE_USER_LIMIT} links used)"
    
    welcome_message = (
        f"👋 Welcome to the Terabox Downloader Bot!\n\n"
        f"Send me any Terabox link (video or folder) and I'll send you the direct download links.\n\n"
        f"👤 **Your Status:** {status}\n\n"
        f"Developed by @YourUsername" # Change this
    )
    await update.message.reply_text(welcome_message)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the user's current status."""
    user_id = update.effective_user.id
    user_data = db.get_or_create_user(user_id)
    
    if user_data.get('is_premium'):
        status_message = "✨ You are a **Premium User**.\nYou can convert unlimited links!"
    else:
        usage = user_data.get('usage_count', 0)
        remaining = FREE_USER_LIMIT - usage
        status_message = (
            f"🆓 You are a **Free User**.\n"
            f"You have used **{usage}** out of **{FREE_USER_LIMIT}** links.\n"
            f"You have **{remaining}** links remaining."
        )
    await update.message.reply_html(status_message)


async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to grant premium access to a user."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        target_user_id = int(context.args[0])
        db.set_premium_status(target_user_id, True)
        await update.message.reply_text(f"✅ User {target_user_id} has been granted premium access.")
        await context.bot.send_message(
            chat_id=target_user_id,
            text="Congratulations! You have been upgraded to a Premium User ✨. You now have unlimited conversions!"
        )
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /addpremium <user_id>")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")

async def remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to revoke premium access."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        target_user_id = int(context.args[0])
        db.set_premium_status(target_user_id, False)
        await update.message.reply_text(f"❌ Premium access for user {target_user_id} has been revoked.")
        await context.bot.send_message(
            chat_id=target_user_id,
            text="Your premium access has been revoked. You are now a free user."
        )
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /removepremium <user_id>")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")


# --- Core Logic ---
# (handle_message IS EXACTLY THE SAME, but with minor changes to use .get() for safety)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """The main handler for processing Terabox links."""
    message_text = update.message.text
    user_id = update.effective_user.id
    
    if "terabox.com" not in message_text:
        await update.message.reply_text("Please send a valid Terabox link.")
        return
        
    user_data = db.get_or_create_user(user_id)

    # Check usage limit for free users
    if not user_data.get('is_premium') and user_data.get('usage_count', 0) >= FREE_USER_LIMIT:
        await update.message.reply_text("🚫 You have reached your free limit of 10 links. Contact the admin for premium access.")
        return

    processing_message = await update.message.reply_text("🔎 Processing your link, please wait...")

    try:
        params = {'url': message_text}
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        api_data = response.json()

        if not api_data or not isinstance(api_data, list) or 'links' not in api_data[0]:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="❌ Failed to parse the link.")
            return

        download_links = api_data[0]['links']
        if not download_links:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text="❌ No downloadable files found.")
            return

        response_text = "✅ Success! Here are your direct download links:\n\n"
        for i, link_info in enumerate(download_links, 1):
            response_text += f"**{i}. {link_info.get('name', 'Unknown File')}**\n[Download Link]({link_info['url']})\n\n"
        
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
        await update.message.reply_markdown(response_text, disable_web_page_preview=True)

        if not user_data.get('is_premium'):
            db.increment_usage(user_id)

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while calling API: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text=f"❌ Network Error: Could not connect to the service.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=processing_message.message_id, text=f"❌ An unexpected error occurred.")

# --- Main function to run the bot ---
# (main() IS EXACTLY THE SAME)
def main():
    """Start the bot."""
    if not BOT_TOKEN or not ADMIN_ID:
        logger.error("BOT_TOKEN and ADMIN_ID environment variables are not set!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("addpremium", add_premium_command))
    application.add_handler(CommandHandler("removepremium", remove_premium_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()