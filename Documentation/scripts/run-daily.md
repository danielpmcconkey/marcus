# run_daily.py

`workspace/skills/curate/scripts/run_daily.py`

Daily gather pipeline. Checks RSS feeds for new uploads, enriches metadata, inserts into DB, and returns candidate videos for the agent to curate. Does NOT touch the YouTube playlist — that's `build_playlist.py`'s job.

## Usage

```bash
python3 run_daily.py                 # Standard daily run
python3 run_daily.py --sync-subs     # Sync subscriptions first, then run
```

## Pipeline Steps

1. **Load active channels** — `db.get_active_channels()` returns all subscribed channels (tiers 0-3).
2. **Check RSS feeds** — `rss_check.check_feeds(channels)` polls all channels in parallel (20 workers). Free, no API quota.
3. **Deduplicate** — Compares RSS video IDs against `marcus.video`. Only new videos proceed.
4. **Enrich metadata** — `metadata.enrich_videos(youtube, video_ids)` calls YouTube API in batches of 50. Extracts duration, description, thumbnail. Filters Shorts (< 60s).
5. **Merge** — Combines RSS data (channel_id, published_at) with enriched data (duration, description, thumbnail).
6. **Insert into DB** — `db.upsert_videos(merged)` inserts new videos with status `new`.
7. **Expire stale** — `db.expire_stale_videos(90)` marks videos older than 90 days as expired.
8. **Gather news candidates** — `db.get_news_candidates()` returns tier 0 videos from last 24h.
9. **Gather subscription picks** — `db.get_subscription_picks()` mechanically selects 3-5h of content.
10. **Log run** — `db.log_run(...)` records the run in `marcus.run_log`.

## Output

JSON to stdout:

```json
{
  "news_candidates": [
    {
      "video_id": "abc123",
      "channel_id": "UC...",
      "channel_name": "Reuters",
      "category": "general",
      "title": "Fed signals rate pause",
      "description": "...",
      "published_at": "2026-03-19T14:30:00+00:00",
      "duration_seconds": 180,
      "thumbnail_url": "https://..."
    }
  ],
  "subscription_picks": [
    {
      "video_id": "def456",
      "channel_id": "UC...",
      "channel_name": "Technology Connections",
      "category": "technology",
      "title": "Why LED bulbs flicker",
      "published_at": "2026-03-18T12:00:00+00:00",
      "duration_seconds": 1340,
      "tier": 1,
      "last_queued_at": null,
      "times_queued": 0
    }
  ],
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

Diagnostic output (RSS progress, enrichment batches, counts) goes to stderr.

## No-New-Videos Case

If RSS returns no new videos (or all are already known), the script still:
- Runs expiry
- Gathers news candidates (may exist from prior runs)
- Gathers subscription picks (from existing DB inventory)
- Logs the run

The output always has the same shape. `new_videos` will be 0.

## Subscription Sync

The `--sync-subs` flag calls `subscriptions.fetch_subscriptions()` and `subscriptions.sync_subscriptions()` before the main pipeline. New subscriptions are inserted at tier 2. Unsubscribed channels are marked `subscribed=FALSE` (tier 0 channels are protected).

Use sparingly — weekly or on-demand. The subscription list changes slowly.
