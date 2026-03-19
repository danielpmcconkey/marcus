# playlist.py

`workspace/skills/curate/scripts/playlist.py`

YouTube playlist CRUD for the "Marcus Queue" custom playlist. Low-level operations — create, add, remove, list. Used by `build_playlist.py` for daily rebuilds and by the agent for interactive commands.

## Functions

| Function | API cost | Description |
|----------|---------|-------------|
| `ensure_playlist(youtube)` | 1-2 units | Returns playlist ID. Checks DB cache → verifies with API → searches existing playlists → creates if needed. Caches ID in `marcus.config`. |
| `add_to_playlist(youtube, playlist_id, video_id)` | 50 units | Adds a video. Returns the `playlist_item_id` (needed for removal), or None on failure. |
| `remove_from_playlist(youtube, playlist_item_id)` | 50 units | Removes an item by its playlist item ID. Returns True/False. |
| `list_playlist(youtube, playlist_id)` | 1 unit/page | Lists all items. Paginates automatically. Returns list of `{video_id, title, playlist_item_id, position}`. |

## Playlist Details

- **Name:** "Marcus Queue"
- **Description:** "Curated by Marcus — your YouTube subscription watchdog."
- **Privacy:** Private
- **ID:** Cached in `marcus.config` table (key: `playlist_id`)

## CLI

```bash
python3 playlist.py --ensure           # Create if needed, print ID
python3 playlist.py --add VIDEO_ID     # Add video, print result
python3 playlist.py --remove ITEM_ID   # Remove item, print result
python3 playlist.py --list             # List all items, print JSON
```

## Why a Custom Playlist?

YouTube's Watch Later playlist (`WL`) has been inaccessible via API since September 2016. All operations return `playlistOperationUnsupported`. Marcus uses a custom private playlist instead. Dan bookmarks it on Roku — it shows up in Library → Playlists.
