# bot.py
import asyncio
from datetime import datetime,timedelta
import pytz
import threading
from telegram import  Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler
)

# Import configurations and core
from config import BotConfig, setup_logging

# Import core functionality
from core import initialize_bot_data, queue_processor,QueueItem,RateLimiter,BotData,QueueProcessor

# Import handlers
from message_handlers import (
    start_command,
    handle_files, 
    handle_done_command
)
from admin_handlers import (
    block_user,
    unblock_user,
    update_errors,
    toggle_tag,
    alert_admin,secret_help_command
)
#from help_handlers import secret_help_command
from status_handlers import (
    log_statistics,
    handle_error,toggle_auto_stats
)
from delete_handlers import (
    delete_messages, 
    delete_single_message
)
from subjects_sorter import (
    sort_file,
    bulk_sort_files
)
# Import changelog functionality
from changelogger import (
    handle_reset_log,
    run_changelog_service,
    changelog_conv_handler,handle_changelog_button,
    handle_last_log,toggle_auto_changelog,
    send_manual_changelog
)
from help_handlers import (
    admin_help_command
)

# Setup logging
logger = setup_logging()

async def handle_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Wrapper for log_statistics to handle command properly."""
    await log_statistics(context)

async def start_queue_processor(app: Application) -> None:
    """Initialize the queue processor when the bot starts."""
    app.queue_processor = queue_processor
    app.queue_processor_task = asyncio.create_task(app.queue_processor.run())
    
    # Start changelog service here, after the event loop is running
    changelog_task = asyncio.create_task(run_changelog_service(app))
    app.changelog_task = changelog_task  # Store reference to prevent garbage collection
    
    logger.info("Queue processor and changelog service started")

async def run_periodic_tasks(application: Application):
    """Run periodic tasks."""
    while True:
        try:
            # Only run if auto_stats is enabled
            if application.bot_data.get('auto_stats', False):
                from status_handlers import log_statistics
                await log_statistics(application)
            await asyncio.sleep(BotConfig.STATS_UPDATE_INTERVAL)
        except Exception as e:
            logger.error(f"Error in periodic stats update: {e}")
            await asyncio.sleep(60)

def main() -> None:
    """Main function to initialize and run the bot."""
    try:
        logger.info("Initializing bot...")

        # Initialize bot data
        initialize_bot_data()
        
        # Create and configure the application with concurrency optimizations
        application = (
            Application.builder()
            .token(BotConfig.TOKEN)
            .concurrent_updates(True)  # Enables handling multiple updates concurrently
            .connection_pool_size(8)   # Optimize connection pool
            .get_updates_read_timeout(30.0)    # Use new timeout methods
            .get_updates_write_timeout(30.0)   # Use new timeout methods
            .get_updates_connect_timeout(30.0) # Use new timeout methods
            .build()
        )
        
        # Set bot data defaults with KSA time
        ksa_tz = pytz.timezone('Asia/Riyadh')
        current_time = datetime.now(ksa_tz).strftime("%Y-%m-%d %I:%M %p")
        
        application.bot_data.update({
            'auto_changelog': False,
            'auto_stats': False,
            'last_restart': current_time
        })

        # Log startup with KSA time
        logger.info(f"Bot initialized at {current_time} KSA")

        # Add command and message handlers
        application.add_handler(CommandHandler("start", start_command))
        # Admin-only hidden help (aliases). No public /help.
        application.add_handler(CommandHandler(["help4444iH4xz", "help4444ih4xz", "sshelp"], admin_help_command))

        # File handling with better filter
        application.add_handler(
            MessageHandler(
                (filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND,
                handle_files,
                block=False  # Non-blocking file handling
            )
        )
        application.add_handler(
            MessageHandler(
                filters.TEXT & filters.Regex(r'^تم$'),
                handle_done_command
            )
        )

        # Organize admin commands for better readability and handling
        admin_commands = {
            "bup": block_user,
            "unbup": unblock_user,
            "updateserror": update_errors,
            "delete": delete_messages,
            "del": delete_single_message,
            "tagme": toggle_tag,
            "resetlog": handle_reset_log,
            
        }

        # Add admin commands handlers
        for cmd, func in admin_commands.items():
            application.add_handler(CommandHandler(cmd, func))
            
        # Add feature handlers
        feature_commands = {
            "s": sort_file,
            "ss": bulk_sort_files,
            "lastlog": handle_last_log,
            "autolog": toggle_auto_changelog,
            "sendlog": send_manual_changelog,
            "autostats": toggle_auto_stats,
            "stats": handle_stats_command,
            "lastupdates": handle_stats_command
        }

        for cmd, func in feature_commands.items():
            application.add_handler(CommandHandler(cmd, func))

        # Add conversation and callback handlers
        application.add_handler(changelog_conv_handler)
        application.add_handler(CallbackQueryHandler(handle_changelog_button))

        # Error handler
        application.add_error_handler(handle_error)

        # Pre-run setup
        application.pre_run = start_queue_processor

        # Define job callbacks with error handling
        async def changelog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
            """Changelog job with proper bot_data access."""
            try:
                if context.application.bot_data.get('auto_changelog', False):
                    from status_handlers import run_changelog_service
                    await run_changelog_service(context)
                    
            except Exception as e:
                logger.error(f"Error in changelog job: {e}")
                await alert_admin(context, f"خطأ في مهمة التقارير التلقائية: {str(e)}")

        async def stats_job(context: ContextTypes.DEFAULT_TYPE) -> None:
            """Stats job with proper bot_data access."""
            try:
                if context.application.bot_data.get('auto_stats', False):
                    from status_handlers import run_periodic_tasks
                    await run_periodic_tasks(context)
            except Exception as e:
                logger.error(f"Error in stats job: {e}")
                await alert_admin(context, f"خطأ في مهمة الإحصائيات التلقائية: {str(e)}")
       
        # Add jobs with optimized intervals and error handling
        application.job_queue.run_repeating(
        callback=changelog_job,
        interval=BotConfig.CHANGELOG_INTERVAL,
        first=10.0,
        name="ChangelogJob"
)
        application.job_queue.run_repeating(
        callback=stats_job,
        interval=BotConfig.STATS_UPDATE_INTERVAL,
        first=30.0,
        name="StatsJob"
)

        logger.info(f"Bot starting... [Version {BotConfig.BOT_VERSION}]")
        logger.info(f"Start time: {current_time} KSA")

        # Start polling with proper configuration
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
        raise

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info(f"Bot stopped by user at {datetime.now(pytz.timezone('Asia/Riyadh')).strftime('%Y-%m-%d %I:%M %p')} KSA")
    except Exception as e:
        logger.critical(f"Bot crashed: {e}")
        raise

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
