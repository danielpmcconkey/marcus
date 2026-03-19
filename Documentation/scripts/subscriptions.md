# subscriptions.py

`workspace/skills/curate/scripts/subscriptions.py`

Fetches Dan's YouTube subscription list and syncs it to the database. New subscriptions are inserted at tier 2 (priority). Channels Dan has unsubscribed from are marked `subscribed=FALSE`.

## Functions

| Function | Description |
|----------|-------------|
| `fetch_subscriptions(youtube)` | Calls `subscriptions.list(mine=True)`, paginates through all results. Returns list of `{channel_id, channel_name}`. |
| `sync_subscriptions(subs)` | Upserts channels to DB and marks unsubscribed. Returns summary dict. |

## Sync Behaviour

- **New subscription:** Inserted into `marcus.channel` at tier 2, `subscribed=TRUE`.
- **Existing subscription:** Name updated, `subscribed` set to TRUE (handles re-subscribes).
- **Unsubscribed:** Channels in DB that are NOT in the fetched list get `subscribed=FALSE`. **Tier 0 channels are excluded** — the `mark_unsubscribed()` query has `AND tier != 0` to protect manually added news channels.

## Usage Frequency

Use sparingly. Dan's subscription list changes slowly. Weekly or on-demand is sufficient. The daily `run_daily.py` does NOT sync subscriptions unless `--sync-subs` is passed.

API cost: 1 unit per page of 50 subscriptions. ~4 pages for 188 subscriptions = 4 units.

## CLI

```bash
python3 subscriptions.py              # Fetch + sync to DB, print summary
python3 subscriptions.py --fetch-only # Fetch + print JSON, don't touch DB
```

Sync output:
```json
{
  "total_subscriptions": 188,
  "new_channels": 2,
  "updated_channels": 186,
  "unsubscribed": 0
}
```
