#!/usr/bin/env python3
"""Database operations for Marcus. All SQL lives here.

Uses the marcus schema in the openclaw database.
Connection credentials from /media/dan/fdrive/marcus/.pgpass.
"""

import json
import sys

import psycopg2
import psycopg2.extras

PGPASS_PATH = "/media/dan/fdrive/marcus/.pgpass"


def _read_pgpass():
    """Parse .pgpass file for connection params."""
    with open(PGPASS_PATH) as f:
        line = f.readline().strip()
    host, port, dbname, user, password = line.split(":")
    return dict(host=host, port=int(port), dbname=dbname, user=user, password=password)


def get_connection():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(**_read_pgpass())


# Aliases for convenience
connect = get_connection


# ── Channel operations ──────────────────────────────────────────────

def get_active_channels():
    """Return all channels with tier 1 or 2 that are still subscribed."""
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT channel_id, channel_name, tier, last_upload_at
                FROM marcus.channel
                WHERE subscribed = TRUE AND tier IN (1, 2)
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
    """Set a channel's tier (1, 2, or 3)."""
    if tier not in (1, 2, 3):
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
                    SET status = %s, playlist_item_id = %s, queued_at = now()
                    WHERE video_id = %s
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


def expire_stale_videos(max_age_days=3):
    """Expire videos older than max_age_days that are still 'queued' or 'presented'.

    Returns list of expired video dicts (for digest reporting).
    """
    with connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                UPDATE marcus.video
                SET status = 'expired', expired_at = now()
                WHERE status IN ('queued', 'presented')
                  AND created_at < now() - interval '%s days'
                RETURNING video_id, channel_id, title, status
            """, (max_age_days,))
            expired = cur.fetchall()
        conn.commit()
    return expired


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
    """Quick connectivity check."""
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, version()")
                row = cur.fetchone()
                # Check if marcus schema tables exist
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
