#!/usr/bin/env python3
"""Build the Marcus Queue playlist from an ordered list of video IDs.

Clears the existing playlist completely, then inserts videos in the
specified order. Updates video statuses in the database.

The agent calls run_daily.py first to gather candidates, makes news
curation decisions, then pipes the final ordered list here.

Usage:
    echo '{"video_ids": ["abc", "def"]}' | python3 build_playlist.py
    python3 build_playlist.py --file /path/to/picks.json
"""

import argparse
import json
import sys

from auth import get_youtube_service
import db
import playlist


def clear_playlist(youtube, playlist_id):
    """Remove all items from the playlist.

    Returns (count_deleted, units_used).
    """
    items = playlist.list_playlist(youtube, playlist_id)
    units = 1  # list call
    deleted = 0

    for item in items:
        ok = playlist.remove_from_playlist(youtube, item["playlist_item_id"])
        if ok:
            deleted += 1
            units += 50

    return deleted, units


def build(youtube, playlist_id, video_ids):
    """Insert videos into playlist in order.

    Returns (results_list, units_used).
    """
    results = []
    units = 0

    for vid in video_ids:
        item_id = playlist.add_to_playlist(youtube, playlist_id, vid)
        units += 50
        if item_id:
            results.append({"video_id": vid, "playlist_item_id": item_id})
        else:
            print(f"Failed to add {vid} to playlist.", file=sys.stderr)

    return results, units


def run(video_ids):
    """Full playlist rebuild: clear, build, update DB."""
    if not video_ids:
        return {
            "cleared": 0,
            "inserted": 0,
            "failed": 0,
            "units_used": 0,
            "error": "No video IDs provided.",
        }

    youtube = get_youtube_service()
    playlist_id = playlist.ensure_playlist(youtube)
    total_units = 1  # ensure_playlist check

    # Reset DB statuses from previous build
    reset_count = db.reset_playlist_statuses()
    if reset_count:
        print(f"Reset {reset_count} previously queued videos.", file=sys.stderr)

    # Clear the playlist
    print(f"Clearing playlist {playlist_id}...", file=sys.stderr)
    cleared, clear_units = clear_playlist(youtube, playlist_id)
    total_units += clear_units
    print(f"Cleared {cleared} items ({clear_units} units).", file=sys.stderr)

    # Build the new playlist
    print(f"Building playlist with {len(video_ids)} videos...", file=sys.stderr)
    results, build_units = build(youtube, playlist_id, video_ids)
    total_units += build_units
    print(f"Inserted {len(results)}/{len(video_ids)} ({build_units} units).",
          file=sys.stderr)

    # Update DB: mark inserted videos as queued
    for item in results:
        db.update_video_status(
            item["video_id"], "queued",
            playlist_item_id=item["playlist_item_id"]
        )

    failed = len(video_ids) - len(results)

    return {
        "cleared": cleared,
        "inserted": len(results),
        "failed": failed,
        "units_used": total_units,
        "playlist_items": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Marcus playlist rebuild")
    parser.add_argument("--file", metavar="PATH",
                        help="Read video IDs from a JSON file instead of stdin")
    args = parser.parse_args()

    # Read input
    if args.file:
        with open(args.file) as f:
            data = json.load(f)
    else:
        raw = sys.stdin.read().strip()
        if not raw:
            print(json.dumps({"error": "No input on stdin"}), file=sys.stdout)
            sys.exit(1)
        data = json.loads(raw)

    video_ids = data.get("video_ids", [])

    try:
        result = run(video_ids)
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        error_result = {"error": str(e)}
        print(json.dumps(error_result, indent=2), file=sys.stdout)
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
