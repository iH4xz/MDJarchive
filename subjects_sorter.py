# subjects_sorter.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from config import BotConfig
from core import bot_data
import asyncio  # Add if not already imported

logger = logging.getLogger(__name__)

async def is_admin_or_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Check if user is an admin or member."""
    try:
        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except TelegramError:
        return False

def validate_subject_code(subject_code: str) -> str:
    """
    Validate and normalize subject code.
    Returns normalized code if valid, None if invalid.
    """
    # Normalize to uppercase for comparison
    subject_code = subject_code.upper()
    
    # Check if it exists in valid subjects
    if subject_code in BotConfig.VALID_SUBJECTS_NORMALIZED:
        return subject_code
    
    return None
async def delete_messages_delayed(*messages, delay: int = 4):
    """Delete messages after specified delay."""
    await asyncio.sleep(delay)
    for message in messages:
        try:
            await message.delete()
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
async def sort_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /s command to resort files to correct subject topics."""
    try:
        # Check if user is member/admin
        if not await is_admin_or_member(context, update.effective_user.id):
            await update.message.reply_text("عذراً، يجب أن تكون عضواً في المجموعة لاستخدام هذا الأمر.")
            return

        # Check if command is a reply to a message
        if not update.message.reply_to_message:
            await update.message.reply_text("يجب الرد على الملف المراد تصنيفه باستخدام الأمر /s متبوعاً برمز المقرر.")
            return

        # Check if replied message contains a document
        if not update.message.reply_to_message.document:
            await update.message.reply_text("يجب الرد على ملف.")
            return

        # Get subject code from command
        if not context.args or len(context.args) != 1:
            await update.message.reply_text("الرجاء إدخال رمز المقرر بعد الأمر /s\nمثال: /s MGT-301")
            return

        # Validate subject code
        subject_code = validate_subject_code(context.args[0])
        if not subject_code:
            await update.message.reply_text("رمز المقرر غير صحيح. الرجاء التأكد من الرمز وإعادة المحاولة.")
            return

        # Get document details
        document = update.message.reply_to_message.document
        original_message = update.message.reply_to_message
        
        # Get new topic ID
        new_topic_id = BotConfig.VALID_SUBJECTS_NORMALIZED[subject_code]

        # Try to send to new topic
        try:
            # Preserve original caption if exists
            caption = original_message.caption if original_message.caption else None
            
            # Send to new topic
            new_message = await context.bot.send_document(
                chat_id=BotConfig.GROUP_ID,
                document=document.file_id,
                caption=caption,
                message_thread_id=int(new_topic_id)
            )

            if new_message:
                # Delete original message
                await original_message.delete()
                
                # Send confirmation and schedule deletion
                confirm_msg = await update.message.reply_text(
                    f"✅ تم نقل الملف إلى المقرر {subject_code} بنجاح."
                )
                
                # Schedule deletion of command and confirmation
                asyncio.create_task(delete_messages_delayed(
                    update.message,
                    confirm_msg
                ))
                
                logger.info(
                    f"File moved from topic {original_message.message_thread_id} "
                    f"to topic {new_topic_id} by user {update.effective_user.id}"
                )

        except BadRequest as e:
            await update.message.reply_text(f"حدث خطأ أثناء نقل الملف: {str(e)}")
            logger.error(f"Error moving file: {e}")

    except Exception as e:
        await update.message.reply_text("حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.")
        logger.error(f"Error in sort_file: {e}")

# Updated bulk_sort_files function for subjects_sorter.py

async def bulk_sort_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle the /ss command for bulk sorting files.
    Usage: /ss MGT-301 5 (will move the replied file and next 4 files)
    """
    try:
        # Check if user is admin
        chat_member = await context.bot.get_chat_member(BotConfig.GROUP_ID, update.effective_user.id)
        if chat_member.status not in ['administrator', 'creator']:
            return  # Silently ignore if not admin

        # Check if command is a reply to a message
        if not update.message.reply_to_message:
            error_msg = await update.message.reply_text(
                "يجب الرد على الملف الأول المراد نقله."
            )
            asyncio.create_task(delete_messages_delayed(update.message, error_msg))
            return

        # Check if replied message has a document
        if not update.message.reply_to_message.document:
            error_msg = await update.message.reply_text(
                "يجب الرد على ملف."
            )
            asyncio.create_task(delete_messages_delayed(update.message, error_msg))
            return

        # Check command arguments
        if not context.args or len(context.args) != 2:
            error_msg = await update.message.reply_text(
                "الصيغة الصحيحة: /ss رمز_المقرر عدد_الملفات\n"
                "مثال: /ss MGT-301 5"
            )
            asyncio.create_task(delete_messages_delayed(update.message, error_msg))
            return

        # Validate subject code
        subject_code = validate_subject_code(context.args[0])
        if not subject_code:
            error_msg = await update.message.reply_text(
                "رمز المقرر غير صحيح. الرجاء التأكد من الرمز وإعادة المحاولة."
            )
            asyncio.create_task(delete_messages_delayed(update.message, error_msg))
            return

        # Validate and get number of files
        try:
            num_files = int(context.args[1])
            if num_files < 1:
                raise ValueError
        except ValueError:
            error_msg = await update.message.reply_text(
                "عدد الملفات يجب أن يكون رقماً صحيحاً موجباً."
            )
            asyncio.create_task(delete_messages_delayed(update.message, error_msg))
            return

        # Get new topic ID
        new_topic_id = BotConfig.VALID_SUBJECTS_NORMALIZED[subject_code]
        
        # Initialize status message
        status_msg = await update.message.reply_text(
            f"جاري نقل {num_files} ملفات إلى {subject_code}..."
        )

        moved_count = 0
        files_processed = 0
        failed_moves = 0
        starting_message = update.message.reply_to_message

        # Process the files
        while files_processed < num_files and starting_message:
            try:
                if starting_message.document:
                    # Preserve original caption
                    caption = starting_message.caption if starting_message.caption else None
                    
                    # Send to new topic
                    new_message = await context.bot.send_document(
                        chat_id=BotConfig.GROUP_ID,
                        document=starting_message.document.file_id,
                        caption=caption,
                        message_thread_id=int(new_topic_id)
                    )

                    if new_message:
                        # Delete original message
                        try:
                            await starting_message.delete()
                            moved_count += 1
                        except Exception as e:
                            logger.error(f"Error deleting message: {e}")
                            failed_moves += 1

                        # Update status every 2 files
                        if moved_count % 2 == 0:
                            await status_msg.edit_text(
                                f"جاري النقل... تم نقل {moved_count} من {num_files} ملف"
                            )

                files_processed += 1
                
                # Get the next message in the thread
                messages = await context.bot.copy_message(
                    chat_id=BotConfig.GROUP_ID,
                    from_chat_id=BotConfig.GROUP_ID,
                    message_id=starting_message.message_id + 1,
                    message_thread_id=starting_message.message_thread_id
                )
                starting_message = messages
                
            except Exception as e:
                logger.error(f"Error processing file: {e}")
                break

        # Send final confirmation
        final_status = (
            f"✅ اكتمل النقل:\n"
            f"• تم نقل: {moved_count} ملف\n"
        )
        if failed_moves > 0:
            final_status += f"• فشل نقل: {failed_moves} ملف\n"
        
        final_msg = await status_msg.edit_text(final_status)
        
        # Schedule deletion of command and confirmation
        asyncio.create_task(delete_messages_delayed(
            update.message,
            final_msg,
            delay=6
        ))
        
        logger.info(
            f"Bulk move completed: {moved_count} files moved, {failed_moves} failed, "
            f"to topic {new_topic_id} by admin {update.effective_user.id}"
        )

    except Exception as e:
        error_msg = await update.message.reply_text("حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى.")
        asyncio.create_task(delete_messages_delayed(update.message, error_msg))
        logger.error(f"Error in bulk_sort_files: {e}")

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
