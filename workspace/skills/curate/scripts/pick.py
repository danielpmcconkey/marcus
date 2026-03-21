#!/usr/bin/env python3
"""Pick eligible videos from the database and output as JSON.

Used by Marcus for the "add" / "more" / "load it up" command.
Queries the DB for eligible videos filtered by tier and duration cap,
then outputs a video_ids list ready to pipe into build_playlist.py.

Usage:
    python3 pick.py --tiers 1,2 --max-seconds 7200
    python3 pick.py --tiers 1,2 --max-seconds 7200 | python3 build_playlist.py
"""

import argparse
import json

import db


def main():
    parser = argparse.ArgumentParser(description="Pick eligible videos from DB")
    parser.add_argument("--tiers", default="1,2,3",
                        help="Comma-separated tier numbers (default: 1,2,3)")
    parser.add_argument("--max-seconds", type=int, default=18000,
                        help="Target duration in seconds (default: 18000)")
    args = parser.parse_args()

    tiers = [int(t) for t in args.tiers.split(",")]
    picks, total_seconds = db.get_subscription_picks(
        target_seconds=args.max_seconds, tiers=tiers
    )

    result = {
        "video_ids": [p["video_id"] for p in picks],
        "details": [
            {
                "video_id": p["video_id"],
                "title": p["title"],
                "channel_name": p["channel_name"],
                "tier": p["tier"],
                "duration_seconds": p["duration_seconds"],
            }
            for p in picks
        ],
        "total_seconds": total_seconds,
        "count": len(picks),
    }

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
