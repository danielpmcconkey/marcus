# build_playlist.py

`workspace/skills/curate/scripts/build_playlist.py`

Clears the "Marcus Queue" playlist and rebuilds it from an ordered list of video IDs. This is the write side of the daily programme build — the agent calls it after making curation decisions.

## Usage

```bash
# From stdin (typical — agent pipes curated list)
echo '{"video_ids": ["abc123", "def456"]}' | python3 build_playlist.py

# From file
python3 build_playlist.py --file /path/to/picks.json
```

## Input

JSON with a single key:

```json
{"video_ids": ["VIDEO_ID_1", "VIDEO_ID_2", "..."]}
```

Order matters — videos are inserted in the given order. News block first, subscriptions after.

## Pipeline Steps

1. **Read input** — from stdin or `--file` argument.
2. **Authenticate** — `get_youtube_service()`.
3. **Get playlist ID** — `playlist.ensure_playlist(youtube)`. Checks DB cache, verifies with YouTube API.
4. **Reset DB statuses** — `db.reset_playlist_statuses()` sets all currently `queued` videos back to `new`, clears their `playlist_item_id`.
5. **Clear playlist** — Lists all items in the YouTube playlist, deletes each one. 50 API units per delete.
6. **Insert videos** — Adds each video to the playlist in order. 50 API units per insert.
7. **Update DB** — For each successfully inserted video, calls `db.update_video_status(vid, 'queued', item_id)` which sets status, `playlist_item_id`, `last_queued_at`, and increments `times_queued`.

## Output

JSON to stdout:

```json
{
  "cleared": 30,
  "inserted": 28,
  "failed": 2,
  "units_used": 4100,
  "playlist_items": [
    {"video_id": "abc123", "playlist_item_id": "UExh..."},
    {"video_id": "def456", "playlist_item_id": "UExb..."}
  ]
}
```

## Error Handling

Individual video insert failures are logged to stderr and skipped. The build continues with remaining videos. The `failed` count in the output reports how many videos could not be added.

Common failure reasons:
- Video is private or deleted
- Video is region-restricted
- YouTube API rate limiting (unlikely within our quota budget)

## Quota Cost

| Operation | Cost | Count |
|-----------|------|-------|
| `playlist.list_playlist()` | 1 unit/page | ~1 |
| `playlist.remove_from_playlist()` | 50 units | N (old items) |
| `playlist.add_to_playlist()` | 50 units | M (new items) |

For a typical rebuild: clear 30 + insert 30 = ~3,001 units.
