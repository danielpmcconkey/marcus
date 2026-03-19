#!/usr/bin/env python3
"""Format the evening programme digest for Discord.

Takes the curated news block and subscription picks and produces a
Discord-friendly message with Marcus Brody character voice.

Usage as module:
    from digest import format_digest
    message = format_digest(news_block, subscription_block, stats)
"""

import json
import sys


TIER_LABELS = {
    0: "News",
    1: "Must Watch",
    2: "Priority",
    3: "Also Playing",
}


def _format_duration(seconds):
    """Format seconds as H:MM:SS or M:SS."""
    if not seconds:
        return "?:??"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _format_total_duration(seconds):
    """Format total seconds as friendly string like '4h 12m'."""
    if not seconds:
        return "0m"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    if hours:
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    return f"{mins}m"


def _video_line(video):
    """Format a single video line: title — channel (duration)."""
    title = video.get("title", "Unknown")
    channel = video.get("channel_name", "")
    duration = video.get("duration_seconds")

    line = f"  {title}"
    if channel:
        line += f" — *{channel}*"
    if duration:
        line += f" ({_format_duration(duration)})"
    return line


def format_digest(news_block, subscription_block, stats):
    """Format the full evening programme digest.

    news_block: list of video dicts (agent-curated news picks)
    subscription_block: list of video dicts (mechanically selected, with 'tier' key)
    stats: dict with channels_checked, new_videos, subscription_total_seconds, etc.
    """
    lines = []

    # ── Opening ──────────────────────────────────────────────────
    total_videos = len(news_block) + len(subscription_block)
    sub_seconds = stats.get("subscription_total_seconds", 0)
    news_seconds = sum(v.get("duration_seconds") or 0 for v in news_block)
    total_seconds = news_seconds + sub_seconds

    lines.append("**Tonight's Programme**")
    lines.append("")

    if total_videos == 0:
        lines.append("A rather bare evening, I'm afraid. The galleries are empty. "
                      "Perhaps tomorrow will bring better pickings.")
    elif total_videos <= 5:
        lines.append("A lean selection this evening — but every piece is worth your time.")
    else:
        lines.append("Your evening viewing is prepared. "
                      f"~{_format_total_duration(total_seconds)} of curated content.")

    # ── News block ───────────────────────────────────────────────
    if news_block:
        lines.append("")
        lines.append(f"**News Block** (~{_format_total_duration(news_seconds)})")
        for video in news_block:
            lines.append(_video_line(video))

    # ── Subscription block ───────────────────────────────────────
    if subscription_block:
        lines.append("")

        # Group by tier
        by_tier = {}
        for video in subscription_block:
            tier = video.get("tier", 2)
            by_tier.setdefault(tier, []).append(video)

        for tier in sorted(by_tier.keys()):
            label = TIER_LABELS.get(tier, f"Tier {tier}")
            tier_videos = by_tier[tier]
            tier_seconds = sum(v.get("duration_seconds") or 0 for v in tier_videos)
            lines.append(f"**{label}** ({len(tier_videos)} videos, "
                         f"~{_format_total_duration(tier_seconds)})")
            for video in tier_videos:
                lines.append(_video_line(video))
            lines.append("")

    # ── Stats footer ─────────────────────────────────────────────
    lines.append("---")
    channels_checked = stats.get("channels_checked", 0)
    new_count = stats.get("new_videos", 0)
    shorts_count = stats.get("shorts_filtered", 0)
    expired_count = stats.get("expired", 0)

    stat_parts = [f"{channels_checked} channels"]
    if new_count:
        stat_parts.append(f"{new_count} new")
    stat_parts.append(f"{total_videos} queued")
    stat_parts.append(f"~{_format_total_duration(total_seconds)}")
    if shorts_count:
        stat_parts.append(f"{shorts_count} Shorts dismissed")
    if expired_count:
        stat_parts.append(f"{expired_count} expired")

    lines.append("*" + " | ".join(stat_parts) + "*")

    return "\n".join(lines)


def main():
    """Read programme data from stdin, produce digest to stdout."""
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"error": "No input provided on stdin"}))
        sys.exit(1)

    data = json.loads(raw)
    news = data.get("news_block", [])
    subs = data.get("subscription_block", [])
    stats = data.get("stats", {})

    message = format_digest(news, subs, stats)
    print(json.dumps({"digest": message}, indent=2))


if __name__ == "__main__":
    main()
