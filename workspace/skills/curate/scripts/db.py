#!/usr/bin/env python3
"""Database operations for Marcus. All SQL lives here.

Uses the marcus schema in the openclaw database.
Connection credentials from pass store (openclaw/marcus/pgpass).
"""

import json
import subprocess
import sys

import psycopg2
import psycopg2.extras


def _read_pgpass():
    """Read connection params from pass store."""
    line = subprocess.check_output(
        ["pass", "show", "openclaw/marcus/pgpass"], text=True
    ).strip()
    host, port, dbname, user, password = line.split(":")
    return dict(host=host, port=int(port), dbname=dbname, user=user, password=password)


def get_connection():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(**_read_pgpass())


# Aliases for convenience
connect = get_connection


# ── Channel operations ──────────────────────────────────────────────

def get_active_channels():
    """Return all subscribed channels (tiers 0-3)."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id, channel_name, tier, category, last_upload_at
                FROM marcus.channel
                WHERE subscribed = TRUE AND tier IN (0, 1, 2, 3, 4)
                ORDER BY tier, channel_name
            """)
            return cur.fetchall()


def get_tier1_channels():
    """Return all tier 1 (auto-queue) channels."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id, channel_name, last_upload_at
                FROM marcus.channel
                WHERE subscribed = TRUE AND tier = 1
                ORDER BY channel_name
            """)
            return cur.fetchall()


def upsert_channels(channels):
    """Insert or update channels. channels is a list of {channel_id, channel_name}.

    New channels get tier 2. Existing channels get their name updated.
    Returns (inserted, updated) counts.
    """
    inserted = 0
    updated = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for ch in channels:
                cur.execute("""
                    INSERT INTO marcus.channel (channel_id, channel_name, tier, subscribed)
                    VALUES (%s, %s, 2, TRUE)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        subscribed = TRUE,
                        updated_at = now()
                    RETURNING (xmax = 0) AS is_insert
                """, (ch["channel_id"], ch["channel_name"]))
                row = cur.fetchone()
                if row[0]:
                    inserted += 1
                else:
                    updated += 1
        conn.commit()
    return inserted, updated


def mark_unsubscribed(active_channel_ids):
    """Mark channels not in active_channel_ids as unsubscribed.

    Returns count of channels marked unsubscribed.
    """
    if not active_channel_ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.channel
                SET subscribed = FALSE, updated_at = now()
                WHERE subscribed = TRUE
                  AND tier NOT IN (0, 4)
                  AND channel_id != ALL(%s)
            """, (list(active_channel_ids),))
            count = cur.rowcount
        conn.commit()
    return count


def update_channel_last_upload(channel_id, last_upload_at):
    """Set the last_upload_at timestamp for a channel."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.channel
                SET last_upload_at = %s, updated_at = now()
                WHERE channel_id = %s
            """, (last_upload_at, channel_id))
        conn.commit()


def set_channel_tier(channel_id, tier):
    """Set a channel's tier (0=news, 1=must-watch, 2=priority, 3=filler, 4=spanish)."""
    if tier not in (0, 1, 2, 3, 4):
        raise ValueError(f"Invalid tier: {tier}")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.channel
                SET tier = %s, updated_at = now()
                WHERE channel_id = %s
            """, (tier, channel_id))
        conn.commit()


# ── Video operations ────────────────────────────────────────────────

def get_existing_video_ids(video_ids):
    """Given a list of video IDs, return the set that already exist in DB."""
    if not video_ids:
        return set()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT video_id FROM marcus.video
                WHERE video_id = ANY(%s)
            """, (list(video_ids),))
            return {row[0] for row in cur.fetchall()}


def upsert_videos(videos):
    """Insert new videos. videos is a list of dicts with keys:
    video_id, channel_id, title, description, published_at,
    duration_seconds, thumbnail_url, status.

    Returns count inserted.
    """
    if not videos:
        return 0
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for v in videos:
                cur.execute("""
                    INSERT INTO marcus.video
                        (video_id, channel_id, title, description, published_at,
                         duration_seconds, thumbnail_url, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (video_id) DO NOTHING
                """, (
                    v["video_id"], v["channel_id"], v["title"],
                    v.get("description"), v["published_at"],
                    v.get("duration_seconds"), v.get("thumbnail_url"),
                    v.get("status", "new"),
                ))
                inserted += cur.rowcount
        conn.commit()
    return inserted


def update_video_status(video_id, status, playlist_item_id=None):
    """Update a video's status. Optionally set playlist_item_id and queued_at."""
    with connect() as conn:
        with conn.cursor() as cur:
            if status == "queued":
                cur.execute("""
                    UPDATE marcus.video
                    SET status = %s, playlist_item_id = %s, queued_at = now(),
                        last_queued_at = now(), times_queued = times_queued + 1
                    WHERE video_id = %s
                      AND status NOT IN ('watched', 'skipped')
                """, (status, playlist_item_id, video_id))
            elif status == "expired":
                cur.execute("""
                    UPDATE marcus.video
                    SET status = %s, expired_at = now()
                    WHERE video_id = %s
                """, (status, video_id))
            else:
                cur.execute("""
                    UPDATE marcus.video
                    SET status = %s
                    WHERE video_id = %s
                """, (status, video_id))
        conn.commit()


def expire_stale_videos(max_age_days=90):
    """Expire videos older than max_age_days (by published_at).

    Marks non-terminal videos as expired, removing them from the candidate pool.
    Returns list of expired video dicts.
    """
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                UPDATE marcus.video
                SET status = 'expired', expired_at = now()
                WHERE status NOT IN ('watched', 'skipped', 'expired')
                  AND published_at < now() - interval '%s days'
                RETURNING video_id, channel_id, title, status
            """, (max_age_days,))
            expired = cur.fetchall()
        conn.commit()
    return expired


# ── Programme build queries ─────────────────────────────────────────

def get_spanish_picks(target_seconds=2700, min_seconds=1800):
    """Select tier 4 (Spanish learning) videos for the daily programme.

    Fills a 30-45 minute block. Duration cap: 25 min per video.
    Within tier: newest first, deprioritise recently queued.

    target_seconds: 2700 = 45 min (upper bound)
    min_seconds: 1800 = 30 min (lower bound, best-effort)
    """
    DEFAULT_DURATION = 600  # 10 min for videos with unknown duration
    DURATION_CAP = 1500  # 25 min per video

    picks = []
    running_total = 0

    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT v.video_id, v.channel_id, c.channel_name, c.category,
                       v.title, v.description, v.published_at,
                       v.duration_seconds, v.thumbnail_url,
                       c.tier, v.last_queued_at, v.times_queued
                FROM marcus.video v
                JOIN marcus.channel c ON v.channel_id = c.channel_id
                WHERE c.tier = 4 AND c.subscribed = TRUE
                  AND v.published_at > now() - interval '90 days'
                  AND v.status NOT IN ('watched', 'skipped', 'expired')
                  AND COALESCE(v.duration_seconds, 0) >= 60
                  AND COALESCE(v.duration_seconds, %s) <= %s
                ORDER BY v.published_at DESC,
                         v.last_queued_at ASC NULLS FIRST
            """, (DEFAULT_DURATION, DURATION_CAP))

            for row in cur:
                dur = row["duration_seconds"] or DEFAULT_DURATION
                if running_total + dur > target_seconds:
                    continue
                picks.append(dict(row))
                running_total += dur

    return picks, running_total


def get_news_candidates():
    """Return tier 0 videos from the last 24 hours, <=5 min, for agent curation."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT v.video_id, v.channel_id, c.channel_name, c.category,
                       v.title, v.description, v.published_at,
                       v.duration_seconds, v.thumbnail_url
                FROM marcus.video v
                JOIN marcus.channel c ON v.channel_id = c.channel_id
                WHERE c.tier = 0 AND c.subscribed = TRUE
                  AND v.published_at > now() - interval '24 hours'
                  AND v.status NOT IN ('watched', 'skipped', 'expired')
                  AND COALESCE(v.duration_seconds, 0) <= 300
                ORDER BY v.published_at DESC
            """)
            return cur.fetchall()


def get_subscription_picks(target_seconds=18000, min_seconds=10800, tiers=None):
    """Mechanically select subscription videos for the daily programme.

    Fills from tier 1 (no duration cap), then tier 2 (<=25 min),
    then tier 3 (<=25 min). Within each tier: newest first, deprioritise
    recently queued. Stops at target_seconds. Returns ordered list.

    target_seconds: 18000 = 5 hours (upper bound)
    min_seconds: 10800 = 3 hours (lower bound, best-effort)
    tiers: list of tier numbers to include (default: [1, 2, 3])
    """
    DEFAULT_DURATION = 600  # 10 min for videos with unknown duration
    TIER_DURATION_CAP = {1: None, 2: 1500, 3: 1500}  # 25 min = 1500s

    if tiers is None:
        tiers = [1, 2, 3]

    picks = []
    running_total = 0

    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for tier in tiers:
                if running_total >= target_seconds:
                    break

                cap = TIER_DURATION_CAP[tier]
                duration_filter = ""
                if cap is not None:
                    duration_filter = f"AND COALESCE(v.duration_seconds, {DEFAULT_DURATION}) <= {cap}"

                cur.execute(f"""
                    SELECT v.video_id, v.channel_id, c.channel_name, c.category,
                           v.title, v.description, v.published_at,
                           v.duration_seconds, v.thumbnail_url,
                           c.tier, v.last_queued_at, v.times_queued
                    FROM marcus.video v
                    JOIN marcus.channel c ON v.channel_id = c.channel_id
                    WHERE c.tier = %s AND c.subscribed = TRUE
                      AND v.published_at > now() - interval '90 days'
                      AND v.status NOT IN ('watched', 'skipped', 'expired')
                      AND COALESCE(v.duration_seconds, 0) >= 60
                      {duration_filter}
                    ORDER BY v.published_at DESC,
                             v.last_queued_at ASC NULLS FIRST
                """, (tier,))

                for row in cur:
                    dur = row["duration_seconds"] or DEFAULT_DURATION
                    if running_total + dur > target_seconds:
                        continue  # skip this one, might fit a shorter video
                    picks.append(dict(row))
                    running_total += dur

    return picks, running_total


def reset_playlist_statuses():
    """Reset all 'queued' videos back to 'new' for playlist rebuild.

    Clears playlist_item_id. Called before each daily rebuild.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marcus.video
                SET status = 'new', playlist_item_id = NULL
                WHERE status = 'queued'
            """)
            count = cur.rowcount
        conn.commit()
    return count


def add_news_channel(channel_id, channel_name, category=None):
    """Add a tier 0 (news) channel. Not a YouTube subscription."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.channel
                    (channel_id, channel_name, tier, subscribed, category)
                VALUES (%s, %s, 0, TRUE, %s)
                ON CONFLICT (channel_id) DO UPDATE SET
                    channel_name = EXCLUDED.channel_name,
                    tier = 0,
                    subscribed = TRUE,
                    category = EXCLUDED.category,
                    updated_at = now()
            """, (channel_id, channel_name, category))
        conn.commit()


# ── Run log ─────────────────────────────────────────────────────────

def log_run(channels_checked, new_videos, queued, digest_posted=False, notes=None):
    """Insert a run_log entry. Returns the new row id."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.run_log
                    (channels_checked, new_videos, queued, digest_posted, notes)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (channels_checked, new_videos, queued, digest_posted, notes))
            row_id = cur.fetchone()[0]
        conn.commit()
    return row_id


# ── Playlist config ─────────────────────────────────────────────────

def get_playlist_config():
    """Get the cached playlist ID from a simple config table.

    Returns the playlist_id string or None.
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT value FROM marcus.config
                WHERE key = 'playlist_id'
            """)
            row = cur.fetchone()
            return row[0] if row else None


def save_playlist_config(playlist_id):
    """Save the playlist ID to the config table."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marcus.config (key, value)
                VALUES ('playlist_id', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (playlist_id,))
        conn.commit()


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Marcus DB utilities")
    parser.add_argument("--check", action="store_true",
                        help="Quick connectivity check")
    parser.add_argument("--set-status", nargs=2, metavar=("VIDEO_ID", "STATUS"),
                        help="Set a video's status (e.g. watched, skipped)")
    args = parser.parse_args()

    if args.set_status:
        video_id, status = args.set_status
        valid = ("new", "queued", "watched", "skipped", "expired")
        if status not in valid:
            print(json.dumps({"error": f"Invalid status '{status}'. Must be one of: {', '.join(valid)}"}))
            sys.exit(1)
        update_video_status(video_id, status)
        print(json.dumps({"action": "set_status", "video_id": video_id, "status": status}))
    else:
        # Default: connectivity check (same as --check)
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database(), current_user, version()")
                    row = cur.fetchone()
                    cur.execute("""
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema = 'marcus'
                        ORDER BY table_name
                    """)
                    tables = [r[0] for r in cur.fetchall()]
            result = {
                "status": "connected",
                "database": row[0],
                "user": row[1],
                "pg_version": row[2],
                "marcus_tables": tables,
            }
        except Exception as e:
            result = {"status": "error", "error": str(e)}
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
