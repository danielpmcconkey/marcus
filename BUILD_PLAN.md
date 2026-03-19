# Marcus — YouTube Curator Bot: Build Plan

> **Status:** Questions resolved. Ready for Phase 0.
> **Character:** Marcus Brody (Indiana Jones). Distinguished museum curator. Reverent
> about quality content, horrified by AI slop.
> **Last updated:** 2026-03-18

---

## Context

YouTube's subscription feed is broken. It was supposed to show new uploads from
channels Dan subscribes to, in chronological order. Instead it's an algorithmic
soup that flattens Dan's breadth of interests (homebrewing, rock collecting,
hiking, language learning, coding, cooking) into whatever YouTube thinks will
maximise watch time. Add the flood of AI-generated slop and copycat channels,
and the signal-to-noise ratio is unbearable.

Marcus solves this by being the curator YouTube refuses to be. He checks Dan's
subscriptions for new uploads, presents them cleanly, manages a viewing queue,
and — over time — learns what Dan actually wants to watch.

---

## Critical API Constraints

These are hard limitations of the YouTube Data API v3, not design choices.
They shape everything that follows.

### 1. Watch Later playlist is inaccessible via API

Since September 2016, the YouTube Data API returns hardcoded placeholder strings
(`WL`) for the Watch Later playlist. All operations — list, insert, delete —
fail with `playlistOperationUnsupported`. There is no workaround. This has been
an open issue on Google's tracker for 10 years with no indication of a fix.

**Implication:** Marcus manages a **custom playlist** (e.g., "Marcus Queue")
instead. Dan bookmarks it on Roku. Functionally equivalent — it shows up in
the YouTube app's Library section alongside Watch Later.

### 2. Watch History is inaccessible via API

Same deprecation wave. The `HL` playlist ID is non-functional.
`playlistItems.list` returns empty.

**Implication:** Marcus cannot detect what Dan has watched. All feedback flows
through **Discord** — Dan tells Marcus what he thought, or Marcus infers from
silence (decay).

### 3. Quota: 10,000 units/day

| Operation | Cost |
|-----------|------|
| Read (list endpoints) | 1 unit |
| Write (insert/update/delete) | 50 units |
| `search.list` | **100 units — never use this** |

Our estimated daily budget for Phase 1 is **~200-400 units** (mostly writes to
the playlist). Comfortable headroom.

### 4. RSS feeds are free

`https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID` returns the
15 most recent uploads. No API key, no OAuth, no quota cost. This is how Marcus
detects new uploads — the API is only used for metadata enrichment and playlist
management.

---

## Key Design Decisions

1. **Custom playlist, not Watch Later.** API constraint. Dan bookmarks it on Roku.
   Possibly multiple playlists later ("Marcus Queue", "Discovery").

2. **RSS for new upload detection, API for everything else.** RSS is free and
   sufficient for daily polling. Saves ~200 quota units/day vs. API polling.
   PubSubHubbub (push notifications) would be better but requires a publicly
   reachable callback server — not worth the infrastructure for Phase 1.

3. **Discord for all feedback.** Since watch history is unavailable, Dan tells
   Marcus what he watched/liked/skipped in Discord. Reactions for quick feedback,
   free text for nuanced taste signals.

4. **Agent-as-curator pattern.** Python scripts handle YouTube API calls, RSS
   parsing, and DB operations. Marcus (the Claude agent) makes curation decisions.
   No API calls from Python scripts to Claude — the agent IS Claude.

5. **PostgreSQL for state.** New `marcus` schema in the existing localhost
   Postgres instance. Same pattern as Thatcher.

6. **Tiered channel system for Phase 1.** Dan's subscriptions are bucketed into
   tiers. Tier 1 = always add to playlist. Tier 2 = show in digest, Dan picks.
   Tier 3 = ignore. Tiers evolve into the full taste model in Phase 2.

7. **Sonnet for Phase 1.** The work is mechanical — fetch, filter, post.
   Phase 2's taste model may warrant Opus. Revisit then.

---

## Phase 0: Infrastructure (Dan's Hands Required)

These steps require human credentials, web UI access, or admin privileges.

### 0.1 — Google Cloud / YouTube API Setup

**Decision:** Separate Google Cloud project (`openclaw-marcus`). Full isolation
from Zazu — revoking or disabling one project has zero impact on the other.
No hosting involved — Google Cloud Console is just where API credentials are managed.

Steps:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. **Create a new project** → name: `openclaw-marcus`
3. **APIs & Services → Library** → search "YouTube Data API v3" → **Enable**
4. **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name: `marcus-youtube`
5. Download the JSON credentials file → save as `/media/dan/fdrive/marcus/.client_secret.json` (mode 0600)
6. The first time the auth script runs, it will open a browser for OAuth consent.
   Dan authorizes with his YouTube/Google account. The refresh token is saved
   to `/media/dan/fdrive/marcus/.youtube_token.json` (mode 0600).

**OAuth scope required:** `https://www.googleapis.com/auth/youtube.force-ssl`
(covers both read and write; SSL-only variant is the minimum-privilege option
for playlist management).

**YouTube account:** `danielpmcconkey@gmail.com` (primary). Also has a second
channel "Aprendiendo Español" on the same account — future scope, not Phase 1.

### 0.2 — Discord Bot Creation

Follow the validated procedure from `discord-bot-private-problem.md`:

1. [Discord Developer Portal](https://discord.com/developers/applications) → **New Application** → name: `Marcus`
2. **IMMEDIATELY** → Installation → set Install Link to **None** → Save
3. Bot → toggle **Public Bot OFF**, **Message Content Intent ON** → Save
4. Bot → copy **Token** → save securely (needed for OpenClaw config)
5. OAuth2 → URL Generator → scopes: `bot` → permissions: Send Messages, Read Message History, View Channels
6. Copy generated URL → open in browser → invite to `dan-home` server
7. Create Discord channel **`#marcus_museum`**
8. Channel permissions: deny `@everyone` View Channel, allow Dan + Marcus bot

### 0.3 — PostgreSQL Setup

```sql
-- Create role
CREATE ROLE marcus WITH LOGIN PASSWORD '<password>';

-- Create schema
CREATE SCHEMA IF NOT EXISTS marcus AUTHORIZATION marcus;

-- Grant connect
GRANT CONNECT ON DATABASE openclaw TO marcus;

-- Marcus owns his schema, full control within it
-- No access to any other schema
```

**Decision:** New `openclaw` database. Per-agent schemas within it. Thatcher
stays in `householdbudget` for now — migration is a future task, not blocking.

Store credentials:
```bash
# /media/dan/fdrive/marcus/.pgpass (mode 0600)
localhost:5432:openclaw:marcus:<password>
```

### 0.4 — Credential File Permissions

```bash
chmod 600 /media/dan/fdrive/marcus/.client_secret.json
chmod 600 /media/dan/fdrive/marcus/.youtube_token.json  # after first auth
chmod 600 /media/dan/fdrive/marcus/.pgpass
```

---

## Phase 1: Subscription Watchdog

> **Goal:** Marcus checks Dan's YouTube subscriptions daily, posts a digest to
> Discord, and adds priority videos to a custom playlist. Dan controls which
> channels are auto-added vs. digest-only.

### 1.1 — Workspace Scaffolding

```
/media/dan/fdrive/marcus/
  workspace/
    SOUL.md
    IDENTITY.md
    USER.md
    AGENTS.md              (copy from Thatcher — standard boilerplate)
    TOOLS.md               (copy from Thatcher — standard boilerplate)
    HEARTBEAT.md
    .openclaw/
      workspace-state.json
    memory/
    skills/
      curate/
        SKILL.md
        scripts/
          .venv/
          auth.py           # OAuth token management
          subscriptions.py  # Fetch subscription list via API
          rss_check.py      # Check RSS feeds for new uploads
          metadata.py       # Enrich videos with API metadata
          playlist.py       # Manage custom playlist (add/remove/list)
          db.py             # All database operations
          digest.py         # Format the daily digest for Discord
          run_daily.py      # Orchestrator — the main entry point
  .client_secret.json       # OAuth client credentials (0600)
  .youtube_token.json       # OAuth refresh token (0600, created on first auth)
  .pgpass                   # PostgreSQL credentials (0600)
  BUILD_PLAN.md             # This file
```

### 1.2 — Database Schema (Phase 1)

```sql
-- All tables in the marcus schema

CREATE TABLE marcus.channel (
    channel_id      TEXT PRIMARY KEY,       -- YouTube channel ID (UC...)
    channel_name    TEXT NOT NULL,
    tier            SMALLINT NOT NULL DEFAULT 2,  -- 1=always, 2=digest, 3=ignore
    subscribed      BOOLEAN NOT NULL DEFAULT TRUE,
    last_upload_at  TIMESTAMPTZ,            -- most recent video we've seen
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE marcus.video (
    video_id        TEXT PRIMARY KEY,       -- YouTube video ID
    channel_id      TEXT NOT NULL REFERENCES marcus.channel(channel_id),
    title           TEXT NOT NULL,
    description     TEXT,                   -- first ~500 chars
    published_at    TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER,
    thumbnail_url   TEXT,
    status          TEXT NOT NULL DEFAULT 'new',
        -- new: just discovered
        -- queued: added to playlist
        -- presented: shown in digest, not queued
        -- watched: Dan confirmed watched
        -- skipped: Dan explicitly skipped
        -- expired: aged out (decay)
    playlist_item_id TEXT,                  -- YouTube's ID for the playlist entry (needed for removal)
    queued_at       TIMESTAMPTZ,
    expired_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE marcus.run_log (
    id              SERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    channels_checked INTEGER,
    new_videos      INTEGER,
    queued          INTEGER,
    digest_posted   BOOLEAN DEFAULT FALSE,
    notes           TEXT
);
```

### 1.3 — Python Scripts

**`auth.py`** — OAuth token management
- Load client secret from `/media/dan/fdrive/marcus/.client_secret.json`
- Load/refresh token from `/media/dan/fdrive/marcus/.youtube_token.json`
- On first run: launch browser-based OAuth flow, save refresh token
- Expose `get_youtube_service()` that returns an authenticated API client
- Uses `google-auth-oauthlib` and `google-api-python-client`

**`subscriptions.py`** — Fetch subscription list
- Call `subscriptions.list(mine=True)`, paginate through all results
- Return list of `{channel_id, channel_name}`
- Called infrequently (weekly sync, or on-demand) — not every daily run
- First run: bulk-insert all subscriptions into `marcus.channel` at tier 2
- Subsequent runs: detect new subs (insert at tier 2) and unsubs (set `subscribed=false`)

**`rss_check.py`** — Check for new uploads via RSS
- For each active channel (tier 1 or 2), fetch RSS feed
- Parse Atom XML for `<entry>` elements newer than `channel.last_upload_at`
- Return list of `{video_id, channel_id, title, published_at}`
- Update `channel.last_upload_at` to the newest video seen
- **Filter out Shorts** (duration < 60 seconds — detected after metadata enrichment)
- Zero API quota cost

**`metadata.py`** — Enrich with API metadata
- Take a list of video IDs, call `videos.list` in batches of 50
- Extract: title, description (truncated), duration, thumbnail URL
- Return enriched video dicts
- Cost: 1 unit per 50 videos — negligible

**`playlist.py`** — Custom playlist management
- `ensure_playlist()` — create "Marcus Queue" if it doesn't exist, return playlist ID
- `add_to_playlist(video_id)` — `playlistItems.insert`, return playlist_item_id (50 units)
- `remove_from_playlist(playlist_item_id)` — `playlistItems.delete` (50 units)
- `list_playlist()` — `playlistItems.list`, return current contents (1 unit)
- Playlist ID cached in DB or a small config file to avoid re-lookup

**`db.py`** — Database operations
- Connection via `.pgpass`, role `marcus`, database `openclaw`
- CRUD for channels, videos, run_log
- `get_tier1_channels()`, `get_active_channels()`, `upsert_videos()`, etc.
- Uses `psycopg2`

**`digest.py`** — Format daily digest
- Takes the day's new videos, groups by channel
- Formats a Discord-friendly message:
  - Tier 1 videos (auto-queued): listed with checkmark
  - Tier 2 videos (digest-only): listed with video link, Dan can say "queue that"
  - Summary stats (channels checked, new videos, queued count)
- Character voice: Marcus Brody flavour text
- Output: string ready for Discord `message` tool

**`run_daily.py`** — Main orchestrator
- Called by the agent (not directly by cron — the cron wakes Marcus, Marcus runs the script)
- Steps:
  1. Load active channels from DB
  2. Check RSS feeds for new uploads (`rss_check.py`)
  3. Deduplicate against existing `marcus.video` rows
  4. Enrich new videos with metadata (`metadata.py`)
  5. Insert new videos into DB (drop Shorts — duration < 60s)
  6. Auto-queue tier 1 videos to playlist (`playlist.py`)
  7. Run decay: expire videos older than N days that are still `queued` or `presented`
  8. Generate digest (`digest.py`)
  9. Log the run (`run_log`)
  10. Output digest JSON for the agent to post to Discord

### 1.4 — SOUL.md (Summary)

Marcus Brody. Museum curator. Reverent about quality, horrified by slop.
Distinguished but endearingly scattered — "I once got lost in my own museum."

Key operational instructions embedded in SOUL.md:
- You are a YouTube curator. Your job is to surface quality content.
- Python scripts handle the YouTube API. You make curation decisions.
- You do NOT call the YouTube API yourself. You run scripts.
- Your channel: `#marcus_museum`
- Absolute paths to all scripts
- How to handle Dan's interactive commands (tier changes, queue requests, feedback)

### 1.5 — SKILL.md: `curate`

Frontmatter:
```yaml
---
name: curate
description: Daily YouTube subscription scan and playlist curation
user-invocable: true
metadata:
  openclaw:
    emoji: "🏛️"
    requires:
      bins: ["python3"]
---
```

Processing flow:
1. Run `run_daily.py` → capture JSON output
2. Post digest to Discord with Brody-flavoured commentary
3. If Dan responds with commands ("queue that", "always add this channel",
   "ignore this channel"), execute the appropriate DB/playlist changes

Interactive commands Marcus responds to:
- "queue [video link or title reference]" → add to playlist
- "drop [video]" → remove from playlist
- "always add [channel]" → set tier 1
- "digest only [channel]" → set tier 2
- "ignore [channel]" → set tier 3
- "what's in the queue?" → list current playlist
- "sync subscriptions" → re-fetch subscription list from YouTube

### 1.6 — OpenClaw Registration & Cron

```bash
# Register agent
openclaw agents add marcus \
  --workspace /media/dan/fdrive/marcus/workspace \
  --model anthropic/claude-sonnet-4-6 \
  --non-interactive

# Wire up Discord (then edit openclaw.json for bindings + channel allowlist)
openclaw channels add --channel discord --account marcus --token "BOT_TOKEN"
```

Exec approvals (`~/.openclaw/exec-approvals.json`):
```json
{
  "marcus": {
    "allowlist": [
      { "pattern": "/media/dan/fdrive/marcus/workspace/skills/curate/scripts/run_daily.py" },
      { "pattern": "/media/dan/fdrive/marcus/workspace/skills/curate/scripts/subscriptions.py" },
      { "pattern": "/media/dan/fdrive/marcus/workspace/skills/curate/scripts/playlist.py" },
      { "pattern": "/media/dan/fdrive/marcus/workspace/skills/curate/scripts/auth.py" }
    ]
  }
}
```

**Schedule:** 02:00 ET daily. Digest is ready when Dan wakes up.

Cron job (added to `~/.openclaw/cron/jobs.json`):
```json
{
  "agentId": "marcus",
  "name": "marcus:curate",
  "enabled": true,
  "schedule": {
    "kind": "cron",
    "expr": "0 2 * * *",
    "tz": "America/New_York"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "kind": "agentTurn",
    "message": "/curate",
    "timeoutSeconds": 600
  },
  "delivery": {
    "mode": "announce",
    "channel": "last",
    "to": "<marcus_museum-channel-id>"
  }
}
```

### 1.7 — Phase 1 Deliverables Checklist

- [ ] OAuth flow working (auth.py)
- [ ] Subscription sync populates `marcus.channel`
- [ ] RSS check finds new uploads
- [ ] Metadata enrichment works (batched, ≤1 unit per 50 videos)
- [ ] Custom playlist created and manageable (add/remove)
- [ ] Tier system works (1=auto, 2=digest, 3=ignore)
- [ ] Daily digest posts to Discord with proper formatting
- [ ] Interactive commands work (queue, drop, tier changes)
- [ ] Decay removes stale queued videos
- [ ] Cron triggers daily run

---

## Phase 2: Taste & Decay

> **Goal:** Marcus learns Dan's preferences through explicit feedback and
> implicit signals. The tier system evolves into a proper taste model.
> Unwatched videos decay intelligently. The queue gets smarter over time.

### 2.1 — Feedback System

Dan provides feedback in Discord:
- **Reactions on digest items:** 👍 (liked), 👎 (not interested), ⭐ (loved)
- **Free text:** "Loved the editing on that one" / "This channel has gone downhill"
- **Implicit:** silence + decay = mild negative signal

New DB tables:

```sql
CREATE TABLE marcus.feedback (
    id              SERIAL PRIMARY KEY,
    video_id        TEXT NOT NULL REFERENCES marcus.video(video_id),
    rating          TEXT NOT NULL,           -- loved, liked, meh, disliked, skipped
    comment         TEXT,                    -- Dan's free-text "why"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE marcus.interest (
    id              SERIAL PRIMARY KEY,
    topic           TEXT NOT NULL UNIQUE,    -- e.g., "homebrewing", "woodworking"
    weight          REAL NOT NULL DEFAULT 0.5,  -- 0.0 to 1.0
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Add to channel table:
ALTER TABLE marcus.channel ADD COLUMN trust_score REAL DEFAULT 0.5;
ALTER TABLE marcus.channel ADD COLUMN notes TEXT;  -- Marcus's observations about the channel
```

### 2.2 — Taste Model

The taste model is **Marcus himself** — not a numeric algorithm, but Claude
reasoning about Dan's preferences based on accumulated feedback.

When Marcus curates (daily run or interactive request):
1. Scripts pull: new videos, Dan's feedback history, channel trust scores,
   topic interest weights, recent queue/watch patterns
2. This data is provided to Marcus as context
3. Marcus decides: queue, present in digest, or skip — and explains why in
   internal notes

The numeric scores (channel trust, topic weights) are **hints to Marcus**, not
a scoring algorithm. Marcus updates them based on his reasoning after
processing feedback. This keeps the model interpretable and allows Marcus to
consider nuances that pure numbers miss ("Dan likes woodworking videos but only
from channels that show real projects, not product reviews").

### 2.3 — Smart Decay

Phase 1 decay is simple: age out after N days. Phase 2 adds intelligence:

- Videos from tier 1 channels decay slower (5 days vs. 3)
- Videos Dan partially engaged with (opened digest link but didn't queue) get
  a softer decay signal than videos he never acknowledged
- Decay events feed back into the taste model: a tier 1 channel whose videos
  consistently expire may drift toward tier 2
- Marcus posts a weekly "expired this week" summary — not every video, just
  patterns ("You didn't watch any cooking videos this week — still interested
  in that topic?")

### 2.4 — Taste Feedback Scripts

**`feedback.py`** — Process feedback
- Record Dan's reaction/comment to `marcus.feedback`
- Recalculate channel trust score (simple running average of recent ratings)
- Update topic interest weights based on feedback patterns
- Output summary for Marcus to reason about

**`taste.py`** — Taste model data provider
- Compile Dan's preference profile from DB:
  - Topic interests with weights
  - Channel trust scores
  - Recent feedback history (last 30 days)
  - Decay patterns (which types of videos expire unwatched)
- Output as structured JSON for Marcus to use in curation decisions

### 2.5 — Phase 2 Deliverables Checklist

- [ ] Feedback capture via Discord reactions and free text
- [ ] Channel trust scores update based on feedback
- [ ] Topic interest weights tracked and updated
- [ ] Marcus uses taste data in curation decisions (not just tier rules)
- [ ] Smart decay with channel-tier-aware timing
- [ ] Weekly taste summary / expired video patterns
- [ ] Tier adjustments suggested by Marcus based on viewing patterns

---

## Phase 3: Discovery

> **Goal:** Marcus occasionally surfaces videos from channels Dan doesn't
> subscribe to. High confidence only. Sommelier, not firehose.

### 3.1 — Discovery Sources

Since `search.list` costs 100 units and is unreliable for taste-matching,
discovery uses indirect methods:

1. **Related channels.** YouTube's `channels.list` with
   `part=brandingSettings` doesn't expose related channels via API, but many
   channels link to others in their descriptions or "Channels" tab. Marcus
   can parse channel descriptions for channel links/mentions.

2. **Community recommendations.** Dan occasionally mentions channels or videos
   in Discord. Marcus remembers and checks them out.

3. **"More from this creator" expansion.** When Dan loves a video, Marcus
   checks if the creator has other content Dan hasn't seen.

4. **Curated seed lists.** Dan can give Marcus a list of channels to monitor
   without subscribing — a "watching with interest" tier.

5. **Topic-based RSS aggregation.** Specific subreddits or forums for Dan's
   interests often surface quality YouTube content. Marcus could parse these
   (similar to how Zazu handles RSS).

**Decision:** Deferred. Dan wants the taste model (Phase 2) to develop
organically through feedback before designing discovery sources. Revisit
after Phase 2 burn-in.

### 3.2 — Discovery DB Additions

```sql
CREATE TABLE marcus.discovery_source (
    id              SERIAL PRIMARY KEY,
    source_type     TEXT NOT NULL,   -- related_channel, community, expansion, seed_list, forum
    source_detail   TEXT,            -- e.g., subreddit name, referring channel
    video_id        TEXT REFERENCES marcus.video(video_id),
    channel_id      TEXT REFERENCES marcus.channel(channel_id),
    confidence      REAL,            -- Marcus's confidence this is a good recommendation
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.3 — Discovery Delivery

- Discovery videos go into a separate section of the digest: "Something new"
- Frequency: 1-3 per week, not daily. Quality over quantity.
- Each discovery includes Marcus's reasoning: why he thinks Dan would like it
- Option: separate playlist ("Marcus Discovers") so Dan can browse discovery
  picks on Roku without mixing them into the main queue

### 3.4 — Phase 3 Deliverables Checklist

- [ ] At least one discovery source implemented
- [ ] Discovery section in daily/weekly digest
- [ ] Confidence scoring for discovery recommendations
- [ ] Discovery feedback feeds back into taste model
- [ ] Optional separate discovery playlist

---

## Full DB Schema (All Phases)

| Table | Phase | Purpose |
|-------|-------|---------|
| `marcus.channel` | 1 | Subscribed channels, tier, trust score |
| `marcus.video` | 1 | Every video Marcus evaluates |
| `marcus.run_log` | 1 | Daily run tracking |
| `marcus.feedback` | 2 | Dan's explicit feedback |
| `marcus.interest` | 2 | Topic weights |
| `marcus.discovery_source` | 3 | How non-subscription videos were found |

---

## Directory Structure (Final)

```
/media/dan/fdrive/marcus/
  workspace/
    SOUL.md
    IDENTITY.md
    USER.md
    AGENTS.md
    TOOLS.md
    HEARTBEAT.md
    .openclaw/
      workspace-state.json
    memory/
    skills/
      curate/
        SKILL.md
        scripts/
          .venv/
          auth.py
          subscriptions.py
          rss_check.py
          metadata.py
          playlist.py
          db.py
          digest.py
          feedback.py        # Phase 2
          taste.py            # Phase 2
          discovery.py        # Phase 3
          run_daily.py
  .client_secret.json        # OAuth (0600)
  .youtube_token.json        # Refresh token (0600, created on first auth)
  .pgpass                    # PostgreSQL (0600)
  BUILD_PLAN.md              # This file
```

---

## Build Order

| Step | What | Phase | Who |
|------|------|-------|-----|
| 1 | Answer open questions (Q1-Q7) | 0 | Dan |
| 2 | Enable YouTube API, create OAuth client, download credentials | 0 | Dan |
| 3 | Create Discord bot (Private, Install Link = None) | 0 | Dan |
| 4 | Create Discord channel, set permissions | 0 | Dan |
| 5 | Create PostgreSQL database/schema/role | 0 | Dan (SQL from Hobson) |
| 6 | Workspace scaffolding (dirs, SOUL.md, IDENTITY.md, boilerplate) | 1 | Hobson |
| 7 | `auth.py` — OAuth flow + token refresh | 1 | Hobson |
| 8 | First OAuth authorization (browser flow) | 1 | Dan |
| 9 | `db.py` — database operations | 1 | Hobson |
| 10 | `subscriptions.py` — fetch + sync subscription list | 1 | Hobson |
| 11 | Initial subscription sync — populate `marcus.channel` | 1 | Hobson + Dan (verify) |
| 12 | Dan sets initial channel tiers (at least a few tier 1s) | 1 | Dan |
| 13 | `rss_check.py` — RSS feed polling | 1 | Hobson |
| 14 | `metadata.py` — video metadata enrichment | 1 | Hobson |
| 15 | `playlist.py` — custom playlist CRUD | 1 | Hobson |
| 16 | `digest.py` — Discord digest formatter | 1 | Hobson |
| 17 | `run_daily.py` — orchestrator | 1 | Hobson |
| 18 | SKILL.md — full skill definition | 1 | Hobson |
| 19 | OpenClaw registration + Discord wiring | 1 | Hobson + Dan (token) |
| 20 | Exec approvals | 1 | Hobson |
| 21 | End-to-end test (manual trigger, verify digest + playlist) | 1 | Both |
| 22 | Cron setup | 1 | Hobson |
| 23 | Burn-in period (1-2 weeks of daily use) | 1 | Dan |
| 24 | `feedback.py` + taste tables | 2 | Hobson |
| 25 | `taste.py` + SKILL.md updates for taste-aware curation | 2 | Hobson |
| 26 | Smart decay logic | 2 | Hobson |
| 27 | Phase 2 burn-in | 2 | Dan |
| 28 | Discovery source(s) per Q6 decision | 3 | Hobson |
| 29 | Discovery integration + separate playlist (optional) | 3 | Hobson |

---

## Not in MVP (Phase 1)

- Taste model (Phase 2)
- Discovery (Phase 3)
- Video transcript analysis (checking actual video content for quality)
- Multiple playlist support
- ~~Shorts filtering~~ — moved to Phase 1. Shorts are dead to us.
- Cross-agent integration (Radar weekly rollup)
- XR glasses optimisation
- Channel "probation" (auto-demote after N ignored videos)

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| **YouTube API quota exceeded** | Low | RSS handles the heavy lifting. Daily budget est. ~200-400 units out of 10,000. |
| **OAuth token expiry** | Medium | Refresh tokens are long-lived, but Google can revoke if the app is in "Testing" mode and the consent screen expires after 7 days. Plan: start in test mode, publish after validating. |
| **RSS feed format changes** | Low | YouTube RSS has been stable for years. If it breaks, fall back to API polling (costs ~200 more units/day, still fine). |
| **Custom playlist not discoverable on Roku** | Low | Custom playlists appear in Library → Playlists on all YouTube clients. Dan may need to scroll past Watch Later. Verify on first setup. |
| **Dan has too many subscriptions for RSS polling** | Medium | 200 channels × 1 HTTP request each = 200 requests. At ~0.5s each (sequential), that's ~100 seconds. Parallelise with asyncio/aiohttp to bring it under 20s. |
| **Sonnet doesn't follow curation instructions well** | Medium | Lesson from Thatcher: Sonnet can be stubborn. Put critical instructions in SOUL.md. If persistent issues, upgrade to Opus (costs more tokens per run). |

---

## Questions — Resolved (2026-03-18)

All questions answered. Decisions locked in above.

| # | Question | Answer |
|---|----------|--------|
| Q1 | Google Cloud project | **Separate project** (`openclaw-marcus`). Full isolation from Zazu. |
| Q2 | YouTube account | `danielpmcconkey@gmail.com`. Second channel "Aprendiendo Español" on same account — future scope. |
| Q3 | Discord channel | `#marcus_museum` |
| Q4 | Database | New `openclaw` DB with `marcus` schema |
| Q5 | Cron time | 02:00 ET (overnight, digest ready at wake-up) |
| Q6 | Discovery sources | Deferred to post-Phase 2 burn-in. Taste model learns organically first. |
| Q7 | Shorts | Filtered out in Phase 1. No Shorts, ever. |
| Q8 | OAuth app status | Test mode first, publish after validating. |

---

## Python Dependencies (Phase 1)

```
google-api-python-client    # YouTube Data API client
google-auth-oauthlib        # OAuth 2.0 flow
google-auth-httplib2        # HTTP transport for auth
psycopg2-binary             # PostgreSQL
feedparser                  # RSS/Atom parsing (alternative: raw XML with ElementTree)
```

All pip-installable. No system packages needed beyond `python3`.
