# Marcus Documentation

Quick reference for navigating the codebase. Each doc is self-contained.

| Looking for... | Go to |
|---|---|
| What Marcus is and why it exists | [overview.md](overview.md) |
| Database schema, tiers, video statuses | [database.md](database.md) |
| Daily programme build flow (gather → curate → build) | [pipeline.md](pipeline.md) |
| YouTube API constraints, quota budget, OAuth | [youtube-api.md](youtube-api.md) |
| Secrets, cron, exec-approvals, OpenClaw config | [configuration.md](configuration.md) |
| Script architecture and shared patterns | [scripts/overview.md](scripts/overview.md) |
| `db.py` — all database operations | [scripts/db.md](scripts/db.md) |
| `run_daily.py` — daily gather pipeline | [scripts/run-daily.md](scripts/run-daily.md) |
| `build_playlist.py` — playlist clear and rebuild | [scripts/build-playlist.md](scripts/build-playlist.md) |
| `playlist.py` — YouTube playlist CRUD | [scripts/playlist.md](scripts/playlist.md) |
| `rss_check.py` — RSS feed polling | [scripts/rss-check.md](scripts/rss-check.md) |
| `metadata.py` — video metadata enrichment | [scripts/metadata.md](scripts/metadata.md) |
| `digest.py` — Discord programme digest | [scripts/digest.md](scripts/digest.md) |
| `auth.py` — OAuth token management | [scripts/auth.md](scripts/auth.md) |
| `subscriptions.py` — YouTube subscription sync | [scripts/subscriptions.md](scripts/subscriptions.md) |
