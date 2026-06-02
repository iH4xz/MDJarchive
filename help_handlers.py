# help_handlers.py
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import BotConfig

logger = logging.getLogger(__name__)

async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin help. If caller isn't admin, fall back to public help."""
    if not update.message:
        return

    is_admin_user = update.effective_user and update.effective_user.id == BotConfig.ADMIN_ID
    if not is_admin_user:
        # In groups: try to delete the non-admin command message silently
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    text = """
🤖 *MDJ Archive Bot — Admin Help*

*Admin Commands:*
• `/bup [user_id]` - Block user
• `/unbup [user_id]` - Unblock user
• `/updateserror` - View violation log
• `/delete [count]` - Delete multiple messages (reply to start)
• `/del` - Delete single message (reply to message)

*Sorting:*
• `/s [subject-code]` - Sort a single file (reply to file)
• `/ss [subject-code] [count]` - Bulk sort multiple files

*Stats & Logs:*
• `/stats`, `/lastupdates` - View statistics
• `/autostats` - Toggle automatic stats
• `/lastlog` - View last changelog
• `/autolog` - Toggle automatic changelogs
• `/sendlog` - Send manual changelog
• `/resetlog` - Reset changelog

*File Requirements:*
• Supported formats: {0}
• Max file size: {1}MB
• Max files per queue: {2}
• Rate limit: {3} files/min per user
""".format(
        ", ".join(BotConfig.ALLOWED_FILE_TYPES),
        BotConfig.MAX_FILE_SIZE // (1024 * 1024),
        BotConfig.MAX_FILES_PER_USER_QUEUE,
        BotConfig.USER_RATE_LIMIT
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
