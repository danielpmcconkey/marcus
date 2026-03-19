# Scripts Overview

All scripts live at `/media/dan/fdrive/codeprojects/marcus/workspace/skills/curate/scripts/`.

Python 3, venv at `.venv/` in the same directory. Dependencies: `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `psycopg2-binary`.

## Script Inventory

| Script | Role | Called by | Touches YouTube? | Touches DB? |
|--------|------|-----------|-----------------|-------------|
| `run_daily.py` | Gather pipeline — RSS, enrich, candidate selection | Agent (cron) | Yes (metadata) | Yes |
| `build_playlist.py` | Playlist clear and rebuild | Agent (after curation) | Yes (playlist CRUD) | Yes |
| `db.py` | All database operations | Other scripts | No | Yes |
| `playlist.py` | YouTube playlist CRUD | `build_playlist.py`, agent | Yes | Yes (config cache) |
| `rss_check.py` | RSS feed polling | `run_daily.py` | No | Yes (last_upload_at) |
| `metadata.py` | Video metadata enrichment | `run_daily.py` | Yes (videos.list) | No |
| `digest.py` | Discord programme digest formatting | Agent | No | No |
| `auth.py` | OAuth token management | All YouTube scripts | No (manages tokens) | No |
| `subscriptions.py` | YouTube subscription sync | Agent (on-demand) | Yes (subscriptions.list) | Yes |

## Shared Patterns

**Secrets:** All scripts that need credentials use `pass show openclaw/marcus/...` via `subprocess.check_output`. No plaintext files.

**JSON I/O:** Scripts that serve as pipeline stages read from stdin and write to stdout (JSON). Diagnostic output goes to stderr. This enables piping between stages.

**Error handling:** Top-level `try/except` in `main()` catches exceptions and outputs a JSON error object to stdout. Individual operations (RSS fetch, API call, DB write) catch and log failures without aborting the full run.

**CLI + module:** Every script works as both a module (`from X import Y`) and a CLI (`python3 X.py --flag`). The `if __name__ == "__main__"` block handles CLI usage.

## Data Flow

```
                    run_daily.py
                    ┌──────────┐
                    │          │
          ┌────────┤  gather  ├────────┐
          │        │          │        │
          ▼        └──────────┘        ▼
    rss_check.py              metadata.py
    (RSS feeds)               (YouTube API)
          │                        │
          └──────┐    ┌────────────┘
                 ▼    ▼
                 db.py
              (PostgreSQL)
                   │
                   ▼
            Agent (Claude)
          curates news block
                   │
                   ▼
          build_playlist.py
          ┌──────────────┐
          │ clear + build │──── playlist.py ──── YouTube API
          └──────────────┘
                   │
                   ▼
              digest.py
          (format for Discord)
```
