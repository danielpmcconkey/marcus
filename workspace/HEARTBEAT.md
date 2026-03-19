# HEARTBEAT.md

## Checks

- [ ] **YouTube OAuth token** — Is `/media/dan/fdrive/codeprojects/marcus/.youtube_token.json` present and not expired? If the token refresh fails, flag it immediately — nothing works without auth.
- [ ] **Last successful run** — When did `run_daily.py` last complete? Check `marcus.run_log` for the most recent entry. If it's been more than 36 hours, something may be wrong.
- [ ] **Stale RSS channels** — Any active (tier 1 or 2) channels where `last_upload_at` is older than 30 days? They may have gone dormant or the RSS feed URL may have changed.
- [ ] **Playlist accessible** — Can `playlist.py --list` run without errors? If the playlist was deleted or permissions changed, flag it.
- [ ] **Database connection** — Can we connect to the `openclaw` database as role `marcus`? If `.pgpass` is missing or the role is broken, flag it.

## Notes

Keep this file small. Add temporary reminders below as needed, remove them when resolved.
