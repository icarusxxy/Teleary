# Spec: Diary Bot

## Objective

A private Telegram bot that serves as a personal diary. The bot makes journaling low-friction by providing a quick entry flow (emoji mood + thoughts), resurfaces past entries as "memories" on their anniversaries, and gently nudges the user to keep the habit going.

**User:** Single user (bot owner), accessed via Telegram DM.

**Success:** The user can quickly log a mood + thought, get random reminders during a configurable time window, receive daily memories as replies to original messages, import old entries by date, and optionally view basic stats.

## Tech Stack

- **Language:** Python 3.10+
- **Telegram:** `python-telegram-bot` v20+ (async, webhook-friendly)
- **Database:** SQLite via `aiosqlite`
- **Scheduling:** `APScheduler` (for random reminders + daily memory)
- **Env:** `.env` via `python-dotenv`
- **Timezone:** `Asia/Taipei` (UTC+8)

## Commands

```
# Run the bot
python bot.py

# Install dependencies
pip install -r requirements.txt
```

## Project Structure

```
diary-bot/
├── bot.py              # Entry point, bot setup, handler registration
├── database.py         # SQLite schema + async CRUD operations
├── handlers.py         # Telegram message/callback handlers
├── scheduler.py        # APScheduler jobs (reminders + memories)
├── utils.py            # Emoji map, date helpers, formatting
├── config.py           # Load .env, centralized settings
├── requirements.txt    # Dependencies
├── .env.example        # Template for env vars
├── spec.md             # This file
└── diary.db            # SQLite database (created at runtime)
```

## Code Style

- Async-first: all DB and HTTP operations are async
- Functions: `snake_case`, descriptive names (`handle_new_entry`, not `handler1`)
- Classes: `PascalCase` only for data models
- Constants: `UPPER_SNAKE_CASE` in `config.py`
- Prefer early returns over nested if/else

## Database Schema

```sql
CREATE TABLE entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,           -- Telegram message_id for reply linking
    mood TEXT NOT NULL,            -- emoji character
    thought TEXT NOT NULL,         -- freeform text
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Settings keys:
- `reminder_start` — hour (0-23) when random reminders can start
- `reminder_end` — hour (0-23) when random reminders stop
- `memory_time` — HH:MM when daily memory sends

## Features

### 1. New Entry
- User sends any text message → bot asks for mood (inline keyboard with 5 emojis: 😊 😢 😐 😤 😴)
- User taps emoji → entry saved with mood + text, bot confirms with a checkmark
- Store `message_id` of the user's original text for reply-linking

### 2. Edit Entry
- `/edit` → bot shows last 10 entries as inline buttons
- User taps entry → bot shows current mood + text, asks what to change
- Support editing mood, thought, or both

### 3. Delete Entry
- `/delete` → bot shows last 10 entries as inline buttons
- User taps entry → confirmation prompt → delete

### 4. Import Entry
- `/import YYYY-MM-DD` followed by text on next line
- Bot saves entry with that date, prompts for mood via inline keyboard
- Format: multiline message after `/import 2024-03-15`

### 5. Random Reminders
- APScheduler fires every 15 minutes during `reminder_start`–`reminder_end`
- Each tick: 30% chance to send "Don't forget to journal today!" (or similar varied messages)
- Messages are varied (pool of 5-6 different reminder texts)

### 6. Daily Memory
- APScheduler fires daily at `memory_time`
- Query entries where `date(created_at) == date('now')` for previous years
- For each match: send the entry text as a **reply** to the original `message_id`
- Include mood emoji + formatted date in the reply header

### 7. Settings
- `/settings` → inline keyboard to configure:
  - Reminder window (start hour, end hour)
  - Memory time
- Stored in `settings` table

### 8. Stats (Nice-to-Have)
- `/stats` → send message with:
  - Total entries count
  - Entries this month
  - Mood distribution (emoji counts)
  - Longest streak (consecutive days with entries)
  - Current streak

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + instructions |
| `/settings` | Configure reminder window + memory time |
| `/edit` | Edit a past entry |
| `/delete` | Delete a past entry |
| `/import YYYY-MM-DD` | Import an entry for a specific date |
| `/stats` | View journaling stats |

## Environment Variables (.env)

```
BOT_TOKEN=your_telegram_bot_token
TIMEZONE=Asia/Taipei
```

## Boundaries

- **Always:** Use async/await for all I/O, validate user input, handle Telegram API errors gracefully
- **Ask first:** Changing the database schema, adding new bot commands, modifying the entry flow
- **Never:** Commit `.env` or `diary.db`, hardcode the bot token, block the event loop

## Success Criteria

- [ ] Bot starts without errors and responds to `/start`
- [ ] User can create an entry (text + mood emoji)
- [ ] User can edit a past entry
- [ ] User can delete a past entry
- [ ] User can import an entry for a past date
- [ ] Random reminders fire during configured time window
- [ ] Daily memory sends past entries as replies to original messages
- [ ] `/stats` shows correct counts and mood distribution
- [ ] `/settings` allows configuring reminder window and memory time
- [ ] All data persists in SQLite across bot restarts

## Open Questions

- None — all requirements confirmed via interview.
