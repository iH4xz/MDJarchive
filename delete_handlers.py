from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError
import asyncio
from functools import wraps

def admin_required(func):
    """Decorator to check if user is an admin before executing command."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # Get the effective message (could be edited or original)
        message = update.effective_message
        if not message:
            return
            
        if not update.effective_chat or not update.effective_user:
            await message.reply_text("خطأ في تنفيذ الأمر.")
            return
        
        try:
            chat_member = await update.effective_chat.get_member(update.effective_user.id)
            if chat_member.status not in {'administrator', 'creator'}:
                await message.reply_text("عذرًا، هذا الأمر متاح للإداريين فقط.")
                return
            return await func(update, context, *args, **kwargs)
        except TelegramError:
            await message.reply_text("حدث خطأ أثناء التحقق من صلاحيات المستخدم.")
    return wrapper

class MessageHandler:
    def __init__(self, context: ContextTypes.DEFAULT_TYPE):
        self.context = context
        self.deleted_count = 0
        self.failed_count = 0
        
    async def delete_message(self, chat_id: int, message_id: int, thread_id: Optional[int] = None) -> bool:
        try:
            await self.context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            self.deleted_count += 1
            return True
        except TelegramError:
            self.failed_count += 1
            return False
            
    async def send_temp_message(self, 
                              chat_id: int, 
                              text: str, 
                              thread_id: Optional[int] = None, 
                              duration: int = 3) -> None:
        try:
            msg = await self.context.bot.send_message(
                chat_id=chat_id,
                text=text,
                message_thread_id=thread_id if thread_id else None
            )
            await asyncio.sleep(duration)
            await self.delete_message(chat_id, msg.message_id)
        except TelegramError:
            pass

@admin_required
async def delete_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete multiple messages in a chain starting from the replied message."""
    message = update.effective_message
    if not message:
        return
        
    if not context.args:
        await message.reply_text(
            "يرجى تحديد عدد الرسائل للحذف.",
            message_thread_id=message.message_thread_id
        )
        return

    try:
        count = int(context.args[0])
        if count < 1:
            await message.reply_text(
                "يجب أن يكون العدد أكبر من صفر.",
                message_thread_id=message.message_thread_id
            )
            return
    except ValueError:
        await message.reply_text(
            "يرجى إدخال رقم صحيح.",
            message_thread_id=message.message_thread_id
        )
        return

    if not message.reply_to_message:
        await message.reply_text(
            "يرجى الرد على الرسالة التي تريد بدء الحذف منها.",
            message_thread_id=message.message_thread_id
        )
        return

    handler = MessageHandler(context)
    current_message = message.reply_to_message
    thread_id = message.message_thread_id
    
    # Delete messages in chain
    for _ in range(count):
        if not current_message:
            break
            
        if await handler.delete_message(
            current_message.chat_id, 
            current_message.message_id, 
            thread_id
        ):
            current_message = current_message.reply_to_message
        else:
            break

    # Delete command message
    await handler.delete_message(
        message.chat_id, 
        message.message_id, 
        thread_id
    )
    
    # Send temporary status message
    status_text = (
        f"تم حذف {handler.deleted_count} رسائل بنجاح."
        f"{f' فشل حذف {handler.failed_count} رسائل.' if handler.failed_count else ''}"
    )
    await handler.send_temp_message(
        message.chat_id, 
        status_text, 
        thread_id
    )

@admin_required
async def delete_single_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a single message that was replied to."""
    message = update.effective_message
    if not message:
        return
        
    if not message.reply_to_message:
        await message.reply_text(
            "يرجى الرد على الرسالة التي تريد حذفها.",
            message_thread_id=message.message_thread_id
        )
        return

    handler = MessageHandler(context)
    reply_msg = message.reply_to_message
    thread_id = message.message_thread_id
    
    # Delete replied message and command message
    await handler.delete_message(reply_msg.chat_id, reply_msg.message_id, thread_id)
    await handler.delete_message(message.chat_id, message.message_id, thread_id)
    
    # Send temporary confirmation
    if handler.deleted_count > 0:
        await handler.send_temp_message(
            message.chat_id, 
            "تم الحذف بنجاح.", 
            thread_id
        )
    else:
        await handler.send_temp_message(
            message.chat_id, 
            "فشل حذف الرسالة.", 
            thread_id
        )

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
