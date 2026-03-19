#!/usr/bin/env python3
"""Custom playlist management for Marcus.

Manages the "Marcus Queue" playlist — create, add, remove, list.
Playlist ID is cached in DB to avoid re-lookup each run.

Usage as module:
    from playlist import ensure_playlist, add_to_playlist, remove_from_playlist, list_playlist

Usage as CLI:
    python3 playlist.py --ensure          # Create playlist if needed, print ID
    python3 playlist.py --add VIDEO_ID    # Add video to playlist
    python3 playlist.py --remove ITEM_ID  # Remove item from playlist
    python3 playlist.py --list            # List current playlist contents
"""

import json
import sys

from auth import get_youtube_service
import db

PLAYLIST_TITLE = "Marcus Queue"
PLAYLIST_DESCRIPTION = "Curated by Marcus — your YouTube subscription watchdog."


def ensure_playlist(youtube):
    """Create the Marcus Queue playlist if it doesn't exist. Return playlist ID.

    Checks DB cache first. If not cached, searches existing playlists.
    If not found, creates it. Caches the ID in DB.
    """
    # Check DB cache
    cached_id = db.get_playlist_config()
    if cached_id:
        # Verify it still exists
        try:
            response = youtube.playlists().list(
                part="id",
                id=cached_id,
            ).execute()
            if response.get("items"):
                print(f"Playlist found (cached): {cached_id}", file=sys.stderr)
                return cached_id
            else:
                print("Cached playlist ID no longer valid. Searching...", file=sys.stderr)
        except Exception as e:
            print(f"Error verifying cached playlist: {e}", file=sys.stderr)

    # Search existing playlists for one with our title
    try:
        request = youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50,
        )
        while request is not None:
            response = request.execute()
            for item in response.get("items", []):
                if item["snippet"]["title"] == PLAYLIST_TITLE:
                    playlist_id = item["id"]
                    db.save_playlist_config(playlist_id)
                    print(f"Playlist found (search): {playlist_id}", file=sys.stderr)
                    return playlist_id
            request = youtube.playlists().list_next(request, response)
    except Exception as e:
        print(f"Error searching playlists: {e}", file=sys.stderr)
        raise

    # Create it
    print("Creating Marcus Queue playlist...", file=sys.stderr)
    try:
        response = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": PLAYLIST_TITLE,
                    "description": PLAYLIST_DESCRIPTION,
                },
                "status": {
                    "privacyStatus": "private",
                },
            },
        ).execute()
        playlist_id = response["id"]
        db.save_playlist_config(playlist_id)
        print(f"Playlist created: {playlist_id}", file=sys.stderr)
        return playlist_id
    except Exception as e:
        print(f"Error creating playlist: {e}", file=sys.stderr)
        raise


def add_to_playlist(youtube, playlist_id, video_id):
    """Add a video to the playlist. Returns the playlistItem ID."""
    try:
        response = youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                },
            },
        ).execute()
        item_id = response["id"]
        print(f"Added {video_id} to playlist (item: {item_id})", file=sys.stderr)
        return item_id
    except Exception as e:
        print(f"Error adding {video_id} to playlist: {e}", file=sys.stderr)
        return None


def remove_from_playlist(youtube, playlist_item_id):
    """Remove an item from the playlist by its playlistItem ID."""
    try:
        youtube.playlistItems().delete(id=playlist_item_id).execute()
        print(f"Removed playlist item: {playlist_item_id}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Error removing playlist item {playlist_item_id}: {e}", file=sys.stderr)
        return False


def list_playlist(youtube, playlist_id):
    """List all items currently in the playlist.

    Returns list of {video_id, title, playlist_item_id, position}.
    """
    items = []
    request = youtube.playlistItems().list(
        part="snippet",
        playlistId=playlist_id,
        maxResults=50,
    )

    while request is not None:
        try:
            response = request.execute()
        except Exception as e:
            print(f"Error listing playlist: {e}", file=sys.stderr)
            break

        for item in response.get("items", []):
            snippet = item["snippet"]
            items.append({
                "video_id": snippet["resourceId"]["videoId"],
                "title": snippet.get("title", ""),
                "playlist_item_id": item["id"],
                "position": snippet.get("position"),
            })

        request = youtube.playlistItems().list_next(request, response)

    return items


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Marcus playlist manager")
    parser.add_argument("--ensure", action="store_true",
                        help="Create playlist if needed, print ID")
    parser.add_argument("--add", metavar="VIDEO_ID",
                        help="Add a video to the playlist")
    parser.add_argument("--remove", metavar="PLAYLIST_ITEM_ID",
                        help="Remove an item from the playlist")
    parser.add_argument("--list", action="store_true",
                        help="List current playlist contents")
    args = parser.parse_args()

    youtube = get_youtube_service()

    if args.ensure:
        playlist_id = ensure_playlist(youtube)
        print(json.dumps({"playlist_id": playlist_id}, indent=2))

    elif args.add:
        playlist_id = ensure_playlist(youtube)
        item_id = add_to_playlist(youtube, playlist_id, args.add)
        print(json.dumps({
            "action": "add",
            "video_id": args.add,
            "playlist_item_id": item_id,
        }, indent=2))

    elif args.remove:
        ok = remove_from_playlist(youtube, args.remove)
        print(json.dumps({
            "action": "remove",
            "playlist_item_id": args.remove,
            "success": ok,
        }, indent=2))

    elif args.list:
        playlist_id = ensure_playlist(youtube)
        items = list_playlist(youtube, playlist_id)
        print(json.dumps(items, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
