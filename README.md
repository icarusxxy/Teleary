<div align="center">

# 📖 Teleary

**Telegram + Diary = Teleary❤️ A Daylio-like mood tracker lives in your Telegram.**

*Because your feelings deserve a soft place to land* 💕

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot%20API-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## ✨ What's Teleary?

Teleary is your cozy little mood tracker (just like [Daylio](https://daylio.net/)), a personal diary bot that lives in your Telegram. Send it a message — any message — and it'll help you log it with a mood emoji. It's like having a warm, supportive friend who never forgets what you said and always asks "how are you feeling?"

Whether you want to capture a quick thought, document a meaningful moment, or just vent about your day, Teleary is here for you. No fancy UIs, no complicated setup — just you, your thoughts, and a cute little bot that cares.

---

## 🎀 Features

| Feature | What it does |
|---------|-------------|
| 📝 **Diary Entries** | Send text, photos, videos, or albums — Teleary saves them all with a mood |
| 😊 **Mood Tracking** | Pick from customizable emoji moods (or add your own!) |
| 🔍 **Search** | Find entries by keyword or date — never lose a thought again |
| 📅 **Browse & Paginate** | Scroll through your entries by month with easy prev/next buttons |
| ✏️ **Edit & Delete** | Change your mind? No problem — update or remove past entries |
| 📥 **Import** | Backdated entries? Import them with a specific date (and time) |
| 🎲 **Random Entry** | Relive a random moment from your past — nostalgia guaranteed |
| 📊 **Stats** | See your streak, mood distribution, and journaling habits |
| ⏰ **Gentle Reminders** | Random nudges to write (only when you haven't already today) |
| 🗓️ **On This Day** | Daily memories from previous years — "a year ago today..." |
| 🌐 **Multi-language** | i18n support (currently in `en` and `zh-tw`) |
| ⚙️ **Customizable** | Configure reminder windows, memory time, emojis, and language |

---

## 🛠️ Tech Stack

```
Python 3.12+  ·  python-telegram-bot  ·  aiosqlite  ·  APScheduler
```

- **python-telegram-bot** — Telegram Bot API wrapper (async)
- **aiosqlite** — Async SQLite for your diary data (no server needed!)
- **APScheduler** — Background jobs for reminders and daily memories

---

## 📋 Prerequisites

Before you begin, make sure you have:

### 1. A Telegram Bot Token
1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **API token** you receive (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)
4. Keep it safe — you'll need it soon

### 2. [Python](https://www.python.org/downloads/) 3.12+ or [Docker](https://www.docker.com/products/docker-desktop/)

---

## 🚀 Quick Start

### Option 1: Python (Local)

```bash
# 1. Clone the repository
git clone https://github.com/icarusxxy/teleary.git
cd teleary

# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your environment
cp .env.example .env
# Edit .env and add your BOT_TOKEN

# 5. Run the bot!
python bot.py
```

### Option 2: Docker (Recommended for Production)

```bash
# 1. Clone the repository
git clone https://github.com/icarusxxy/teleary.git
cd teleary

# 2. Create your environment file
cp .env.example .env
# Edit .env and add your BOT_TOKEN

# 3. Build and start with Docker Compose
docker compose --env-file .env up -d

# 4. Check it's running
docker compose logs -f teleary
```

### Option 3: Docker (Manual Build)

```bash
# Build the image
docker build -t teleary .

# Run the container
docker run -d \
  --name teleary \
  --restart unless-stopped \
  --env-file .env \
  -v bot-data:/app/data \
  teleary
```

---

## 💬 Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message and initialization | `/start` |
| `/help` | Show help page | `/help` |
| `/list` | Browse your diary entries | `/list` |
| `/random` | Get a random diary entry | `/random` |
| `/search <text>` | Search entries by keyword | `/search happy` |
| `/search_by_date <date>` | Search by date pattern | `/search_by_date 2026` |
| `/edit` | Edit a past entry | `/edit` |
| `/delete` | Delete a past entry | `/delete` |
| `/import YYYY-MM-DD [HHMM]` | Import a backdated entry | `/import 2026-03-15 1430` |
| `/settings` | Configure bot settings | `/settings` |
| `/stats` | View your journaling statistics | `/stats` |
| `/language` | Change language | `/language` |
| `/cancel` | Cancel current action | `/cancel` |

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file from the example and customize:

```bash
cp .env.example .env
```

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BOT_TOKEN` | Telegram bot token from @BotFather | — | ✅ Yes |
| `TIMEZONE` | Your timezone (display, scheduling, Docker system) | `Asia/Taipei` | No |
| `DB_PATH` | Path to SQLite database file | `data/diary.db` | No |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` | No |

### Settings Menu

Once the bot is running, you can configure these via the `/settings` command:

- **Remind Window** — Hours when random reminders can appear (default: 9:00–21:00)
- **Memory Time** — When to receive "on this day" memories (default: 09:00)
- **Mood Emojis** — Add, edit, or remove mood emojis
- **Language** — Switch between English and Traditional Chinese

---

## 📁 Project Structure

```
teleary/
├── bot.py              # Entry point — wires everything together
├── bot_state.py        # Global state (bot instance, chat_id)
├── core/               # Infrastructure layer
│   ├── config.py       # Environment variables, logging setup
│   ├── database.py     # SQLite queries and schema
│   ├── cache.py        # TTL cache for settings/moods
│   ├── i18n.py         # Internationalization (locale loader)
│   └── scheduler.py    # Background jobs (reminders, memories)
├── handlers/           # Telegram interaction layer
│   ├── states.py       # Conversation state constants
│   ├── common.py       # Shared helpers (language, keyboards, media groups)
│   ├── entry.py        # New diary entry flow
│   ├── edit.py         # Edit entry flow
│   ├── delete.py       # Delete entry flow
│   ├── import_flow.py  # Import backdated entries
│   ├── settings.py     # Settings and configuration
│   ├── list.py         # Browse and paginate entries
│   ├── search.py       # Search by keyword/date
│   ├── random.py       # Random entry
│   ├── stats.py        # Journaling statistics
│   └── memory.py       # "On this day" memories
├── utils/              # Pure utility code
│   ├── utils.py        # Date parsing, timezone conversion, formatters
│   ├── emoji_config.py # Mood emoji CRUD with DB-backed customization
│   └── validators.py   # Input validation
├── locale/             # Translation files
│   ├── eng.json        # English
│   └── zh-tw.json      # Traditional Chinese
├── data/               # SQLite database (created at runtime)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker image definition
├── docker-compose.yml  # Docker Compose configuration
└── .env.example        # Environment variable template
```

---

## 🐳 Docker Notes

### Environment Variables

Docker Compose uses `${VARIABLE}` syntax to read values from a `.env` file you provide at runtime.

```bash
# Start with your env file
docker compose --env-file .env up -d
```

### Data Persistence

Your diary data is stored in a Docker named volume (`bot-data`). This means:

- Data survives container restarts
- Data survives image updates
- To back up: `docker compose exec teleary cat /app/data/diary.db > backup.db`
- To restore: `docker compose exec -T teleary tee /app/data/diary.db < backup.db`

### Resource Limits

The Docker Compose config includes sensible defaults:

| Resource | Limit |
|----------|-------|
| Memory | 256MB max, 64MB reserved |
| CPU | 0.5 cores max, 0.1 reserved |
| Logs | 10MB max, 3 rotated files |

Adjust these in `docker-compose.yml` as needed.

### Health Check

The container includes a health check that verifies the Python process is running. Check status with:

```bash
docker inspect --format='{{.State.Health.Status}}' teleary
```

---

## 🌍 Internationalization

Teleary supports multiple languages via JSON locale files in the `locale/` directory.

### Currently Supported

- 🇺🇸 **English** (`eng.json`)
- 🇹🇼 **Traditional Chinese** (`zh-tw.json`)

### Adding a New Language

1. Create a new file in `locale/` named `<language-code>.json` (e.g., `ja.json` for Japanese)
2. Copy `locale/eng.json` as a template
3. Translate all values and keep the keys unchanged
4. Restart the bot — it will automatically detect the new locale

Contributions for new languages are greatly appreciated! 🎉

---

## 🤝 Contributing

Contributions are welcome!  
Please be free to submit pull requests or open issues for bugs and feature requests. 🥹

### Ideas for Contributions

- 🌐 New language translations
- 📊 New stats or analytics features
- 🎨 Mood emoji improvements
- 📱 Telegram client optimizations
- 🧪 Tests (always appreciated!)
- 📖 Documentation improvements

---

## ⚠️ Disclaimer

This is a personal project built for personal use. While it works great as a personal diary bot:

- **Back up your data** — SQLite databases can corrupt. Regular backups are wise.
- **No encryption** — Your diary entries are stored in plain text in SQLite. Don't store secrets.
- **Single-user design** — This bot is built for one person. Running it for multiple users **WILL** have unexpected behavior.
- **No guarantees** — Use at your own risk. The author is not responsible for lost data or existential crises triggered by using the bot.

---

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Made with 💕 for diary lovers everywhere**

*Your feelings matter. Write them down.*

</div>
