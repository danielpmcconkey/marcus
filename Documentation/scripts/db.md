# db.py

`workspace/skills/curate/scripts/db.py`

All database operations for Marcus. Every SQL query lives here — no other script constructs SQL directly. Uses `psycopg2` with `RealDictCursor` for dict-style row access.

Credentials are read from `pass show openclaw/marcus/pgpass` on every `get_connection()` call.

## Connection

| Function | Description |
|----------|-------------|
| `get_connection()` | Returns a new `psycopg2` connection. Reads credentials from `pass` store. |
| `connect` | Alias for `get_connection()`. |

Each function opens its own connection via `with connect() as conn:`. No connection pooling. Acceptable for the daily batch workload (< 50 queries per run).

## Channel Operations

| Function | Description |
|----------|-------------|
| `get_active_channels()` | All channels with `subscribed=TRUE` and `tier IN (0,1,2,3)`. Returns list of dicts with `channel_id`, `channel_name`, `tier`, `category`, `last_upload_at`. |
| `get_tier1_channels()` | Convenience: tier 1 only. |
| `upsert_channels(channels)` | Insert or update from a list of `{channel_id, channel_name}`. New channels get tier 2. Returns `(inserted, updated)` counts. |
| `mark_unsubscribed(active_channel_ids)` | Sets `subscribed=FALSE` for channels not in the provided list. **Excludes tier 0** — news channels are never touched by subscription sync. |
| `update_channel_last_upload(channel_id, ts)` | Sets `last_upload_at` for a channel. Called by `rss_check.py` after finding new videos. |
| `set_channel_tier(channel_id, tier)` | Sets tier. Validates `tier in (0, 1, 2, 3)`. |
| `add_news_channel(channel_id, name, category)` | Insert a tier 0 channel. Upserts — if the channel exists, sets it to tier 0 with the given category. |

## Video Operations

| Function | Description |
|----------|-------------|
| `get_existing_video_ids(video_ids)` | Given a list of video IDs, returns the set that already exist in DB. Used for deduplication. |
| `upsert_videos(videos)` | Insert new videos. `ON CONFLICT DO NOTHING`. Returns count inserted. |
| `update_video_status(video_id, status, playlist_item_id)` | Update a video's status. When `status='queued'`, also sets `queued_at`, `last_queued_at`, and increments `times_queued`. When `status='expired'`, sets `expired_at`. |
| `expire_stale_videos(max_age_days=90)` | Marks videos as `expired` where `published_at` is older than `max_age_days` and status is not terminal (`watched`, `skipped`, `expired`). Returns list of expired video dicts. |

## Programme Build Queries

| Function | Description |
|----------|-------------|
| `get_news_candidates()` | Tier 0 videos from last 24 hours, ≤5 min, not in terminal status. Joined with channel name and category. Ordered by `published_at DESC`. |
| `get_subscription_picks(target_seconds, min_seconds)` | Mechanical selection for the subscription block. Iterates tiers 1→2→3, newest first, respecting duration caps (none for tier 1, 25 min for 2/3). Accumulates until `target_seconds` (default 18,000 = 5h). Returns `(picks_list, total_seconds)`. Videos with NULL duration budgeted at 600s. |
| `reset_playlist_statuses()` | Sets all `queued` videos back to `new`, clears `playlist_item_id`. Called at the start of each playlist rebuild. Returns count reset. |

## Run Log

| Function | Description |
|----------|-------------|
| `log_run(channels_checked, new_videos, queued, digest_posted, notes)` | Insert a `run_log` entry. Returns the new row ID. |

## Playlist Config

| Function | Description |
|----------|-------------|
| `get_playlist_config()` | Returns the cached playlist ID string, or None. |
| `save_playlist_config(playlist_id)` | Saves/updates the playlist ID in `marcus.config`. |

## CLI

```bash
python3 db.py    # Quick connectivity check — prints database, user, version, tables
```
