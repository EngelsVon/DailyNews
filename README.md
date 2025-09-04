# DailyNews Aggregation & Translation Platform

DailyNews is a lightweight, ready-to-run tech news aggregation and translation platform. Built with Flask + SQLAlchemy + APScheduler, it fetches news by sections from multiple sources on schedule, offers a clean web UI, one-click refresh, and collaborative translation (MyMemory free API or local Gemini CLI).

- Easy to deploy with SQLite by default; no external services required (override with DATABASE_URL if needed)
- Section-based management: RSS, arXiv, and custom Gemini collector
- Friendly UI: per-section item limit, timezone switch, global/per-section translation, expandable summaries
- Background jobs: scheduled fetching and batch translation

## Table of Contents
- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [Advanced Topics](#advanced-topics)
- [FAQ](#faq)
- [License](#license)

## Features
- Multi-source collection: RSS, arXiv, and Gemini-based collector (execute local/remote models via CLI)
- De-duplication: simple (title + url) check before insert
- Friendly ordering: index page sorts by created_at first so newly fetched items show up immediately
- Translation options:
  - Browser pseudo-translate (front-end demo)
  - MyMemory Free API (optional email to expand quota)
  - Gemini CLI (invoke local command; requires GEMINI_API_KEY or local setup)
- Background translation: start on demand or run periodically

## Quick Start
1) Clone and enter
```
git clone https://github.com/yourname/DailyNews.git
cd DailyNews
```
2) Virtualenv and dependencies
```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```
3) Environment variables (optional)
Copy .env.example to .env and adjust accordingly:
```
cp .env.example .env
```
Important keys:
- SECRET_KEY
- DATABASE_URL (default sqlite:///data/dailynews.db)
- GEMINI_CLI_CMD / GEMINI_API_KEY (if using Gemini translation)
- MYMEMORY_EMAIL (if using free translation)

4) Run dev server
```
python app.py
```
Open http://127.0.0.1:5000/

## Configuration
See <mcfile name="config.py" path="d:\PythonProjects\DailyNews\config.py"></mcfile> for key settings:
- Database: SQLite by default at data/dailynews.db; override via DATABASE_URL
- Scheduler: APScheduler background jobs; API enabled
- Translation: GEMINI_CLI_CMD, GEMINI_API_KEY, MYMEMORY_EMAIL

Templates and static files:
- Templates: <mcfolder name="templates" path="d:\PythonProjects\DailyNews\templates\"></mcfolder>
- Static: <mcfolder name="static" path="d:\PythonProjects\DailyNews\static\"></mcfolder>

## Usage Guide
1) Create a Section
- Go to the "Sections" page, fill Name, Description, fetch method (rss/arxiv/gemini) and interval; save then click Manual Refresh
- Each method has a JSON template in the modal dialog

2) Index page
- Per-section slider to limit visible items, timezone switch, and translation toggles
- A red "New" badge marks items created within the last 12 hours
- Manual Refresh triggers a backend fetch and reloads the page

3) Translation
- Choose translation method in Settings: browser/free/gemini
- free: providing MYMEMORY_EMAIL is recommended to improve quota
- gemini: set CLI command (e.g. gemini or gemini-cli) in Settings and ensure GEMINI_API_KEY is available
- From the index page, you can run Translate once or start Background Translation to batch-process untranslated items

## Advanced Topics
- Background translation schedule: controlled via AUTO_TRANSLATE_INTERVAL_MINUTES (registered in app.py)
- Custom collectors: add implementations under collectors and configure section fetch_method + config_json
- Production deployment: use a proper WSGI server (e.g., gunicorn + gevent) or an ASGI adapter; switch to a persistent DB (PostgreSQL/MySQL)

## FAQ
- Page not updating? The index is ordered by created_at first; after Manual Refresh the page reloads automatically.
- No "New" badge for new entries? It is based on created_at <= 12 hours; adjust the threshold in the backend if needed.
- Free translation rate/quota? Reduce batch size or provide an email when using MyMemory.

## License
This project is open-source. See LICENSE for details.
