# core.py
import asyncio
import logging
import os
import re
from datetime import datetime,timedelta
from typing import Optional, Dict, Set, DefaultDict
from collections import defaultdict
import json
from dataclasses import dataclass
from telegram import Document, User
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest
from config import BotConfig
from bot_types import QueueItem
from telegram.error import RetryAfter, BadRequest
import os
logger = logging.getLogger(__name__)

@dataclass
class QueueItem:
    """Represents a file in the processing queue."""
    context: ContextTypes.DEFAULT_TYPE
    document: Document
    user: User
    chat_id: int
    timestamp: datetime = datetime.now()
class RateLimiter:
    def __init__(self, rate_limit: int, time_window: int = 60):
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.timestamps: Dict[int, list] = defaultdict(list)

    async def can_process(self, user_id: int) -> bool:
        now = datetime.now()
        # Remove old timestamps
        self.timestamps[user_id] = [
            ts for ts in self.timestamps[user_id]
            if now - ts < timedelta(seconds=self.time_window)
        ]
        
        if len(self.timestamps[user_id]) < self.rate_limit:
            self.timestamps[user_id].append(now)
            return True
        return False
class BotData:
    """Manages bot's persistent data and state."""
    def __init__(self):
        self.user_violations: DefaultDict[int, int] = defaultdict(int)
        self.blocked_users: Set[int] = set()
        self.show_tags: Set[int] = set()
        self.total_files: int = 0
        self.user_uploads: DefaultDict[int, int] = defaultdict(int)
        self.user_queue_counts: DefaultDict[int, int] = defaultdict(int)
        self.queue_status_messages: Dict[int, int] = {}
        self.queue_status_tasks: Dict[int, asyncio.Task] = {}
        
        # Auto-features states
        self.auto_changelog: bool = False
        self.auto_stats: bool = False
        
        self._load_data()

    def _load_data(self) -> None:
        """Load data from JSON file."""
        try:
            if BotConfig.DATA_FILE.exists():
                data = json.loads(BotConfig.DATA_FILE.read_text())
                self.user_violations = defaultdict(int, data.get('user_violations', {}))
                self.blocked_users = set(data.get('blocked_users', []))
                self.total_files = data.get('total_files', 0)
                self.user_uploads = defaultdict(int, data.get('user_uploads', {}))
                self.show_tags = set(data.get('show_tags', []))
                # Load auto-features states
                self.auto_changelog = data.get('auto_changelog', False)
                self.auto_stats = data.get('auto_stats', False)
                logger.info("Data loaded successfully")
        except Exception as e:
            logger.error(f"Error loading data: {e}")

    def save_data(self) -> None:
        """Save data to JSON file."""
        try:
            data = {
                'user_violations': dict(self.user_violations),
                'blocked_users': list(self.blocked_users),
                'total_files': self.total_files,
                'user_uploads': dict(self.user_uploads),
                'show_tags': list(self.show_tags),
                # Save auto-features states
                'auto_changelog': self.auto_changelog,
                'auto_stats': self.auto_stats
            }
            BotConfig.DATA_FILE.write_text(json.dumps(data, indent=2))
            logger.info("Data saved successfully")
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def set_auto_changelog(self, state: bool) -> None:
        """Set auto changelog state and save."""
        self.auto_changelog = state
        self.save_data()
        logger.info(f"Auto changelog {'enabled' if state else 'disabled'}")

    def set_auto_stats(self, state: bool) -> None:
        """Set auto stats state and save."""
        self.auto_stats = state
        self.save_data()
        logger.info(f"Auto stats {'enabled' if state else 'disabled'}")

    def get_auto_changelog(self) -> bool:
        """Get auto changelog state."""
        return self.auto_changelog

    def get_auto_stats(self) -> bool:
        """Get auto stats state."""
        return self.auto_stats

class QueueProcessor:
    def __init__(self):
        
        self.queue = asyncio.Queue()
        self.active = True
        self.processing = False  # Added this line
        self.processing_users: Set[int] = set()
        self.user_rate_limiter = RateLimiter(BotConfig.USER_RATE_LIMIT)
        self.global_rate_limiter = RateLimiter(BotConfig.GLOBAL_RATE_LIMIT)
        self.user_queues: Dict[int, int] = defaultdict(int)
        logger.info("Queue processor initialized")
        self.bot_data = bot_data  # Add this line
    
    async def start_processing(self) -> None:
        """Start processing queued files."""
        if not self.processing:
            self.processing = True
            await self.run()
    async def run(self) -> None:
        """Process queued files."""
        logger.info("Queue processor started")
        self.processing = True  # Ensure processing flag is set
        
        while self.active and self.processing:
            try:
                item = await self.queue.get()
                user_id = item.user.id

                if user_id not in self.processing_users:
                    self.processing_users.add(user_id)
                    try:
                        await self.process_file(item)
                    finally:
                        self.processing_users.remove(user_id)
                        self.user_queues[user_id] = max(0, self.user_queues[user_id] - 1)
                        if self.user_queues[user_id] == 0:
                            del self.user_queues[user_id]

                self.queue.task_done()
                await asyncio.sleep(BotConfig.FILE_PROCESS_DELAY)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                await asyncio.sleep(1)
        
        self.processing = False
        logger.info("Queue processor stopped")
    async def add_to_queue(self, item: QueueItem) -> tuple[bool, str]:
        """Add file to queue with rate limiting."""
        try:
            user_id = item.user.id
            
            # Check user queue limit
            if self.user_queues[user_id] >= BotConfig.MAX_FILES_PER_USER_QUEUE:
                return False, f"عذراً، لديك الحد الأقصى من الملفات في قائمة الانتظار ({BotConfig.MAX_FILES_PER_USER_QUEUE})"

            # Check rate limits
            if not await self.user_rate_limiter.can_process(user_id):
                return False, "عذراً، يرجى الانتظار قليلاً قبل رفع المزيد من الملفات"

            if not await self.global_rate_limiter.can_process(0):
                return False, "النظام مشغول حالياً، يرجى المحاولة بعد قليل"

            # Add to queue
            await self.queue.put(item)
            self.user_queues[user_id] += 1
            logger.info(f"Added file to queue for user {user_id}. Queue size: {self.user_queues[user_id]}")
            return True, ""

        except Exception as e:
            logger.error(f"Error adding to queue: {e}")
            return False, "حدث خطأ أثناء إضافة الملف لقائمة الانتظار"
    
    def find_subject_code(self, filename: str) -> Optional[str]:
        """
        Extract subject code from filename.
        Supports formats like: MGT-301, mgt301, MGT 301, etc.
        Returns uppercase version of the code if found.
        """
        try:
            import re
            # Pattern to match subject codes anywhere in the filename
            pattern = r'([A-Za-z]+)[-\s]?(\d{3})'
            matches = re.finditer(pattern, filename.upper())
            
            for match in matches:
                # Construct the subject code in standardized format (e.g., MGT-301)
                subject_code = f"{match.group(1)}-{match.group(2)}"
                # Check if this standardized code exists in our valid subjects
                if subject_code in BotConfig.VALID_SUBJECTS_NORMALIZED:
                    return subject_code
            
            return None
        except Exception as e:
            logger.error(f"Error finding subject code for {filename}: {e}")
            return None
    async def process_file(self, item: QueueItem) -> bool:
        """Process a single file from queue."""
        try:
            # Check if user is blocked
            if item.user.id in self.bot_data.blocked_users:
                logger.warning(f"Blocked user {item.user.id} attempted to upload file")
                return False

            file = item.document
            file_name = file.file_name
            download_path = os.path.join('downloads', file_name)
            
            # Find subject code and topic
            subject_code = self.find_subject_code(file_name)
            topic_id = (BotConfig.VALID_SUBJECTS_NORMALIZED.get(subject_code, BotConfig.OTHER_FILES_TOPIC_ID)
                       if subject_code else BotConfig.OTHER_FILES_TOPIC_ID)

            try:
                # First download the file
                file_obj = await item.context.bot.get_file(file.file_id)
                await file_obj.download_to_drive(download_path)
                logger.info(f"Downloaded file: {file_name}")

                # Try to send to topic
                try:
                    # Include caption only if user wants to be tagged
                    caption = f"تم رفع بواسطة {item.user.full_name}" if item.user.id in self.bot_data.show_tags else None
                    
                    sent_message = await item.context.bot.send_document(
                        chat_id=BotConfig.GROUP_ID,
                        document=file.file_id,
                        caption=caption,
                        message_thread_id=int(topic_id)
                    )
                    logger.info(f"Sent file {file_name} to topic {topic_id}")
                    return True

                except BadRequest as e:
                    if "message thread not found" in str(e).lower():
                        # Fallback to main group
                        caption = f"تم رفع بواسطة {item.user.full_name}" if item.user.id in self.bot_data.show_tags else None
                        sent_message = await item.context.bot.send_document(
                            chat_id=BotConfig.GROUP_ID,
                            document=file.file_id,
                            caption=caption
                        )
                        logger.info(f"Sent file {file_name} to main group (topic not found)")
                        return True
                    raise

            except RetryAfter as e:
                logger.warning(f"Rate limit hit, waiting {e.retry_after} seconds")
                await asyncio.sleep(e.retry_after)
                # Re-queue the item
                await self.queue.put(item)
                return False

            finally:
                # Clean up downloaded file
                if os.path.exists(download_path):
                    os.remove(download_path)
                    logger.info(f"Cleaned up file: {file_name}")

        except Exception as e:
            logger.error(f"Error processing file {item.document.file_name}: {e}")
            return False

    

    def get_user_queue_count(self, user_id: int) -> int:
            """Get number of files in queue for user."""
            return self.user_queues.get(user_id, 0)
        

# Initialize bot data and queue processor
bot_data = BotData()
queue_processor = QueueProcessor()

def initialize_bot_data() -> None:
    """Initialize bot data when starting the bot."""
    global bot_data, queue_processor
    bot_data = BotData()
    queue_processor = QueueProcessor()
    
    # Create downloads directory if it doesn't exist
    os.makedirs('downloads', exist_ok=True)
    logger.info("Bot data and directories initialized")

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
