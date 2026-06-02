# message_handlers.py
import logging
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from config import BotConfig
from core import QueueItem, queue_processor, bot_data
from status_handlers import start_status_updates
from bot_types import QueueItem  # Changed from types to bot_types

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    welcome_message = (
        "مرحبًا! أنا بوت لرفع الملفات.\n\n"
        "🔹 يمكنك رفع ملفات PDF أو PPT/PPTX.\n"
        "🔹 يجب أن يبدأ اسم الملف برمز المقرر (مثل MGT-301).\n"
        "🔹 يمكنك رفع عدة ملفات في آن واحد.\n"
        f"🔹 الحد الأقصى لحجم الملف هو {BotConfig.MAX_FILE_SIZE // (1024 * 1024)} ميجابايت.\n\n"
        "🔸 عندما تنتهي من رفع جميع الملفات، أرسل كلمة 'تم' لبدء المعالجة."
    )
    await update.message.reply_text(welcome_message)
async def sshelp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help4444iH4xz command."""
    if update.effective_user.id != BotConfig.ADMIN_ID:
            # Silently ignore if not admin
            await update.message.delete()
            return
    welcome_message = (
        """
🤖 *MDJ Archive Bot Commands Guide*

*General Commands:*
• `/start` - Start the bot and get welcome message
• Send files directly to bot to queue them
• Send 'تم' when done uploading to process files

*File Management:*
• `/s [subject-code]` - Sort a single file to correct subject topic (reply to file)
• `/ss [subject-code] [count]` - Bulk sort multiple files
• `/tagme` - Toggle your name being shown on uploaded files

*Admin Commands:*
• `/bup [user_id]` - Block user from using bot
• `/unbup [user_id]` - Unblock user
• `/updateserror` - View violation log
• `/delete [count]` - Delete multiple messages (reply to start)
• `/del` - Delete single message (reply to message)

*Stats & Logs:*
• `/stats` or `/lastupdates` - View current statistics
• `/autostats` - Toggle automatic stats updates
• `/lastlog` - View last changelog
• `/autolog` - Toggle automatic changelogs
• `/sendlog` - Send manual changelog
• `/resetlog` - Reset changelog

*Subject Codes:*
Examples: `ISLAM-101`, `MGT-301`, `STAT-101`, etc.

*File Requirements:*
• Supported formats: {0}
• Max file size: {1}MB
• Files must start with subject code
• Max files per queue: {2}
• Rate limit: {3} files per minute per user

*Notes:*
• Files are automatically sorted by subject code
• Unrecognized files go to general topic
• Blocked after 3 naming violations
"""
    )
    await update.message.reply_text(welcome_message)
async def validate_file(document, user_id: int) -> tuple[bool, str]:
    """
    Validate uploaded file with improved checks and logging.
    Returns: (is_valid, error_message)
    """
    try:
        # Check file extension
        if not document.file_name.lower().endswith(BotConfig.ALLOWED_FILE_TYPES):
            return False, "تنسيق الملف غير مدعوم"
        
        # Check file size
        if document.file_size > BotConfig.MAX_FILE_SIZE:
            return False, f"حجم الملف يتجاوز {BotConfig.MAX_FILE_SIZE // (1024 * 1024)} ميجابايت"
        
        # Check for bad words
        if any(word.lower() in document.file_name.lower() for word in BotConfig.BAD_WORDS):
            bot_data.user_violations[user_id] += 1
            violations = bot_data.user_violations[user_id]
            
            if violations >= 3:
                bot_data.blocked_users.add(user_id)
                bot_data.save_data()
                logger.warning(f"User {user_id} blocked for multiple violations")
                return False, "تم حظرك لتجاوز عدد المخالفات المسموح"
            
            bot_data.save_data()
            return False, "اسم الملف غير مناسب"
        
        return True, ""
        
    except Exception as e:
        logger.error(f"Error validating file: {e}")
        return False, "حدث خطأ أثناء التحقق من الملف"

async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded files silently."""
    user = update.message.from_user
    chat_id = update.effective_chat.id

    try:
        # Ignore files sent in the target group
        if chat_id == BotConfig.GROUP_ID:
            return
            
        # Check eligibility
        try:
            chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, user.id)
            if chat_member.status not in ['member', 'administrator', 'creator'] or user.id in bot_data.blocked_users:
                return
        except TelegramError:
            return

        # Get files
        files_to_process = []
        try:
            if update.message.document:
                files_to_process.append(update.message.document)
            elif update.message.media_group_id:
                media_group = await context.bot.get_media_group(chat_id, update.message.message_id)
                files_to_process = [
                    msg.document for msg in media_group 
                    if msg.document and msg.document.file_name.lower().endswith(BotConfig.ALLOWED_FILE_TYPES)
                ]
        except TelegramError:
            return

        # Queue valid files silently
        queued_files = 0
        for document in files_to_process:
            is_valid, _ = await validate_file(document, user.id)
            if is_valid:
                queue_item = QueueItem(context, document, user, chat_id)
                success, error_msg = await queue_processor.add_to_queue(queue_item)
                if success:
                    queued_files += 1
                elif error_msg:  # Show rate limit messages
                    await update.message.reply_text(error_msg)
                    return

        # Update status message if exists and files were queued
        if queued_files > 0 and user.id in bot_data.queue_status_messages:
            await start_status_updates(context, chat_id, user.id)

    except Exception as e:
        logger.error(f"Error handling files: {e}")

async def handle_done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the 'تم' command to start processing."""
    try:
        user = update.message.from_user
        chat_id = update.effective_chat.id

        # Check queue count using queue_processor 
        queue_count = queue_processor.get_user_queue_count(user.id)
        
        if queue_count == 0:
            msg = await update.message.reply_text("لا توجد ملفات في قائمة الانتظار.")
            await asyncio.sleep(4)
            await msg.delete()
            return

        # Start or update status message
        if user.id not in bot_data.queue_status_messages:
            status_message = await update.message.reply_text(
                f"جاري معالجة {queue_count} ملف..."
            )
            bot_data.queue_status_messages[user.id] = status_message.message_id
            await start_status_updates(context, chat_id, user.id)

        # Start processing
        await queue_processor.start_processing()

        # Delete command message after a delay
        await asyncio.sleep(4)
        await update.message.delete()

    except Exception as e:
        logger.error(f"Error handling done command: {e}")
        error_msg = await update.message.reply_text("حدث خطأ أثناء بدء المعالجة.")
        await asyncio.sleep(4)
        await error_msg.delete()

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
