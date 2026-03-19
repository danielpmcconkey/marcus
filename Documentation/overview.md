# Overview

Marcus is a YouTube curation agent that builds a daily viewing programme for Dan. It replaces YouTube's algorithmic subscription feed with a curated playlist — news up front, then hours of subscription content ordered by priority.

## Why It Exists

YouTube's subscription feed is broken. It's an algorithmic soup that flattens Dan's breadth of interests (homebrewing, rock collecting, hiking, language learning, coding, cooking) into whatever maximises watch time. Add the flood of AI-generated slop and the signal-to-noise ratio is unbearable.

Marcus solves this by being the curator YouTube refuses to be.

## Architecture: Agent-as-Curator

Marcus is an OpenClaw agent — a Claude instance with a character (Marcus Brody from Indiana Jones) and a set of Python scripts. The division of labour:

- **Python scripts** handle all I/O: YouTube API calls, RSS parsing, database operations, playlist management.
- **The agent (Claude)** makes curation decisions — specifically, curating the news block by clustering stories, picking representatives, and ensuring diversity.

The agent does NOT call the YouTube API directly. The scripts fetch data, the agent thinks, the scripts execute.

## The Daily Programme

Every evening at 17:00 ET, Marcus builds a fresh playlist:

1. **News block** (20-30 minutes) — Tier 0 channels. Agent-curated: one video per news story, diverse channels, breadth over depth.
2. **Subscription block** (3-5 hours) — Tiers 1/2/3. Mechanically selected by priority and recency.

The playlist is completely destroyed and rebuilt each day. It is a nightly TV schedule, not a rolling queue. Dan won't watch all 3-5 hours — the buffer gives him enough to skip things he's not interested in on a given night.

## Channel Tiers

| Tier | Role | Duration cap | Selection window |
|------|------|-------------|-----------------|
| 0 | News | 5 min/video | 24 hours |
| 1 | Must-watch | None | 3 months |
| 2 | Priority | 25 min/video | 3 months |
| 3 | Filler | 25 min/video | 3 months |

Tier 0 channels are NOT YouTube subscriptions — they're news outlets added directly to the database. All tiers are polled via RSS (free, no API quota).

Unwanted channels: set `subscribed=false` in the database. There is no "ignore" tier.

## Tech Stack

- **Language:** Python 3
- **Database:** PostgreSQL (`openclaw` database, `marcus` schema)
- **YouTube API:** Google YouTube Data API v3 (OAuth 2.0, 10,000 units/day)
- **RSS:** Standard YouTube channel RSS feeds (free, no quota)
- **Discord:** `#marcus_museum` channel via OpenClaw gateway
- **Secrets:** `pass` password store (GPG-encrypted)
- **Scheduling:** OpenClaw cron (17:00 ET daily)

## Directory Structure

```
/media/dan/fdrive/codeprojects/marcus/
  BUILD_PLAN.md                     # Original build plan (historical)
  Documentation/                    # You are here
  workspace/
    SOUL.md                         # Agent character and operational instructions
    SKILL.md → skills/curate/       # Skill definition
    USER.md                         # Dan's profile and interests
    IDENTITY.md                     # Quick identity reference
    AGENTS.md                       # Workspace protocol
    HEARTBEAT.md                    # Periodic health checks
    .openclaw/
      workspace-state.json
    memory/                         # Agent memory between sessions
    skills/
      curate/
        SKILL.md                    # Curation skill definition
        scripts/
          .venv/                    # Python virtual environment
          auth.py                   # OAuth token management
          subscriptions.py          # Subscription sync
          rss_check.py              # RSS feed polling
          metadata.py               # Video enrichment
          playlist.py               # YouTube playlist CRUD
          db.py                     # All database operations
          digest.py                 # Discord digest formatting
          run_daily.py              # Daily gather pipeline
          build_playlist.py         # Playlist clear and rebuild
```

## Phase History

- **Phase 0:** Infrastructure setup (YouTube API, Discord bot, PostgreSQL). Complete.
- **Phase 1:** Subscription watchdog with append-and-decay queue. Complete. Operational from 2026-03-18.
- **Phase 1.5:** Daily programme rebuild with news block, new tier system, full playlist overwrite. Current.
- **Phase 2:** Taste model and feedback loop via Discord. Planned.
- **Phase 3:** Discovery — surfacing videos from non-subscribed channels. Planned.
