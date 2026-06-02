# types.py
from dataclasses import dataclass
from datetime import datetime
from telegram import Document, User
from telegram.ext import ContextTypes

@dataclass
class QueueItem:
    """Represents a file in the processing queue."""
    context: ContextTypes.DEFAULT_TYPE
    document: Document
    user: User
    chat_id: int
    timestamp: datetime = datetime.now()

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
