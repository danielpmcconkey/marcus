#!/usr/bin/env python3
"""Check YouTube RSS feeds for new uploads.

For each active channel, fetches the RSS feed (no API quota cost) and
extracts entries newer than the channel's last_upload_at timestamp.

Uses concurrent.futures to parallelise HTTP requests (~20 workers).

Usage as module:
    from rss_check import check_feeds
    new_videos = check_feeds(channels)

Usage as CLI:
    python3 rss_check.py   # Check all active channels, print JSON
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
from xml.etree import ElementTree

import db

RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
MAX_WORKERS = 20
TIMEOUT_SECONDS = 15


def _fetch_feed(channel):
    """Fetch and parse RSS feed for a single channel.

    Returns (channel_id, entries) where entries is a list of dicts.
    On error, returns (channel_id, []) and logs to stderr.
    """
    channel_id = channel["channel_id"]
    url = RSS_URL_TEMPLATE.format(channel_id=channel_id)
    last_upload = channel.get("last_upload_at")

    try:
        req = Request(url, headers={"User-Agent": "Marcus-YouTube-Curator/1.0"})
        with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            xml_data = resp.read()
    except (URLError, OSError, TimeoutError) as e:
        print(f"RSS fetch failed for {channel_id}: {e}", file=sys.stderr)
        return channel_id, []

    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as e:
        print(f"RSS parse failed for {channel_id}: {e}", file=sys.stderr)
        return channel_id, []

    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    entries = []

    for entry in root.findall("atom:entry", ns):
        video_id_el = entry.find("yt:videoId", ns)
        title_el = entry.find("atom:title", ns)
        published_el = entry.find("atom:published", ns)

        if video_id_el is None or title_el is None or published_el is None:
            continue

        video_id = video_id_el.text.strip()
        title = title_el.text.strip() if title_el.text else ""
        published_str = published_el.text.strip()

        # Parse the published timestamp
        try:
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except ValueError:
            print(f"Bad date for {video_id}: {published_str}", file=sys.stderr)
            continue

        # Filter: only videos newer than channel's last_upload_at
        if last_upload is not None:
            # Ensure last_upload is timezone-aware
            if hasattr(last_upload, "tzinfo") and last_upload.tzinfo is None:
                last_upload = last_upload.replace(tzinfo=timezone.utc)
            if published_at <= last_upload:
                continue

        entries.append({
            "video_id": video_id,
            "channel_id": channel_id,
            "title": title,
            "published_at": published_at.isoformat(),
        })

    return channel_id, entries


def check_feeds(channels):
    """Check RSS feeds for all provided channels in parallel.

    channels: list of dicts with channel_id, channel_name, last_upload_at.
    Returns list of new video dicts.
    Also updates last_upload_at in DB for channels with new videos.
    """
    all_new = []
    newest_per_channel = {}

    print(f"Checking RSS for {len(channels)} channels...", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_feed, ch): ch for ch in channels}

        for future in as_completed(futures):
            try:
                channel_id, entries = future.result()
            except Exception as e:
                ch = futures[future]
                print(f"Unexpected error for {ch['channel_id']}: {e}", file=sys.stderr)
                continue

            if entries:
                all_new.extend(entries)
                # Track the newest published_at per channel for DB update
                for entry in entries:
                    pub = entry["published_at"]
                    if channel_id not in newest_per_channel or pub > newest_per_channel[channel_id]:
                        newest_per_channel[channel_id] = pub

    # Update last_upload_at for channels that had new videos
    for channel_id, newest_ts in newest_per_channel.items():
        try:
            db.update_channel_last_upload(channel_id, newest_ts)
        except Exception as e:
            print(f"Failed to update last_upload_at for {channel_id}: {e}", file=sys.stderr)

    print(f"Found {len(all_new)} new videos from {len(newest_per_channel)} channels.", file=sys.stderr)
    return all_new


def main():
    channels = db.get_active_channels()
    new_videos = check_feeds(channels)
    print(json.dumps(new_videos, indent=2, default=str))


if __name__ == "__main__":
    main()
