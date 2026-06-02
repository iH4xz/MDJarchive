# config.py
import logging
from pathlib import Path
from typing import Dict, Set, DefaultDict
from collections import defaultdict
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BotConfig:
    # In changelogger:
    CHANGELOG_CHANNEL_ID = int(os.getenv("CHANGELOG_CHANNEL_ID") or 0)
    CHANGELOG_INTERVAL = int(os.getenv("CHANGELOG_INTERVAL") or 7200)  # 2 hours in seconds
    
    # Bot Token & IDs
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        # Provide a dummy string during compilation/import to prevent immediate crash if not set,
        # but it will fail properly when the bot starts.
        TOKEN = "DUMMY_TOKEN_NOT_SET"
        
    GROUP_ID = int(os.getenv("TELEGRAM_GROUP_ID") or 0)
    STATS_TOPIC_ID = int(os.getenv("STATS_TOPIC_ID") or 0)
    OTHER_FILES_TOPIC_ID = int(os.getenv("OTHER_FILES_TOPIC_ID") or 0)
    ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
    BOT_VERSION = "1.0.0"
## changelog extra codes 
    BASE_DIR1 = Path(__file__).parent
    LOG_DIR2 = BASE_DIR1 / 'logs'
    LOG_FILE3 = LOG_DIR2 / 'bot.log'
    
    @classmethod
    def initialize_directories(cls):
        """Create necessary directories."""
        cls.LOG_DIR2.mkdir(parents=True, exist_ok=True)

    # Concurrent Users Settings
    MAX_CONCURRENT_USERS = 10  # Maximum number of users processing files simultaneously
    USER_RATE_LIMIT = 40  # Maximum files per user per minute
    GLOBAL_RATE_LIMIT = 400  # Maximum total files per minute
    QUEUE_TIMEOUT = 300  # Seconds before queue entry expires (5 minutes)
    MAX_FILES_PER_USER_QUEUE = 50  # Maximum files a user can have in queue
    # File Settings
    MAX_FILE_SIZE = 150 * 1024 * 1024  # 150MB
    MAX_FILES_PER_UPLOAD = 50
    MAX_QUEUE_SIZE = 100
    ALLOWED_FILE_TYPES = ('.pdf', '.ppt', '.pptx')
    
    # Queue Settings
    QUEUE_UPDATE_INTERVAL = 10  # seconds
    QUEUE_INITIAL_WAIT = 8  # seconds
    FILE_PROCESS_DELAY = 2.5  # seconds
    STATS_UPDATE_INTERVAL = 6 * 60 * 60  # 6 hours
    
    # Paths
    BASE_DIR = Path(__file__).parent
    DATA_FILE = BASE_DIR / 'data' / 'bot_data.json'
    LOG_FILE = BASE_DIR / 'logs' / 'bot.log'
    DOWNLOAD_DIR = BASE_DIR / 'downloads'
    
    # Create necessary directories
    @classmethod
    def initialize_directories(cls):
        cls.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Subject codes mapping
    VALID_SUBJECTS = {
    "ISLAM-101": "417", "STAT-101": "263", "LAW-101": "415", "ACCT-101": "10", "ECON-101": "3", "MGT-101": "383",
    "ISLAM-102": "419", "STAT-201": "421", "FIN-101": "4", "MGT-201": "427", "MGT-211": "131", "ECOM-101": "423",
    "ECON-201": "25", "MIS-201": "8", "ECOM-201": "425", "MGT-301": "98", "MGT-311": "81", "MGT-312": "1071",
    "ISLAM-103": "790", "ACCT-301": "858", "MGT-321": "800", "MGT-322": "1283", "MGT-323": "748",
    "ISLAM-104": "1218", "MGT-401": "915", "MGT-324": "1263", "MGT-402": "1259", "MGT-403": "1261",
    "MGT-404": "1266", "MGT-421": "1268", "MGT-422": "1270", "MGT-430": "1273",
    "MGT-325": "2173", "MGT-424": "2176", "MGT-425": "2179"
    
}
    
    # Normalized subject codes for case-insensitive matching
    VALID_SUBJECTS_NORMALIZED = {k.upper(): v for k, v in VALID_SUBJECTS.items()}
    
    # Bad words filter
    BAD_WORDS = ["badword1", "badword2", "badword3"]  # Add your bad words here

# Logging configuration
def setup_logging():
    BotConfig.initialize_directories()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(BotConfig.LOG_FILE)
        ]
    )
    logger = logging.getLogger(__name__)
    return logger

# this file is coded and made by iH4xz - iH4xz.pro - Telegram@iH4xz
