#!/usr/bin/env python3
"""Main orchestrator for Marcus daily programme build.

Gathers candidate videos for the evening programme. Does NOT touch the
playlist — that's build_playlist.py's job. Returns structured JSON for
the agent (Marcus) to curate news and confirm subscription picks.

Steps:
  1. Load active channels (tiers 0-3)
  2. Check RSS feeds for new uploads
  3. Deduplicate against existing video rows
  4. Enrich new videos with metadata (filter Shorts)
  5. Insert new videos into DB
  6. Expire videos older than 90 days
  7. Gather news candidates (tier 0, last 24h)
  8. Gather subscription picks (tiers 1-3, mechanical selection)
  9. Log the run
  10. Output JSON to stdout

Usage:
    python3 run_daily.py                 # Standard daily run
    python3 run_daily.py --sync-subs     # Sync subscriptions first, then run
"""

import argparse
import json
import sys

from auth import get_youtube_service
import db
import metadata
import rss_check
import subscriptions


def run(sync_subs=False):
    """Execute the daily gather pipeline. Returns result dict."""
    youtube = get_youtube_service()

    # ── Step 0 (optional): Sync subscriptions ────────────────────
    if sync_subs:
        print("Syncing subscriptions...", file=sys.stderr)
        subs = subscriptions.fetch_subscriptions(youtube)
        sub_result = subscriptions.sync_subscriptions(subs)
        print(f"Sub sync: {json.dumps(sub_result)}", file=sys.stderr)

    # ── Step 1: Load active channels ─────────────────────────────
    channels = db.get_active_channels()
    if not channels:
        print("No active channels found.", file=sys.stderr)
        return {
            "news_candidates": [],
            "subscription_picks": [],
            "stats": {"channels_checked": 0, "new_videos": 0},
        }

    print(f"Loaded {len(channels)} active channels.", file=sys.stderr)

    # ── Step 2: Check RSS feeds ──────────────────────────────────
    rss_videos = rss_check.check_feeds(channels)
    new_video_count = 0
    shorts_filtered = 0

    if rss_videos:
        # ── Step 3: Deduplicate ──────────────────────────────────
        candidate_ids = [v["video_id"] for v in rss_videos]
        existing_ids = db.get_existing_video_ids(candidate_ids)
        new_rss = [v for v in rss_videos if v["video_id"] not in existing_ids]
        dedup_count = len(rss_videos) - len(new_rss)

        if dedup_count:
            print(f"Deduplicated {dedup_count} already-known videos.", file=sys.stderr)

        if new_rss:
            # ── Step 4: Enrich with metadata ─────────────────────
            new_video_ids = [v["video_id"] for v in new_rss]
            enriched = metadata.enrich_videos(youtube, new_video_ids)
            shorts_filtered = len(new_video_ids) - len(enriched)

            # Merge RSS data with enriched data
            rss_by_id = {v["video_id"]: v for v in new_rss}
            merged = []
            for ev in enriched:
                vid = ev["video_id"]
                rss_data = rss_by_id.get(vid, {})
                merged.append({
                    "video_id": vid,
                    "channel_id": rss_data.get("channel_id") or ev.get("channel_id"),
                    "title": ev.get("title") or rss_data.get("title", ""),
                    "description": ev.get("description"),
                    "published_at": rss_data.get("published_at"),
                    "duration_seconds": ev.get("duration_seconds"),
                    "thumbnail_url": ev.get("thumbnail_url"),
                    "live_broadcast": ev.get("live_broadcast", "none"),
                    "status": "new",
                })

            print(f"{len(merged)} videos after enrichment and Shorts filter.", file=sys.stderr)

            # ── Step 5: Insert into DB ───────────────────────────
            inserted = db.upsert_videos(merged)
            new_video_count = inserted
            print(f"Inserted {inserted} new videos.", file=sys.stderr)

    # ── Step 6: Expire stale videos (90-day window) ──────────────
    expired = db.expire_stale_videos(max_age_days=90)
    if expired:
        print(f"Expired {len(expired)} videos (>90 days old).", file=sys.stderr)

    # ── Step 7: Gather news candidates ───────────────────────────
    news_candidates = db.get_news_candidates()
    print(f"News candidates: {len(news_candidates)} videos from tier 0.", file=sys.stderr)

    # ── Step 7.5: Gather Spanish learning picks ────────────────
    spanish_picks, spanish_total_seconds = db.get_spanish_picks()
    spanish_mins = spanish_total_seconds / 60
    print(f"Spanish picks: {len(spanish_picks)} videos, "
          f"{spanish_mins:.0f}min total.", file=sys.stderr)

    # ── Step 8: Gather subscription picks ────────────────────────
    sub_picks, sub_total_seconds = db.get_subscription_picks()
    sub_hours = sub_total_seconds / 3600
    print(f"Subscription picks: {len(sub_picks)} videos, "
          f"{sub_hours:.1f}h total.", file=sys.stderr)

    # ── Step 9: Log the run ──────────────────────────────────────
    run_id = db.log_run(
        channels_checked=len(channels),
        new_videos=new_video_count,
        queued=0,  # playlist build happens separately
        digest_posted=False,
        notes=None,
    )

    # ── Step 10: Output ──────────────────────────────────────────
    # Serialise RealDictRow objects to plain dicts
    news_out = [dict(r) for r in news_candidates]
    spanish_out = [dict(r) for r in spanish_picks]
    sub_out = [dict(r) for r in sub_picks]

    result = {
        "news_candidates": news_out,
        "spanish_picks": spanish_out,
        "subscription_picks": sub_out,
        "stats": {
            "channels_checked": len(channels),
            "new_videos": new_video_count,
            "shorts_filtered": shorts_filtered,
            "expired": len(expired),
            "news_candidate_count": len(news_candidates),
            "spanish_pick_count": len(spanish_picks),
            "spanish_total_seconds": spanish_total_seconds,
            "subscription_pick_count": len(sub_picks),
            "subscription_total_seconds": sub_total_seconds,
        },
        "run_id": run_id,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Marcus daily programme gather")
    parser.add_argument("--sync-subs", action="store_true",
                        help="Sync YouTube subscriptions before the daily run")
    args = parser.parse_args()

    try:
        result = run(sync_subs=args.sync_subs)
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        error_result = {"error": str(e)}
        print(json.dumps(error_result, indent=2), file=sys.stdout)
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
