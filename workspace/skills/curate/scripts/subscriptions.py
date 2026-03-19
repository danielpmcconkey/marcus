#!/usr/bin/env python3
"""Fetch YouTube subscription list and sync to database.

Usage as module:
    from subscriptions import fetch_subscriptions, sync_subscriptions
    subs = fetch_subscriptions(youtube_service)
    result = sync_subscriptions(subs)

Usage as CLI:
    python3 subscriptions.py              # Fetch subs, sync to DB, print JSON summary
    python3 subscriptions.py --fetch-only # Fetch subs, print JSON, don't touch DB
"""

import json
import sys

from auth import get_youtube_service
import db


def fetch_subscriptions(youtube):
    """Fetch all subscriptions for the authenticated user.

    Paginates through the full list.
    Returns list of {channel_id, channel_name}.
    """
    subs = []
    request = youtube.subscriptions().list(
        part="snippet",
        mine=True,
        maxResults=50,
    )

    page = 0
    while request is not None:
        page += 1
        print(f"Fetching subscriptions page {page}...", file=sys.stderr)
        response = request.execute()

        for item in response.get("items", []):
            snippet = item["snippet"]
            subs.append({
                "channel_id": snippet["resourceId"]["channelId"],
                "channel_name": snippet["title"],
            })

        request = youtube.subscriptions().list_next(request, response)

    print(f"Fetched {len(subs)} subscriptions.", file=sys.stderr)
    return subs


def sync_subscriptions(subs):
    """Sync subscription list to DB.

    - Insert new channels at tier 2
    - Mark channels no longer in the sub list as unsubscribed
    Returns summary dict.
    """
    inserted, updated = db.upsert_channels(subs)

    active_ids = [s["channel_id"] for s in subs]
    unsub_count = db.mark_unsubscribed(active_ids)

    return {
        "total_subscriptions": len(subs),
        "new_channels": inserted,
        "updated_channels": updated,
        "unsubscribed": unsub_count,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Marcus subscription sync")
    parser.add_argument("--fetch-only", action="store_true",
                        help="Fetch and print subscriptions without syncing to DB")
    args = parser.parse_args()

    youtube = get_youtube_service()
    subs = fetch_subscriptions(youtube)

    if args.fetch_only:
        print(json.dumps(subs, indent=2))
    else:
        result = sync_subscriptions(subs)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
