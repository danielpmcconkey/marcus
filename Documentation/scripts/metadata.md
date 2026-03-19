# metadata.py

`workspace/skills/curate/scripts/metadata.py`

Enriches videos with YouTube API metadata. Takes video IDs, calls `videos.list` in batches of 50, extracts title, description, duration, and thumbnail. Filters out Shorts.

## Functions

| Function | Description |
|----------|-------------|
| `enrich_videos(youtube, video_ids)` | Fetches metadata in batches of 50. Returns list of enriched video dicts. Filters out Shorts (< 60s). |

## API Call

```
youtube.videos().list(part="snippet,contentDetails", id="ID1,ID2,...")
```

Cost: 1 unit per call. Up to 50 IDs per call. For 100 new videos, that's 2 units.

## Enriched Fields

| Field | Source | Notes |
|-------|--------|-------|
| `video_id` | `item.id` | |
| `title` | `snippet.title` | |
| `description` | `snippet.description` | Truncated to 500 chars |
| `duration_seconds` | `contentDetails.duration` | Parsed from ISO 8601 (`PT1H2M30S` → seconds) |
| `thumbnail_url` | `snippet.thumbnails` | Best available: maxres > high > medium > default |
| `channel_id` | `snippet.channelId` | |
| `live_broadcast` | `snippet.liveBroadcastContent` | `"none"`, `"live"`, or `"upcoming"` |

## Shorts Filtering

Videos with `duration_seconds < 60` are silently dropped. The count of filtered Shorts is logged to stderr.

## Duration Parsing

ISO 8601 durations (`PT1H2M30S`) are parsed to integer seconds via regex. Handles missing components: `PT30S` = 30, `PT1H` = 3600, `PT5M` = 300.

Returns None if the duration string is absent or unparseable — downstream code should handle NULL durations.

## CLI

```bash
# From stdin
echo '["dQw4w9WgXcQ"]' | python3 metadata.py

# From arguments
python3 metadata.py dQw4w9WgXcQ abc123
```
