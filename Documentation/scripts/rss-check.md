# rss_check.py

`workspace/skills/curate/scripts/rss_check.py`

Polls YouTube RSS feeds for new uploads. Parallel execution with 20 workers, 15-second timeout per feed. Zero API quota cost.

## How It Works

For each active channel, fetches `https://www.youtube.com/feeds/videos.xml?channel_id={id}`. Parses Atom XML for `<entry>` elements with a `published` date newer than the channel's `last_upload_at` in the database.

After finding new videos, updates `last_upload_at` for each channel that had new content. This ensures the next run only picks up videos published after the last check.

## Functions

| Function | Description |
|----------|-------------|
| `check_feeds(channels)` | Main entry point. Takes list of channel dicts (from `db.get_active_channels()`). Returns list of `{video_id, channel_id, title, published_at}`. Updates `last_upload_at` in DB. |

## Performance

- 200 channels at 20 workers = ~10-15 seconds total
- Each feed returns up to 15 most recent uploads
- Only entries newer than `last_upload_at` are returned
- User-Agent: `Marcus-YouTube-Curator/1.0`

## Edge Cases

- **Feed fetch timeout:** Logged to stderr, channel skipped. Other channels continue.
- **XML parse error:** Logged, channel skipped.
- **Bad date format:** Individual entry skipped.
- **Timezone handling:** `last_upload_at` is compared timezone-aware. Naive timestamps are assumed UTC.

## CLI

```bash
python3 rss_check.py    # Check all active channels, print new videos as JSON
```
