# YouTube API

YouTube Data API v3. OAuth 2.0 with scope `youtube.force-ssl`. GCP project: `openclaw-marcus`.

## Hard Constraints

These are API limitations, not design choices.

### Watch Later playlist is inaccessible

Since September 2016, the YouTube Data API returns hardcoded placeholder strings (`WL`) for the Watch Later playlist. All operations fail with `playlistOperationUnsupported`. 10-year-old open issue, no fix.

**Implication:** Marcus manages a custom playlist ("Marcus Queue") instead. Dan bookmarks it on Roku.

### Watch History is inaccessible

Same deprecation wave. The `HL` playlist ID is non-functional. `playlistItems.list` returns empty.

**Implication:** Marcus cannot detect what Dan has watched. Feedback must come through Discord (Phase 2). Until then, videos may repeat across daily programmes.

### Quota: 10,000 units/day

Per GCP project, per day (Pacific Time reset).

| Operation | Cost | Used by |
|-----------|------|---------|
| `videos.list` (metadata) | 1 unit per call (up to 50 IDs) | `metadata.py` |
| `playlists.list` / `playlistItems.list` | 1 unit per page | `playlist.py` |
| `playlists.insert` | 50 units | `playlist.py` (one-time) |
| `playlistItems.insert` | 50 units | `build_playlist.py` |
| `playlistItems.delete` | 50 units | `build_playlist.py` |
| `subscriptions.list` | 1 unit per page | `subscriptions.py` |
| `search.list` | **100 units — never use** | Nothing |

### Daily quota budget (estimated)

| Phase | Operation | Units |
|-------|-----------|-------|
| Gather | Metadata enrichment (~5 batches) | ~5 |
| Build | Clear playlist (~30 items) | ~1,500 |
| Build | Insert playlist (~30 items) | ~1,500 |
| Build | Playlist list (1 page) | ~1 |
| Build | Playlist ensure (1 check) | ~1 |
| **Total** | | **~3,000** |

Comfortable headroom against the 10,000 limit. Subscription sync (weekly) adds ~4 units.

## RSS Feeds

YouTube channel RSS feeds are free — no API key, no OAuth, no quota.

URL pattern: `https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}`

Returns Atom XML with the 15 most recent uploads. This is how Marcus detects new uploads. The API is only used for metadata enrichment and playlist management.

RSS feeds have been stable for years. If they break, fallback to API polling would cost ~200 additional units/day (still fine).

## OAuth

**Scope:** `https://www.googleapis.com/auth/youtube.force-ssl` — read and write, SSL-only variant. Minimum privilege for playlist management.

**Token storage:** `pass` store at `openclaw/marcus/youtube-token` (JSON). Refreshed automatically by `auth.py`. Updated token written back to `pass` store.

**Client credentials:** `pass` store at `openclaw/marcus/client-secret` (JSON).

**GCP app status:** Currently in **test mode**. Tokens may expire every 7 days. Publishing the app (internal use) is an outstanding item to make tokens long-lived.

**YouTube account:** `danielpmcconkey@gmail.com` (primary).

## Playlist Details

**Name:** "Marcus Queue"

**Privacy:** Private (only Dan and Marcus bot can see it).

**ID caching:** The playlist ID is cached in `marcus.config` (key: `playlist_id`). `ensure_playlist()` verifies the cached ID is still valid before using it.

**Ordering:** `playlistItems.insert` adds items to the end of the playlist by default. Since the playlist is cleared before rebuild, insertion order matches programme order. News block first, subscriptions after.
