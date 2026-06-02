# admin_handlers.py
import logging
import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes,CallbackContext
from telegram.error import TelegramError
from config import BotConfig
from core import bot_data
from bot_types import QueueItem
from functools import wraps


logger = logging.getLogger(__name__)

async def is_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if user is an admin."""
    try:
        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, user_id)
        return chat_member.status in ['administrator', 'creator']
    except TelegramError:
        return False

async def alert_admin(context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    """Send alert message to admin."""
    try:
        await context.bot.send_message(
            chat_id=BotConfig.ADMIN_ID,
            text=f"🚨 تنبيه إداري:\n{message}"
        )
    except TelegramError as e:
        logger.error(f"Failed to send alert to admin: {e}")


async def secret_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hidden help command that shows all available commands and their usage."""
    try:
        if not update.message:
            return
        
        is_admin_user = update.effective_user.id == BotConfig.ADMIN_ID
            
        # Build help text (basic for all, full for admin)
        basic_help_text = """
🤖 *MDJ Archive Bot*

*General Commands:*
• `/start` - Start the bot and get welcome message
• Send files directly to the bot to queue them
• Send 'تم' when done uploading to process files

*File Requirements:*
• Supported formats: {0}
• Max file size: {1}MB
• Files must start with subject code (e.g., `MGT-301`)
• Max files per queue: {2}
• Rate limit: {3} files/min per user
""".format(
            ", ".join(BotConfig.ALLOWED_FILE_TYPES),
            BotConfig.MAX_FILE_SIZE // (1024 * 1024),
            BotConfig.MAX_FILES_PER_USER_QUEUE,
            BotConfig.USER_RATE_LIMIT
        )

        admin_extra = """

*Admin Commands:*
• `/bup [user_id]` - Block user
• `/unbup [user_id]` - Unblock user
• `/updateserror` - View violation log
• `/delete [count]` - Delete multiple messages (reply to start)
• `/del` - Delete single message (reply to message)

*Stats & Logs:*
• `/stats`, `/lastupdates` - View statistics
• `/autostats` - Toggle automatic stats
• `/lastlog` - View last changelog
• `/autolog` - Toggle automatic changelogs
• `/sendlog` - Send manual changelog
• `/resetlog` - Reset changelog
"""

        help_text = basic_help_text + (admin_extra if is_admin_user else "")

        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        


    except Exception as e:
        logger.error(f"Error in secret help command: {e}")
        try:
            await update.message.reply_text("An error occurred while showing help.")
        except TelegramError:
            pass

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Block a user from using the bot."""
    if not await is_admin(context, update.message.from_user.id):
        await update.message.reply_text("عذرًا، هذا الأمر متاح للإداريين فقط.")
        return

    if not context.args:
        await update.message.reply_text("يرجى تحديد معرف المستخدم.")
        return

    try:
        target = context.args[0]
        user = await context.bot.get_chat(int(target) if target.isdigit() else target)
        
        bot_data.blocked_users.add(user.id)
        bot_data.save_data()
        
        await update.message.reply_text(f"تم حظر المستخدم {user.full_name} (ID: {user.id}).")
        
    except TelegramError as e:
        await update.message.reply_text(f"حدث خطأ: {str(e)}")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unblock a user."""
    if not await is_admin(context, update.message.from_user.id):
        await update.message.reply_text("عذرًا، هذا الأمر متاح للإداريين فقط.")
        return

    if not context.args:
        await update.message.reply_text("يرجى تحديد معرف المستخدم.")
        return

    try:
        target = context.args[0]
        user = await context.bot.get_chat(int(target) if target.isdigit() else target)
        
        if user.id in bot_data.blocked_users:
            bot_data.blocked_users.remove(user.id)
            bot_data.save_data()
            await update.message.reply_text(f"تم إلغاء حظر المستخدم {user.full_name}.")
        else:
            await update.message.reply_text(f"المستخدم {user.full_name} غير محظور.")
            
    except TelegramError as e:
        await update.message.reply_text(f"حدث خطأ: {str(e)}")

async def update_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update and display error log."""
    if not await is_admin(context, update.message.from_user.id):
        await update.message.reply_text("عذرًا، هذا الأمر متاح للإداريين فقط.")
        return

    error_log = "سجل المخالفات:\n\n"
    for user_id, violations in bot_data.user_violations.items():
        try:
            user = await context.bot.get_chat(user_id)
            error_log += f"المستخدم: {user.full_name} (ID: {user_id}) - عدد المخالفات: {violations}\n"
        except TelegramError:
            error_log += f"مستخدم غير معروف (ID: {user_id}) - عدد المخالفات: {violations}\n"

    if not bot_data.user_violations:
        error_log += "لا توجد مخالفات مسجلة."

    await context.bot.send_message(
        chat_id=BotConfig.GROUP_ID,
        text=error_log,
        message_thread_id=BotConfig.STATS_TOPIC_ID
    )

async def toggle_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle whether the user wants to be tagged in uploaded files."""
    user_id = update.effective_user.id
    
    if user_id in bot_data.show_tags:
        bot_data.show_tags.remove(user_id)
        await update.message.reply_text("تم إيقاف إظهار اسمك في الملفات المرفوعة.")
    else:
        bot_data.show_tags.add(user_id)
        await update.message.reply_text("تم تفعيل إظهار اسمك في الملفات المرفوعة.")
    
    bot_data.save_data()

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
