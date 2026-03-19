# Pipeline

The daily programme build is a two-phase pipeline: **gather** (Python) then **curate + build** (agent + Python). The agent sits between the two phases and makes the news curation decision.

## Flow

```
17:00 ET — OpenClaw cron wakes Marcus

Phase 1: GATHER (run_daily.py)
  ┌─────────────────────────────────────────┐
  │  Load active channels (tiers 0-3)       │
  │  Check RSS feeds (parallel, 20 workers) │
  │  Dedup against existing videos          │
  │  Enrich metadata via YouTube API        │
  │  Filter Shorts (< 60s)                  │
  │  Insert new videos into DB              │
  │  Expire videos > 90 days               │
  │  Query news candidates (tier 0, 24h)    │
  │  Query subscription picks (tiers 1-3)   │
  └─────────────┬───────────────────────────┘
                │ JSON output
                ▼
Phase 2: CURATE (agent — Marcus/Claude)
  ┌─────────────────────────────────────────┐
  │  Read news_candidates                   │
  │  Cluster by story                       │
  │  Pick one representative per story      │
  │  Ensure diversity (channels, topics)    │
  │  Target 20-30 minutes                   │
  │  Combine: [news picks] + [sub picks]   │
  └─────────────┬───────────────────────────┘
                │ Ordered video ID list (JSON)
                ▼
Phase 3: BUILD (build_playlist.py)
  ┌─────────────────────────────────────────┐
  │  Reset DB playlist statuses             │
  │  Clear entire YouTube playlist          │
  │  Insert videos in order                 │
  │  Update DB with playlist_item_ids       │
  └─────────────┬───────────────────────────┘
                │ JSON summary
                ▼
Phase 4: DIGEST (agent)
  ┌─────────────────────────────────────────┐
  │  Format programme summary               │
  │  Post to Discord #marcus_museum         │
  └─────────────────────────────────────────┘
```

## Phase 1: Gather (`run_daily.py`)

**Input:** None (reads from DB and RSS feeds).

**What it does:**
1. Loads all channels with `subscribed=TRUE` and `tier IN (0, 1, 2, 3)`.
2. Polls RSS feeds in parallel (20 threads, 15s timeout per feed). RSS is free — no API quota cost. Each channel's feed returns up to 15 most recent uploads.
3. Deduplicates: checks which video IDs already exist in `marcus.video`.
4. Enriches new videos via YouTube API `videos.list` (batched, 50 per call, 1 unit per call). Extracts duration, description, thumbnail. Filters Shorts (< 60s).
5. Inserts new videos into `marcus.video` with status `new`.
6. Expires videos with `published_at` older than 90 days.
7. Queries `get_news_candidates()` — all tier 0 videos from the last 24 hours, ≤5 min each.
8. Queries `get_subscription_picks()` — mechanically selects 3-5 hours of content from tiers 1/2/3.

**Output (JSON to stdout):**
```json
{
  "news_candidates": [...],
  "subscription_picks": [...],
  "stats": {
    "channels_checked": 200,
    "new_videos": 15,
    "shorts_filtered": 3,
    "expired": 2,
    "news_candidate_count": 12,
    "subscription_pick_count": 25,
    "subscription_total_seconds": 16200
  },
  "run_id": 42
}
```

## Subscription Selection Algorithm

The `get_subscription_picks()` function fills the programme mechanically:

1. **Tier 1** — all eligible videos, no duration cap, newest first. These always get priority.
2. **Tier 2** — eligible videos ≤25 minutes, newest first. Fills after tier 1.
3. **Tier 3** — eligible videos ≤25 minutes, newest first. Fills remaining time.

Within each tier, videos are ordered by `published_at DESC, last_queued_at ASC NULLS FIRST`. This means fresh content first, and among equally fresh content, videos that haven't been in the playlist recently get preference.

The function stops accumulating when cumulative runtime hits 18,000 seconds (5 hours). Minimum target is 10,800 seconds (3 hours) — below that, the function has exhausted all eligible videos.

Videos with NULL `duration_seconds` are budgeted at 600 seconds (10 minutes) for accumulation purposes.

## Phase 2: Curate (Agent)

The agent reads `news_candidates` and applies editorial judgment:

- **Story clustering:** Multiple outlets covering the same event = one story. The agent reads titles and groups them.
- **One per story:** Pick the most concise/informative representative.
- **Diversity:** Spread across channels and categories. Don't stack 5 videos from one outlet.
- **Duration target:** 20-30 minutes total. All videos ≤5 minutes.

The agent then combines `[news picks] + [subscription_picks]` into a single ordered list of video IDs.

This is the only point in the pipeline that requires LLM intelligence. Everything else is mechanical.

## Phase 3: Build (`build_playlist.py`)

**Input (JSON on stdin):**
```json
{"video_ids": ["abc123", "def456", ...]}
```

**What it does:**
1. Calls `reset_playlist_statuses()` — sets all currently `queued` videos back to `new`, clears `playlist_item_id`.
2. Lists all items in the YouTube playlist and deletes each one (50 API units per delete).
3. Inserts videos in the specified order (50 API units per insert).
4. Updates `marcus.video` for each inserted video: status → `queued`, sets `playlist_item_id`, increments `times_queued`, updates `last_queued_at`.

**Output (JSON to stdout):**
```json
{
  "cleared": 30,
  "inserted": 28,
  "failed": 0,
  "units_used": 4100,
  "playlist_items": [...]
}
```

## Phase 4: Digest (Agent)

The agent formats a Discord message summarising the programme:
- News block with titles, channels, durations
- Subscription block grouped by tier
- Stats footer (channels checked, videos queued, total duration)

Posts to `#marcus_museum`.

## Error Handling

- **RSS failures:** Individual channel timeouts are logged and skipped. The rest of the run continues.
- **Metadata enrichment failures:** Videos that fail enrichment are dropped from that run. They'll be picked up next time if they appear in RSS again.
- **Playlist insert failures:** Logged and skipped. The build continues with remaining videos. The output reports `failed` count.
- **Total pipeline failure:** `run_daily.py` and `build_playlist.py` both catch top-level exceptions and output JSON error objects to stdout. The agent can report the error to Discord.
