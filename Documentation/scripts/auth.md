# auth.py

`workspace/skills/curate/scripts/auth.py`

OAuth 2.0 token management for YouTube Data API v3. Handles first-run browser flow, token refresh, and credential storage in the `pass` store.

## Functions

| Function | Description |
|----------|-------------|
| `get_youtube_service(force_init=False)` | Returns an authenticated `googleapiclient` service object. This is the entry point every YouTube-facing script uses. |
| `get_credentials(force_init=False)` | Returns valid `Credentials`. Loads from `pass` store, refreshes if expired, or runs browser flow if no token exists. |

## Token Lifecycle

1. **First run:** No token in `pass` store. `get_credentials()` launches a local HTTP server and opens the browser for OAuth consent. Dan authorizes. Refresh token saved to `pass`.
2. **Normal run:** Token loaded from `pass`. If expired, refreshed via `creds.refresh(Request())`. Updated token saved back to `pass`.
3. **Invalid token:** If the token can't be refreshed (revoked, corrupted), falls back to the browser flow.
4. **Force init:** `python3 auth.py --init` forces a fresh browser flow regardless of existing token state.

## Secret Storage

| Pass path | Contents |
|-----------|----------|
| `openclaw/marcus/client-secret` | Google OAuth client credentials JSON (from GCP console) |
| `openclaw/marcus/youtube-token` | Refresh token JSON (written/updated by auth.py) |

The client secret JSON is downloaded once from Google Cloud Console. The token JSON is managed entirely by `auth.py`.

## GCP Test Mode Warning

The GCP project `openclaw-marcus` is currently in **test mode**. OAuth tokens may expire every 7 days. If Marcus starts failing auth, the likely fix is either:
- Re-run `python3 auth.py --init` (manual, requires browser)
- Publish the GCP app for internal use (permanent fix)

## CLI

```bash
python3 auth.py          # Check token status, refresh if needed
python3 auth.py --init   # Force fresh OAuth flow (opens browser)
```

Output:
```json
{
  "valid": true,
  "expired": false,
  "has_refresh_token": true,
  "token_store": "openclaw/marcus/youtube-token"
}
```
