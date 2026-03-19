# Database

PostgreSQL, database `openclaw`, schema `marcus`. Role `marcus` owns the schema with full control within it. No access to other schemas.

Credentials in `pass` store at `openclaw/marcus/pgpass` (format: `host:port:dbname:user:password`).

## Tables

### `marcus.channel`

Tracks YouTube channels — both subscriptions and manually added news outlets.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `channel_id` | TEXT PK | | YouTube channel ID (`UC...`) |
| `channel_name` | TEXT NOT NULL | | Display name |
| `tier` | SMALLINT NOT NULL | 2 | 0=news, 1=must-watch, 2=priority, 3=filler |
| `subscribed` | BOOLEAN NOT NULL | TRUE | FALSE = soft-deleted / unsubscribed |
| `category` | TEXT | NULL | Free-form category (e.g., "technology", "politics") |
| `last_upload_at` | TIMESTAMPTZ | NULL | Most recent video seen from this channel |
| `created_at` | TIMESTAMPTZ NOT NULL | `now()` | |
| `updated_at` | TIMESTAMPTZ NOT NULL | `now()` | |

**Tier semantics:**

| Tier | Role | Duration cap | Selection window | Source |
|------|------|-------------|-----------------|--------|
| 0 | News | 5 min/video | 24 hours | Manually added |
| 1 | Must-watch | None | 3 months | YouTube subscription |
| 2 | Priority | 25 min/video | 3 months | YouTube subscription (default for new subs) |
| 3 | Filler | 25 min/video | 3 months | YouTube subscription |

Tier 0 channels are NOT YouTube subscriptions. They are news outlets added directly via `db.add_news_channel()`. The subscription sync (`subscriptions.py`) will never mark them as unsubscribed — the `mark_unsubscribed()` query explicitly excludes `tier != 0`.

### `marcus.video`

Every video Marcus has ever seen via RSS. One row per video, never deleted.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `video_id` | TEXT PK | | YouTube video ID |
| `channel_id` | TEXT NOT NULL | | FK → `marcus.channel` |
| `title` | TEXT NOT NULL | | |
| `description` | TEXT | NULL | First ~500 chars |
| `published_at` | TIMESTAMPTZ NOT NULL | | YouTube publish timestamp |
| `duration_seconds` | INTEGER | NULL | NULL if metadata enrichment failed |
| `thumbnail_url` | TEXT | NULL | |
| `status` | TEXT NOT NULL | `'new'` | See status values below |
| `playlist_item_id` | TEXT | NULL | YouTube's ID for the playlist entry (needed for removal) |
| `queued_at` | TIMESTAMPTZ | NULL | When first queued |
| `last_queued_at` | TIMESTAMPTZ | NULL | When most recently placed in playlist |
| `times_queued` | INTEGER NOT NULL | 0 | How many times this video has been in the playlist |
| `expired_at` | TIMESTAMPTZ | NULL | When expired from candidate pool |
| `created_at` | TIMESTAMPTZ NOT NULL | `now()` | When Marcus first discovered this video |

**Status values:**

| Status | Meaning | Transition from |
|--------|---------|----------------|
| `new` | Just discovered, eligible for selection | Initial state, or reset after playlist rebuild |
| `queued` | Currently in the playlist | `new` (via `build_playlist.py`) |
| `presented` | Shown in digest but not queued (legacy Phase 1) | `new` |
| `watched` | Dan confirmed watched (Phase 2) | `queued` |
| `skipped` | Dan explicitly skipped (Phase 2) | `queued`, `new` |
| `expired` | Aged out of the candidate pool (>90 days) | Any non-terminal status |

In the daily programme model, `queued` is set during playlist build and reset to `new` at the start of the next build via `reset_playlist_statuses()`. Videos can cycle between `new` and `queued` across multiple days.

### `marcus.run_log`

One row per daily run. Diagnostic only.

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | SERIAL PK | | |
| `run_at` | TIMESTAMPTZ NOT NULL | `now()` | |
| `channels_checked` | INTEGER | | |
| `new_videos` | INTEGER | | |
| `queued` | INTEGER | | |
| `digest_posted` | BOOLEAN | FALSE | |
| `notes` | TEXT | NULL | |

### `marcus.config`

Simple key-value store. Currently holds one entry: `playlist_id`.

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT PK | |
| `value` | TEXT | |

## Indexes

```sql
-- Eligibility window: videos from last 90 days not in terminal states
CREATE INDEX idx_video_published_status ON marcus.video (published_at DESC)
  WHERE status NOT IN ('watched', 'skipped', 'expired');
```

## Common Queries

**All active channels (used by RSS check):**
```sql
SELECT channel_id, channel_name, tier, category, last_upload_at
FROM marcus.channel
WHERE subscribed = TRUE AND tier IN (0, 1, 2, 3)
ORDER BY tier, channel_name;
```

**News candidates (tier 0, last 24h, ≤5 min):**
```sql
SELECT v.*, c.channel_name, c.category
FROM marcus.video v JOIN marcus.channel c ON v.channel_id = c.channel_id
WHERE c.tier = 0 AND c.subscribed = TRUE
  AND v.published_at > now() - interval '24 hours'
  AND v.status NOT IN ('watched', 'skipped', 'expired')
  AND COALESCE(v.duration_seconds, 0) <= 300
ORDER BY v.published_at DESC;
```

**Subscription picks (per tier, newest first, deprioritise recently queued):**
```sql
SELECT v.*, c.channel_name, c.tier
FROM marcus.video v JOIN marcus.channel c ON v.channel_id = c.channel_id
WHERE c.tier = :tier AND c.subscribed = TRUE
  AND v.published_at > now() - interval '90 days'
  AND v.status NOT IN ('watched', 'skipped', 'expired')
  AND COALESCE(v.duration_seconds, 0) >= 60
  -- duration cap applied per tier (none for tier 1, 1500s for tier 2/3)
ORDER BY v.published_at DESC, v.last_queued_at ASC NULLS FIRST;
```
