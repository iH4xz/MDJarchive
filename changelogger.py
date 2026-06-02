# changelogger.py
import os
import re
import logging
import asyncio
from datetime import datetime, timedelta
import pytz
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from telegram.error import TelegramError, BadRequest
from config import BotConfig
from core import bot_data  # Changed from Bot_Data to bot_data (instance)
from admin_handlers import alert_admin

logger = logging.getLogger(__name__)
WAITING_MESSAGE = 1
temp_messages = {}

# Callback data
CONFIRM = 'confirm'
CANCEL = 'cancel'
class ChangeLogger:
    def __init__(self):
        self.last_position = 0
        self.last_check_time = datetime.now()
        self.log_file = 'logs/bot.log'  # Simplified path

    def get_ksa_time(self) -> str:
        """Get current KSA time in 12-hour format."""
        ksa_tz = pytz.timezone('Asia/Riyadh')
        now = datetime.now(ksa_tz)
        return now.strftime("%Y-%m-%d %I:%M %p")

    async def parse_log_entries(self):
        """Parse log file for new file uploads and count them by subject."""
        upload_counts = defaultdict(int)
        new_entries = False

        try:
            if not os.path.exists(self.log_file):
                await alert_admin(None, f"ملف السجل غير موجود: {self.log_file}")
                return None

            with open(self.log_file, 'r', encoding='utf-8') as f:
                try:
                    f.seek(self.last_position)
                except (IOError, ValueError):
                    self.last_position = 0
                    f.seek(0)
                
                for line in f:
                    # Look for file activities
                    if "File moved from topic" in line:
                        new_entries = True
                        match = re.search(r"to topic (\d+)", line)
                        if match:
                            topic_id = match.group(1)
                            # Find subject code
                            subject = "ملفات أخرى"
                            for code, tid in BotConfig.VALID_SUBJECTS.items():
                                if str(tid) == str(topic_id):
                                    subject = code
                                    break
                            upload_counts[subject] += 1
                
                # Update position
                self.last_position = f.tell()
                self.last_check_time = datetime.now()

        except Exception as e:
            await alert_admin(None, f"خطأ في قراءة ملف السجل: {str(e)}")
            self.last_position = 0
            return None

        return upload_counts if new_entries else None

    def format_changelog(self, upload_counts: dict) -> str:
        """Format upload counts into a readable changelog."""
        ksa_time = self.get_ksa_time()
        
        message = f"📋 تقرير نشاط الملفات\n"
        message += f"📅 {ksa_time}\n"
        message += "━━━━━━━━━━━━━━\n\n"

        total_files = sum(upload_counts.values())
        message += f"📊 إجمالي النشاط: {total_files}\n\n"

        sorted_subjects = sorted(
            upload_counts.items(),
            key=lambda x: (-x[1], x[0])
        )

        for subject, count in sorted_subjects:
            message += f"📚 {subject}: {count} ملف\n"

        return message

    async def send_changelog(self, context: ContextTypes.DEFAULT_TYPE):
        """Send changelog to channel if there are new uploads."""
        try:
            upload_counts = await self.parse_log_entries()
            
            if upload_counts:
                message = self.format_changelog(upload_counts)
                
                try:
                    await context.bot.send_message(
                        chat_id=BotConfig.CHANGELOG_CHANNEL_ID,
                        text=message,
                        disable_notification=True
                    )
                    logger.info(f"تم إرسال التقرير في {self.get_ksa_time()}")
                except TelegramError as e:
                    await alert_admin(context, f"فشل إرسال التقرير للقناة: {str(e)}")

        except Exception as e:
            await alert_admin(context, f"خطأ في إرسال التقرير: {str(e)}")
    async def reset_log(self, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
        """Reset the log file and update last position."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            
            # Reset file
            with open(self.log_file, 'w', encoding='utf-8') as f:
                pass
            
            self.last_position = 0
            logger.info(f"Log file reset successfully: {self.log_file}")
            return True, "تم إعادة ضبط السجل بنجاح."
            
        except Exception as e:
            logger.error(f"Error resetting log file: {e}", exc_info=True)
            return False, "حدث خطأ أثناء إعادة ضبط السجل."
async def toggle_auto_changelog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle automatic changelog service."""
    try:
        # Check if admin
        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, update.effective_user.id)
        if chat_member.status not in ['administrator', 'creator']:
            msg = await update.message.reply_text("عذراً، هذا الأمر متاح للإداريين فقط.")
            await asyncio.sleep(4)
            await update.message.delete()
            await msg.delete()
            return

        # Toggle state
        bot_data.auto_changelog = not bot_data.auto_changelog
        bot_data.save_data()
        
        status = "تفعيل" if bot_data.auto_changelog else "تعطيل"
        msg = await update.message.reply_text(f"✅ تم {status} التقارير التلقائية.")
        
        await asyncio.sleep(4)
        await update.message.delete()
        await msg.delete()

    except Exception as e:
        await alert_admin(context, f"خطأ في تبديل حالة التقارير التلقائية: {str(e)}")
        error_msg = await update.message.reply_text("حدث خطأ. الرجاء المحاولة مرة أخرى.")
        await asyncio.sleep(4)
        await update.message.delete()
        await error_msg.delete()



async def handle_reset_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /resetlog command."""
    try:
        # Check if admin
        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, update.effective_user.id)
        if chat_member.status not in ['administrator', 'creator']:
            msg = await update.message.reply_text("عذراً، هذا الأمر متاح للإداريين فقط.")
            await asyncio.sleep(4)
            await update.message.delete()
            await msg.delete()
            return

        # Reset log
        changelog = ChangeLogger()
        success, message = await changelog.reset_log(context)
        
        # Send response
        msg = await update.message.reply_text(message)
        
        # Delete messages after delay
        await asyncio.sleep(4)
        await update.message.delete()
        await msg.delete()

        if success:
            admin_alert_message = f"تم مسح سجل البوت بواسطة {update.effective_user.full_name}"
            await alert_admin(context, admin_alert_message)

    except Exception as e:
        logger.error(f"Error in handle_reset_log: {e}", exc_info=True)


async def run_changelog_service(application):
    """Run the changelog service."""
    changelog = ChangeLogger()
    
    while True:
        try:
            # Only run if auto_changelog is enabled
            if application.bot_data.get('auto_changelog', False):
                await changelog.send_changelog(application)
            await asyncio.sleep(BotConfig.CHANGELOG_INTERVAL)
        except Exception as e:
            logger.error(f"Error in changelog service: {e}")
            await asyncio.sleep(60)


async def start_custom_changelog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the custom changelog process."""
    try:
        # Check if admin and in private chat
        if update.effective_chat.type != 'private':
            await update.message.reply_text("هذا الأمر متاح فقط في المحادثة الخاصة مع البوت.")
            return ConversationHandler.END

        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, update.effective_user.id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text("عذراً، هذا الأمر متاح للإداريين فقط.")
            return ConversationHandler.END

        await update.message.reply_text(
            "أرسل التحديث الذي تريد إضافته للسجل.\n"
            "يمكنك استخدام تنسيق Markdown للنص.\n\n"
            "مثال:\n"
            "تم إضافة مقرر جديد *MGT-430*\n"
            "تم تحديث روابط المقررات"
        )
        
        return WAITING_MESSAGE

    except Exception as e:
        logger.error(f"Error in start_custom_changelog: {e}")
        await update.message.reply_text("حدث خطأ. الرجاء المحاولة مرة أخرى.")
        return ConversationHandler.END
async def send_manual_changelog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /sendlog command to manually send changelog regardless of interval."""
    try:
        # Check if admin
        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, update.effective_user.id)
        if chat_member.status not in ['administrator', 'creator']:
            msg = await update.message.reply_text("عذراً، هذا الأمر متاح للإداريين فقط.")
            await asyncio.sleep(4)
            await update.message.delete()
            await msg.delete()
            return

        changelog = ChangeLogger()
        # Reset last check time to force new reading
        changelog.last_check_time = datetime.now() - timedelta(hours=3)  # Force check by setting time back
        
        try:
            upload_counts = await changelog.parse_log_entries()
            
            if upload_counts:
                message = changelog.format_changelog(upload_counts)
                
                await context.bot.send_message(
                    chat_id=BotConfig.CHANGELOG_CHANNEL_ID,
                    text=message,
                    disable_notification=True
                )
                
                confirm_msg = await update.message.reply_text("✅ تم إرسال التقرير للقناة.")
                
            else:
                confirm_msg = await update.message.reply_text("لا توجد نشاطات جديدة لإنشاء تقرير.")

            # Delete messages after 4 seconds
            await asyncio.sleep(4)
            await update.message.delete()
            await confirm_msg.delete()

        except Exception as e:
            error_msg = await update.message.reply_text("❌ حدث خطأ أثناء إرسال التقرير.")
            await alert_admin(context, f"خطأ في إرسال التقرير اليدوي: {str(e)}")
            
            await asyncio.sleep(4)
            await update.message.delete()
            await error_msg.delete()

    except Exception as e:
        await alert_admin(context, f"خطأ في معالجة أمر التقرير اليدوي: {str(e)}")
        error_msg = await update.message.reply_text("حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.")
        
        await asyncio.sleep(4)
        await update.message.delete()
        await error_msg.delete()
async def handle_changelog_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the received changelog message."""
    try:
        user_id = update.effective_user.id
        temp_messages[user_id] = update.message.text
        
        # Create preview message
        ksa_time = ChangeLogger().get_ksa_time()
        preview = (
            "📋 مراجعة التحديث\n"
            f"📅 {ksa_time}\n"
            "━━━━━━━━━━━━━━\n\n"
            f"{update.message.text}\n\n"
            "هل تريد إرسال هذا التحديث؟"
        )

        # Add confirmation buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ إرسال", callback_data=CONFIRM),
                InlineKeyboardButton("❌ إلغاء", callback_data=CANCEL)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            preview,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in handle_changelog_message: {e}")
        await update.message.reply_text("حدث خطأ. الرجاء المحاولة مرة أخرى.")
        return ConversationHandler.END

async def handle_changelog_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks for changelog confirmation."""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        message = temp_messages.get(user_id)

        if not message:
            await query.edit_message_text("انتهت صلاحية التحديث. الرجاء المحاولة مرة أخرى.")
            return

        if query.data == CONFIRM:
            # Format and send the changelog
            ksa_time = ChangeLogger().get_ksa_time()
            changelog_message = (
                "📋 تحديث النظام\n"
                f"📅 {ksa_time}\n"
                "━━━━━━━━━━━━━━\n\n"
                f"{message}\n\n"
                f"👤 بواسطة: {update.effective_user.full_name}"
            )

            await context.bot.send_message(
                chat_id=BotConfig.CHANGELOG_CHANNEL_ID,
                text=changelog_message,
                parse_mode='Markdown'
            )
            
            await query.edit_message_text("✅ تم إرسال التحديث بنجاح.")
            
        else:  # CANCEL
            await query.edit_message_text("❌ تم إلغاء التحديث.")

        # Clean up
        if user_id in temp_messages:
            del temp_messages[user_id]

    except Exception as e:
        logger.error(f"Error in handle_changelog_button: {e}")
        await query.edit_message_text("حدث خطأ. الرجاء المحاولة مرة أخرى.")

# Create conversation handler
changelog_conv_handler = ConversationHandler(
    entry_points=[CommandHandler('addlog', start_custom_changelog)],
    states={
        WAITING_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_changelog_message)],
    },
    fallbacks=[],
)

async def handle_last_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /lastlog command to manually get the latest changelog."""
    try:
        # Check if user is admin
        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, update.effective_user.id)
        if chat_member.status not in ['administrator', 'creator']:
            msg = await update.message.reply_text("عذراً، هذا الأمر متاح للإداريين فقط.")
            await asyncio.sleep(4)
            await update.message.delete()
            await msg.delete()
            return

        # Create changelog instance
        changelog = ChangeLogger()
        upload_counts = await changelog.parse_log_entries()

        if upload_counts:
            message = changelog.format_changelog(upload_counts)
            
            try:
                # Send to channel
                await context.bot.send_message(
                    chat_id=BotConfig.CHANGELOG_CHANNEL_ID,
                    text=message,
                    disable_notification=True
                )
                
                # Confirm to admin
                confirm_msg = await update.message.reply_text("✅ تم إرسال التقرير للقناة.")
                await asyncio.sleep(4)
                await update.message.delete()
                await confirm_msg.delete()
                
            except Exception as e:
                error_msg = await update.message.reply_text("❌ حدث خطأ أثناء إرسال التقرير.")
                logger.error(f"Error sending manual changelog: {e}", exc_info=True)
                await asyncio.sleep(4)
                await update.message.delete()
                await error_msg.delete()
        else:
            msg = await update.message.reply_text("لا توجد نشاطات جديدة منذ آخر تقرير.")
            await asyncio.sleep(4)
            await update.message.delete()
            await msg.delete()

    except Exception as e:
        logger.error(f"Error in handle_last_log: {e}", exc_info=True)
        error_msg = await update.message.reply_text("حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.")
        await asyncio.sleep(4)
        await update.message.delete()
        await error_msg.delete()

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
