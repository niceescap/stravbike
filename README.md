# stravbike 🚴

A personal cycling training dashboard connecting Strava to coach-athlete collaboration.

## What it does

- Automatically imports cycling activities from Strava
- Displays a training calendar with planned sessions, completed rides and competitions
- Validates completed sessions against coach's planned targets (duration, TSS, IF)
- Enables coach and athlete to comment on activities
- Generates LLM-powered summaries via OpenRouter

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12 + FastAPI + SQLAlchemy |
| Database | PostgreSQL |
| Frontend | HTML / JS / CSS + FullCalendar + Chart.js |
| Strava API | stravalib |
| LLM | OpenRouter |
| Auth | Magic link via TEM |

## Project structure

```
stravbike/
├── api/              # FastAPI routes + Pydantic models
├── db/               # PostgreSQL schema + SQLAlchemy connection
├── frontend/         # SPA (index.html + JS + CSS)
├── ingestion/        # Strava data import (athlete + activities)
└── services/         # Validator (session matching) + LLM calls
```

## Setup

```bash
# Clone
git clone https://github.com/<your-user>/stravbike.git
cd stravbike

# Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Fill in your Strava and OpenRouter credentials

# Apply database schema
psql -U postgres -d stravbike -f db/schema.sql

# Start the server
uvicorn api.main:app --reload --port 2024
```

## Environment variables

```
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REFRESH_TOKEN=
DATABASE_URL=postgresql://postgres@localhost/stravbike
OPENROUTER_API_KEY=
JWT_SECRET=
```

## Status

🚧 Active development — personal project, not production-ready.

## License

MIT
