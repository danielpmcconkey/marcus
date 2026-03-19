#!/usr/bin/env python3
"""Format the daily digest for Discord.

Takes run results and produces a Discord-friendly message with
Marcus Brody character voice.

Usage as module:
    from digest import format_digest
    message = format_digest(tier1_videos, tier2_videos, stats, expired)

Usage as CLI:
    echo '<json>' | python3 digest.py
"""

import json
import sys
from datetime import datetime


def _video_line_queued(video):
    """Format a single tier 1 (auto-queued) video line."""
    title = video.get("title", "Unknown")
    channel = video.get("channel_name", "")
    duration = video.get("duration_seconds")

    parts = [f"  {title}"]
    if channel:
        parts[0] += f" — *{channel}*"
    if duration:
        mins = duration // 60
        secs = duration % 60
        parts[0] += f" ({mins}:{secs:02d})"

    return parts[0]


def _video_line_digest(video):
    """Format a single tier 2 (digest-only) video line with link."""
    title = video.get("title", "Unknown")
    channel = video.get("channel_name", "")
    video_id = video.get("video_id", "")
    duration = video.get("duration_seconds")

    link = f"https://youtu.be/{video_id}" if video_id else ""
    parts = [f"  [{title}]({link})"]
    if channel:
        parts[0] += f" — *{channel}*"
    if duration:
        mins = duration // 60
        secs = duration % 60
        parts[0] += f" ({mins}:{secs:02d})"

    return parts[0]


def format_digest(tier1_videos, tier2_videos, stats, expired=None):
    """Format the full daily digest message.

    tier1_videos: list of dicts (auto-queued, with channel_name merged in)
    tier2_videos: list of dicts (digest-only, with channel_name merged in)
    stats: dict with channels_checked, new_videos, queued, shorts_filtered
    expired: list of expired video dicts (optional)
    """
    lines = []

    # Opening — Marcus Brody voice
    total_new = len(tier1_videos) + len(tier2_videos)
    if total_new == 0:
        lines.append("**Daily Curation Report**")
        lines.append("")
        lines.append("A quiet day at the museum, I'm afraid. No new acquisitions "
                      "to speak of. The collection remains as it was.")
        if expired:
            lines.append("")
            lines.append(f"I did, however, retire {len(expired)} piece(s) from the "
                          "viewing queue — age and neglect, the twin enemies of any curator.")
    else:
        lines.append("**Daily Curation Report**")
        lines.append("")
        if total_new == 1:
            lines.append("A single specimen today. Quality over quantity, as I always say.")
        elif total_new <= 5:
            lines.append("A modest selection today. I've examined each piece carefully.")
        else:
            lines.append("Quite the haul today. I've sorted through the lot and separated "
                          "the genuine articles from the... well, you know.")

    # Tier 1: auto-queued
    if tier1_videos:
        lines.append("")
        lines.append("**Added to the Queue** (tier 1 — trusted sources)")
        for video in tier1_videos:
            lines.append(_video_line_queued(video))

    # Tier 2: digest-only
    if tier2_videos:
        lines.append("")
        lines.append("**For Your Consideration** (tier 2 — your call, old boy)")

        # Group by channel
        by_channel = {}
        for video in tier2_videos:
            ch = video.get("channel_name", "Unknown")
            by_channel.setdefault(ch, []).append(video)

        for channel_name, videos in sorted(by_channel.items()):
            if len(by_channel) > 1:
                lines.append(f"  **{channel_name}**")
            for video in videos:
                lines.append(_video_line_digest(video))

    # Expired
    if expired:
        lines.append("")
        lines.append(f"**Retired** ({len(expired)} expired from queue)")

    # Stats footer
    lines.append("")
    lines.append("---")
    channels_checked = stats.get("channels_checked", 0)
    new_count = stats.get("new_videos", 0)
    queued_count = stats.get("queued", 0)
    shorts_count = stats.get("shorts_filtered", 0)
    expired_count = len(expired) if expired else 0

    stat_parts = [f"{channels_checked} channels surveyed"]
    stat_parts.append(f"{new_count} new")
    if queued_count:
        stat_parts.append(f"{queued_count} queued")
    if shorts_count:
        stat_parts.append(f"{shorts_count} Shorts dismissed")
    channel_filtered = stats.get("channel_filtered", 0)
    if channel_filtered:
        stat_parts.append(f"{channel_filtered} channel-filtered")
    if expired_count:
        stat_parts.append(f"{expired_count} expired")
    lines.append("*" + " | ".join(stat_parts) + "*")

    return "\n".join(lines)


def main():
    """Read run data from stdin, produce digest to stdout."""
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "No input provided on stdin"}))
        sys.exit(1)

    data = json.loads(raw)
    tier1 = data.get("tier1_videos", [])
    tier2 = data.get("tier2_videos", [])
    stats = data.get("stats", {})
    expired = data.get("expired", [])

    message = format_digest(tier1, tier2, stats, expired)
    print(json.dumps({"digest": message}, indent=2))


if __name__ == "__main__":
    main()
