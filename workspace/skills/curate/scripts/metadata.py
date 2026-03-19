#!/usr/bin/env python3
"""Enrich videos with YouTube API metadata.

Takes video IDs, calls videos.list in batches of 50, extracts
title, description, duration, and thumbnail. Filters out Shorts.

Usage as module:
    from metadata import enrich_videos
    enriched = enrich_videos(youtube_service, video_ids)

Usage as CLI:
    echo '["dQw4w9WgXcQ","abc123"]' | python3 metadata.py
    python3 metadata.py VIDEO_ID1 VIDEO_ID2 ...
"""

import json
import re
import sys

from auth import get_youtube_service


def _parse_iso8601_duration(duration_str):
    """Parse ISO 8601 duration (e.g. PT1H2M30S) to seconds."""
    if not duration_str:
        return None
    match = re.match(
        r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$",
        duration_str
    )
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def enrich_videos(youtube, video_ids):
    """Fetch metadata for a list of video IDs.

    Calls videos.list in batches of 50.
    Returns list of enriched video dicts.
    Filters out Shorts (duration < 60 seconds).
    """
    if not video_ids:
        return []

    enriched = []
    shorts_filtered = 0

    # Process in batches of 50
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        print(f"Fetching metadata batch {i // 50 + 1} ({len(batch)} videos)...", file=sys.stderr)

        try:
            response = youtube.videos().list(
                part="snippet,contentDetails",
                id=",".join(batch),
            ).execute()
        except Exception as e:
            print(f"API error fetching metadata batch: {e}", file=sys.stderr)
            continue

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})

            duration_seconds = _parse_iso8601_duration(content.get("duration"))

            # Filter out Shorts (< 60 seconds)
            if duration_seconds is not None and duration_seconds < 60:
                shorts_filtered += 1
                continue

            # Best thumbnail: maxres > high > medium > default
            thumbs = snippet.get("thumbnails", {})
            thumbnail_url = None
            for quality in ("maxres", "high", "medium", "default"):
                if quality in thumbs:
                    thumbnail_url = thumbs[quality].get("url")
                    break

            description = snippet.get("description", "")
            if description and len(description) > 500:
                description = description[:500]

            enriched.append({
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "description": description,
                "duration_seconds": duration_seconds,
                "thumbnail_url": thumbnail_url,
                "channel_id": snippet.get("channelId"),
                "live_broadcast": snippet.get("liveBroadcastContent", "none"),
            })

    if shorts_filtered:
        print(f"Filtered {shorts_filtered} Shorts (< 60s).", file=sys.stderr)

    return enriched


def main():
    # Accept video IDs from stdin JSON or as command-line args
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            video_ids = json.loads(raw)
        else:
            video_ids = []
    else:
        video_ids = sys.argv[1:]

    if not video_ids:
        print(json.dumps({"error": "No video IDs provided"}))
        sys.exit(1)

    youtube = get_youtube_service()
    enriched = enrich_videos(youtube, video_ids)
    print(json.dumps(enriched, indent=2))


if __name__ == "__main__":
    main()
