# digest.py

`workspace/skills/curate/scripts/digest.py`

Formats the evening programme digest for Discord. Takes curated news block and subscription picks, produces a Marcus Brody-flavoured summary.

## Functions

| Function | Description |
|----------|-------------|
| `format_digest(news_block, subscription_block, stats)` | Returns a formatted string ready for Discord posting. |

## Output Format

```
**Tonight's Programme**

Your evening viewing is prepared. ~4h 12m of curated content.

**News Block** (~25m)
  Fed signals rate pause — *Reuters* (3:15)
  UK election results — *BBC News* (4:32)

**Must Watch** (5 videos, ~1h 30m)
  Why LED bulbs flicker — *Technology Connections* (22:14)
  The science of bread crust — *Adam Ragusea* (18:45)

**Priority** (8 videos, ~2h 15m)
  Ratatouille from Ratatouille — *Binging with Babish* (24:12)
  ...

**Also Playing** (3 videos, ~45m)
  ...

---
*200 channels | 15 new | 28 queued | ~4h 12m*
```

## Tier Labels

| Tier | Label in digest |
|------|----------------|
| 0 | "News Block" |
| 1 | "Must Watch" |
| 2 | "Priority" |
| 3 | "Also Playing" |

## Duration Formatting

- Per-video: `M:SS` or `H:MM:SS`
- Totals: `4h 12m` or `25m`

## Empty Programme

If no videos are selected, the opening line reads: "A rather bare evening, I'm afraid. The galleries are empty."

## CLI

```bash
echo '{"news_block": [...], "subscription_block": [...], "stats": {...}}' | python3 digest.py
```
