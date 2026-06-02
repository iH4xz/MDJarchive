# status_handlers.py
import logging
import asyncio
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from config import BotConfig
from core import bot_data, queue_processor
from admin_handlers import alert_admin

logger = logging.getLogger(__name__)

async def handle_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle manual stats request."""
    if not context.application.bot_data.get('auto_stats', False):
        await run_periodic_tasks(context)

async def run_periodic_tasks(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run periodic stats tasks."""
    try:
        # Check if stats are enabled
        if not context.application.bot_data.get('auto_stats', False):
            return

        await log_statistics(context)

    except Exception as e:
        logger.error(f"Error in periodic stats: {e}")
        await alert_admin(context, f"خطأ في التحديث الدوري للإحصائيات: {str(e)}")

async def run_changelog_service(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run changelog service."""
    try:
        # Check if changelog is enabled
        if not context.application.bot_data.get('auto_changelog', False):
            return

        from changelogger import ChangeLogger
        changelog = ChangeLogger()
        await changelog.send_changelog(context)

    except Exception as e:
        logger.error(f"Error in changelog service: {e}")
        await alert_admin(context, f"خطأ في خدمة سجل التغييرات: {str(e)}")

async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in updates."""
    logger.error("Update %s caused error: %s", update, context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "عذراً، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقاً."
            )
    except:
        pass

    # Notify admin
    await alert_admin(context, f"🚨 خطأ في تحديث:\n{update}\n\nالخطأ:\n{context.error}")


def get_ksa_time() -> datetime:
    """Get current time in KSA timezone."""
    ksa_tz = pytz.timezone('Asia/Riyadh')
    return datetime.now(ksa_tz)

def format_ksa_time(dt: datetime) -> str:
    """Format time in 12-hour format with AM/PM."""
    return dt.strftime("%I:%M:%S %p")

def format_time_remaining(seconds: float) -> str:
    """Format remaining time in Arabic."""
    if seconds < 60:
        return f"{int(seconds)} ثانية"
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if remaining_seconds == 0:
        return f"{minutes} دقيقة"
    return f"{minutes} دقيقة و {remaining_seconds} ثانية"

async def generate_stats_message(context: ContextTypes.DEFAULT_TYPE, admin_name: str = None) -> str:
    """Generate comprehensive statistics message."""
    now = get_ksa_time()
    current_time = format_ksa_time(now)
    
    # Get top users and sort by upload count
    top_users = sorted(
        bot_data.user_uploads.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    # Build basic stats
    stats = (
        f"📊 إحصائيات النظام\n"
        f"━━━━━━━━━━━━━━\n"
        f"📅 التاريخ: {now.strftime('%Y-%m-%d')}\n"
        f"⏰ الوقت: {current_time}\n\n"
        f"📈 الإحصائيات العامة:\n"
        f"• إجمالي الملفات المرفوعة: {bot_data.total_files}\n"
        f"• عدد المستخدمين النشطين: {len(bot_data.user_uploads)}\n"
    )

    # Add queue statistics if there are files in queue
    total_queued = queue_processor.queue.qsize()
    if total_queued > 0:
        active_users = sum(1 for count in bot_data.user_queue_counts.values() if count > 0)
        stats += (
            f"\n📋 حالة قائمة الانتظار:\n"
            f"• الملفات قيد المعالجة: {total_queued}\n"
            f"• المستخدمين في الانتظار: {active_users}\n"
        )

    # Add top users section
    if top_users:
        stats += f"\n🏆 أفضل المستخدمين نشاطاً:\n"
        for i, (user_id, count) in enumerate(top_users, 1):
            try:
                user = await context.bot.get_chat_member(BotConfig.GROUP_ID, user_id)
                user_name = user.user.full_name
                if i == 1:
                    stats += f"🥇 {user_name}: {count} ملف\n"
                elif i == 2:
                    stats += f"🥈 {user_name}: {count} ملف\n"
                elif i == 3:
                    stats += f"🥉 {user_name}: {count} ملف\n"
                else:
                    stats += f"• {user_name}: {count} ملف\n"
            except TelegramError:
                continue

    # Add violations if any exist
    if bot_data.user_violations:
        violation_count = len(bot_data.user_violations)
        blocked_count = len(bot_data.blocked_users)
        stats += (
            f"\n⚠️ إحصائيات المخالفات:\n"
            f"• عدد المخالفات المسجلة: {violation_count}\n"
            f"• المستخدمين المحظورين: {blocked_count}\n"
        )

    # Add source and timestamp
    stats += f"\n━━━━━━━━━━━━━━"
    if admin_name:
        stats += f"\n👤 تم طلب التقرير بواسطة: {admin_name}"
    else:
        stats += f"\n🤖 تحديث تلقائي - {current_time}"

    return stats

async def start_status_updates(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    """Start or continue status updates for a user."""
    if user_id in bot_data.queue_status_tasks:
        return

    async def update_status():
        try:
            message_id = bot_data.queue_status_messages[user_id]
            initial_count = bot_data.user_queue_counts[user_id]
            
            while bot_data.user_queue_counts[user_id] > 0:
                try:
                    current_time = format_ksa_time(get_ksa_time())
                    remaining_files = bot_data.user_queue_counts[user_id]
                    processed_files = initial_count - remaining_files
                    total_queue = queue_processor.queue.qsize()
                    
                    # Estimate remaining time
                    estimated_time = remaining_files * BotConfig.FILE_PROCESS_DELAY
                    time_remaining = format_time_remaining(estimated_time)
                    
                    status_text = (
                        f"📊 حالة معالجة الملفات\n\n"
                        f"🕒 آخر تحديث: {current_time}\n"
                        f"📤 تمت معالجة: {processed_files} من {initial_count}\n"
                        f"📁 الملفات المتبقية: {remaining_files}\n"
                        f"⏳ الوقت المتبقي المقدر: {time_remaining}\n"
                        f"📥 إجمالي الملفات في قائمة الانتظار: {total_queue}\n\n"
                        "♻️ يتم تحديث هذه الرسالة كل 10 ثواني..."
                    )

                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=status_text
                    )

                except TelegramError as e:
                    logger.error(f"Error updating status message: {e}")

                await asyncio.sleep(10)  # Update every 10 seconds

            # Send completion message
            completion_time = format_ksa_time(get_ksa_time())
            final_message = (
                "✅ تم الانتهاء من معالجة جميع الملفات بنجاح!\n\n"
                f"📊 تمت معالجة: {initial_count} ملف(ات)\n"
                f"🕒 وقت الانتهاء: {completion_time}"
            )
            
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=final_message
            )

        except Exception as e:
            logger.error(f"Error in status updates: {e}")
        finally:
            # Cleanup
            if user_id in bot_data.queue_status_messages:
                del bot_data.queue_status_messages[user_id]
            if user_id in bot_data.queue_status_tasks:
                del bot_data.queue_status_tasks[user_id]

    # Create and store the status update task
    task = asyncio.create_task(update_status())
    bot_data.queue_status_tasks[user_id] = task

async def log_statistics(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log statistics to the group periodically."""
    try:
        stats_message = await generate_stats_message(context)
        
        try:
            await context.bot.send_message(
                chat_id=BotConfig.GROUP_ID,
                text=stats_message,
                message_thread_id=BotConfig.STATS_TOPIC_ID
            )
            logger.info("Statistics logged successfully")
        except BadRequest:
            await context.bot.send_message(
                chat_id=BotConfig.GROUP_ID,
                text=stats_message
            )
            logger.info("Statistics logged to main group (topic not found)")
        
        bot_data.save_data()
        
    except Exception as e:
        logger.error(f"Error logging statistics: {e}")
        try:
            from admin_handlers import alert_admin
            await alert_admin(context, f"⚠️ خطأ في تحديث الإحصائيات:\n{str(e)}")
        except:
            pass

async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for the bot."""
    logger.error(f"Update {update} caused error: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "عذراً، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقاً."
            )
    except:
        pass

    try:
        from admin_handlers import alert_admin
        await alert_admin(
            context,
            f"🚨 خطأ في تحديث:\n{update}\n\nالخطأ:\n{context.error}"
        )
    except:
        pass

async def toggle_auto_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle automatic statistics updates."""
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
        bot_data.auto_stats = not bot_data.auto_stats
        bot_data.save_data()
        
        status = "تفعيل" if bot_data.auto_stats else "تعطيل"
        msg = await update.message.reply_text(f"✅ تم {status} التحديثات التلقائية للإحصائيات.")
        
        await asyncio.sleep(4)
        await update.message.delete()
        await msg.delete()

    except Exception as e:
        error_msg = await update.message.reply_text("حدث خطأ. الرجاء المحاولة مرة أخرى.")
        logger.error(f"Error toggling auto stats: {e}")
        await asyncio.sleep(4)
        await update.message.delete()
        await error_msg.delete()

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
