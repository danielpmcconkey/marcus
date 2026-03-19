# Configuration

Marcus has no config files in the traditional sense. Configuration is split across the `pass` store (secrets), OpenClaw config (agent registration), and the database (runtime state).

## Secrets (`pass` store)

All secrets are GPG-encrypted in the `pass` password store under the `openclaw/` prefix. The GPG key is `OpenClaw Automation <openclaw@localhost>` — passphrase-less, for unattended cron operation.

| Pass path | Contents | Used by |
|-----------|----------|---------|
| `openclaw/marcus/pgpass` | `host:port:dbname:user:password` | `db.py` |
| `openclaw/marcus/client-secret` | Google OAuth client credentials (JSON) | `auth.py` |
| `openclaw/marcus/youtube-token` | OAuth refresh token (JSON, updated on refresh) | `auth.py` |

Scripts read secrets via `subprocess.check_output(["pass", "show", ...])`. The `auth.py` script writes refreshed tokens back via `pass insert`.

## OpenClaw Agent Registration

Marcus is registered as an OpenClaw agent:

- **Agent ID:** `marcus`
- **Workspace:** `/media/dan/fdrive/codeprojects/marcus/workspace`
- **Model:** `anthropic/claude-sonnet-4-6`
- **Discord channel:** `#marcus_museum` (channel ID: `1483924993145438420`)

## Cron Job

Defined in `~/.openclaw/cron/jobs.json`:

```json
{
  "agentId": "marcus",
  "name": "marcus:curate",
  "enabled": true,
  "schedule": {
    "kind": "cron",
    "expr": "0 17 * * *",
    "tz": "America/New_York"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "kind": "agentTurn",
    "message": "/curate",
    "timeoutSeconds": 900
  },
  "delivery": {
    "mode": "announce",
    "channel": "last",
    "to": "1483924993145438420"
  }
}
```

**Schedule:** 17:00 ET daily. Playlist ready for evening viewing.

**Timeout:** 900 seconds (15 minutes). The pipeline involves RSS polling (~20s), metadata enrichment, agent news curation, and playlist rebuild (~60-80 API calls).

**Trigger:** OpenClaw wakes Marcus in an isolated session, sends `/curate`, Marcus executes the skill.

## Exec Approvals

Defined in `~/.openclaw/exec-approvals.json` under `agents.marcus.allowlist`:

```json
[
  {"pattern": ".../scripts/run_daily.py"},
  {"pattern": ".../scripts/build_playlist.py"},
  {"pattern": ".../scripts/subscriptions.py"},
  {"pattern": ".../scripts/playlist.py"},
  {"pattern": ".../scripts/auth.py"}
]
```

These are the scripts Marcus is permitted to execute. All other script execution requires manual approval.

## Database Configuration

Runtime configuration is stored in `marcus.config` (key-value table). Currently one entry:

| Key | Value | Purpose |
|-----|-------|---------|
| `playlist_id` | YouTube playlist ID | Cached to avoid re-lookup each run |

## Python Virtual Environment

All dependencies are installed in a venv at:
`/media/dan/fdrive/codeprojects/marcus/workspace/skills/curate/scripts/.venv/`

Dependencies:
```
google-api-python-client    # YouTube Data API v3
google-auth-oauthlib        # OAuth 2.0 flow
google-auth-httplib2        # HTTP transport
psycopg2-binary             # PostgreSQL
```

No system packages needed beyond `python3`.
