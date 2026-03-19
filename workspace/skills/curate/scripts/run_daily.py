#!/usr/bin/env python3
"""Main orchestrator for Marcus daily curation run.

Steps:
  1. Load active channels from DB
  2. Check RSS feeds for new uploads
  3. Deduplicate against existing video rows
  4. Enrich new videos with metadata
  5. Filter out Shorts (duration < 60s) — done inside metadata.py
  6. Insert new videos into DB
  7. Auto-queue tier 1 videos to playlist
  8. Expire stale videos (> 3 days in 'queued' or 'presented')
  9. Generate digest
  10. Log the run
  11. Output JSON result to stdout

Usage:
    python3 run_daily.py                 # Standard daily run
    python3 run_daily.py --sync-subs     # Sync subscriptions first, then run
"""

import argparse
import json
import sys

from auth import get_youtube_service
import db
import digest
import metadata
import playlist
import rss_check
import subscriptions


# ── Per-channel filters ────────────────────────────────────────────
# Keyed by channel_id. Each entry can specify:
#   max_duration_seconds: drop individual videos longer than this
#   max_total_seconds:    cumulative runtime cap (newest videos first)
#   filter_live:          drop live/upcoming broadcasts
CHANNEL_FILTERS = {
    "UChqUTb7kYRX8-EiaN3XFrSQ": {  # Reuters
        "max_duration_seconds": 300,   # 5 minutes
        "max_total_seconds": 1200,     # 20 minutes cumulative
        "filter_live": True,
    },
}


def _apply_channel_filters(videos, name_lookup):
    """Apply per-channel filters (duration cap, runtime cap, live filter).

    Returns (kept, filtered_count).
    """
    # Separate filtered channels from the rest
    filtered_ids = set(CHANNEL_FILTERS.keys())
    passthrough = [v for v in videos if v["channel_id"] not in filtered_ids]
    filtered_count = 0

    for ch_id, rules in CHANNEL_FILTERS.items():
        ch_videos = [v for v in videos if v["channel_id"] == ch_id]
        if not ch_videos:
            continue

        ch_name = name_lookup.get(ch_id, ch_id)
        before = len(ch_videos)

        # Filter live/upcoming broadcasts
        if rules.get("filter_live"):
            ch_videos = [v for v in ch_videos
                         if v.get("live_broadcast", "none") == "none"]

        # Filter individual videos over max duration
        max_dur = rules.get("max_duration_seconds")
        if max_dur:
            ch_videos = [v for v in ch_videos
                         if (v.get("duration_seconds") or 0) <= max_dur]

        # Apply cumulative runtime cap (newest first)
        max_total = rules.get("max_total_seconds")
        if max_total and ch_videos:
            ch_videos.sort(key=lambda v: v.get("published_at") or "", reverse=True)
            kept = []
            running = 0
            for v in ch_videos:
                dur = v.get("duration_seconds") or 0
                if running + dur <= max_total:
                    kept.append(v)
                    running += dur
            ch_videos = kept

        dropped = before - len(ch_videos)
        if dropped:
            print(f"Channel filter [{ch_name}]: kept {len(ch_videos)}/{before} "
                  f"(dropped {dropped}).", file=sys.stderr)
        filtered_count += dropped
        passthrough.extend(ch_videos)

    return passthrough, filtered_count


def run(sync_subs=False):
    """Execute the full daily curation pipeline. Returns result dict."""
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
            "digest": "No active channels. Nothing to curate.",
            "stats": {"channels_checked": 0, "new_videos": 0, "queued": 0},
        }

    print(f"Loaded {len(channels)} active channels.", file=sys.stderr)

    # Build tier lookup: channel_id -> tier
    tier_lookup = {ch["channel_id"]: ch["tier"] for ch in channels}
    name_lookup = {ch["channel_id"]: ch["channel_name"] for ch in channels}

    # ── Step 2: Check RSS feeds ──────────────────────────────────
    rss_videos = rss_check.check_feeds(channels)
    if not rss_videos:
        print("No new videos from RSS.", file=sys.stderr)
        # Still run decay and generate digest
        expired = db.expire_stale_videos(max_age_days=3)
        stats = {
            "channels_checked": len(channels),
            "new_videos": 0,
            "queued": 0,
            "shorts_filtered": 0,
        }
        digest_text = digest.format_digest([], [], stats, expired)
        run_id = db.log_run(
            channels_checked=len(channels),
            new_videos=0,
            queued=0,
            digest_posted=False,
            notes="No new videos from RSS."
        )
        return {
            "digest": digest_text,
            "stats": stats,
            "expired_count": len(expired),
            "run_id": run_id,
        }

    # ── Step 3: Deduplicate ──────────────────────────────────────
    candidate_ids = [v["video_id"] for v in rss_videos]
    existing_ids = db.get_existing_video_ids(candidate_ids)
    new_rss = [v for v in rss_videos if v["video_id"] not in existing_ids]
    dedup_count = len(rss_videos) - len(new_rss)

    if dedup_count:
        print(f"Deduplicated {dedup_count} already-known videos.", file=sys.stderr)

    if not new_rss:
        print("All RSS videos already known.", file=sys.stderr)
        expired = db.expire_stale_videos(max_age_days=3)
        stats = {
            "channels_checked": len(channels),
            "new_videos": 0,
            "queued": 0,
            "shorts_filtered": 0,
        }
        digest_text = digest.format_digest([], [], stats, expired)
        run_id = db.log_run(
            channels_checked=len(channels),
            new_videos=0,
            queued=0,
            digest_posted=False,
            notes=f"All {dedup_count} RSS videos already known."
        )
        return {
            "digest": digest_text,
            "stats": stats,
            "expired_count": len(expired),
            "run_id": run_id,
        }

    # ── Step 4: Enrich with metadata ─────────────────────────────
    new_video_ids = [v["video_id"] for v in new_rss]
    enriched = metadata.enrich_videos(youtube, new_video_ids)
    shorts_filtered = len(new_video_ids) - len(enriched)

    # Merge RSS data (published_at, channel_id) with enriched data
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

    print(f"{len(merged)} videos after metadata enrichment and Shorts filter.", file=sys.stderr)

    # ── Step 4b: Apply per-channel filters ─────────────────────
    merged, channel_filtered = _apply_channel_filters(merged, name_lookup)

    # ── Step 5: Insert into DB ───────────────────────────────────
    inserted = db.upsert_videos(merged)
    print(f"Inserted {inserted} new videos.", file=sys.stderr)

    # ── Step 6: Auto-queue tier 1 videos ─────────────────────────
    playlist_id = playlist.ensure_playlist(youtube)
    tier1_videos = []
    tier2_videos = []
    queued_count = 0

    for video in merged:
        ch_id = video["channel_id"]
        tier = tier_lookup.get(ch_id, 2)
        video["channel_name"] = name_lookup.get(ch_id, "Unknown")

        if tier == 1:
            # Auto-queue
            item_id = playlist.add_to_playlist(youtube, playlist_id, video["video_id"])
            if item_id:
                db.update_video_status(video["video_id"], "queued", playlist_item_id=item_id)
                video["playlist_item_id"] = item_id
                queued_count += 1
            tier1_videos.append(video)
        elif tier == 2:
            db.update_video_status(video["video_id"], "presented")
            tier2_videos.append(video)
        # tier 3 channels shouldn't appear (filtered by get_active_channels), but just in case
        # they get status 'new' and are ignored in the digest

    print(f"Queued {queued_count} tier 1 videos.", file=sys.stderr)

    # ── Step 7: Expire stale videos ──────────────────────────────
    expired = db.expire_stale_videos(max_age_days=3)
    if expired:
        print(f"Expired {len(expired)} stale videos.", file=sys.stderr)

    # ── Step 8: Generate digest ──────────────────────────────────
    stats = {
        "channels_checked": len(channels),
        "new_videos": len(merged),
        "queued": queued_count,
        "shorts_filtered": shorts_filtered,
        "channel_filtered": channel_filtered,
    }
    digest_text = digest.format_digest(tier1_videos, tier2_videos, stats, expired)

    # ── Step 9: Log the run ──────────────────────────────────────
    run_id = db.log_run(
        channels_checked=len(channels),
        new_videos=len(merged),
        queued=queued_count,
        digest_posted=False,
        notes=None,
    )

    # ── Step 10: Output ──────────────────────────────────────────
    result = {
        "digest": digest_text,
        "stats": stats,
        "tier1_count": len(tier1_videos),
        "tier2_count": len(tier2_videos),
        "expired_count": len(expired),
        "run_id": run_id,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Marcus daily curation run")
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
