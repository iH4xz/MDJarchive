# 🚀 Setup & Installation Guide

This guide explains how to install, configure, and run the MDJ Archive & Sorter Telegram Bot.

---

## 1. Prerequisites
- **Python 3.8+** installed on your system.
- A Telegram Bot API token from [@BotFather](https://t.me/BotFather).
- A Telegram Supergroup with Forum Topics enabled.

---

## 2. Installation

Clone this repository to your local machine (or download the source code) and install the required dependencies:

```bash
pip install -r requirements.txt
```

---

## 3. Configuration

1. Copy the `.env.example` file to create your own configuration file:
   ```bash
   cp .env.example .env
   ```

2. Open the `.env` file and fill in your details:
   - `TELEGRAM_BOT_TOKEN`: The API token from BotFather.
   - `TELEGRAM_GROUP_ID`: Your supergroup's ID (typically begins with `-100`).
   - `CHANGELOG_CHANNEL_ID`: Channel ID for changelog reports.
   - `ADMIN_ID`: Your personal Telegram User ID (to allow admin commands).
   - `STATS_TOPIC_ID` / `OTHER_FILES_TOPIC_ID`: Thread/Topic IDs inside the forum group.

3. Update the subject mapping (`VALID_SUBJECTS`) in [`config.py`](config.py) to match your group topic thread IDs:
   ```python
   VALID_SUBJECTS = {
       "ISLAM-101": "417",
       "STAT-101": "263",
       # Format: "Subject-Code": "Telegram_Topic_Thread_ID"
   }
   ```

---

## 4. Running the Bot

Run the main bot script:

```bash
python bot.py
```
