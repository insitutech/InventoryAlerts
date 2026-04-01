# InventoryAlerts

A lightweight Python script that watches a parts inventory database and sends real-time alerts to Slack when stock drops below defined thresholds.

---

> **Disclaimer:** This project is intended for **demonstration purposes only**. It is a vertical script built around internal company infrastructure (a proprietary MS Access database, internal network paths, and a company Slack workspace) and will not run outside of that environment as-is.

---

## What it does

- Polls an inventory database every 60 seconds and sends a Slack alert when any monitored part drops at or below its threshold
- Recovers gracefully — once a part is back above threshold, it sends a recovery notice and stops spamming
- Posts a **weekly low-inventory report every Monday at 9 AM**
- Responds to commands directly in Slack (no dashboard needed)

## Slack commands

| Command | What you get |
|---|---|
| `full inventory` | All monitored parts and their current quantities |
| `low inventory` | Only the parts currently below threshold |
| `<PART> qty` | Quantity for a specific part or prefix (e.g. `15H23 qty`) |
| `report` | Bar chart of products created in the last 30 days |
| `report march` | Bar chart for a specific month |
| `thresholds` | Shows the configured alert thresholds |
| `help` | Shows all commands |

## Thresholds

Thresholds live in `thresholds.json` and are re-read on every poll — no restart needed when you tweak them.

```json
{
    "prefix_thresholds": {
        "19T": 10
    },
    "part_thresholds": {
        "19T2510": 15
    }
}
```

`prefix_thresholds` matches any part that starts with that string. `part_thresholds` are exact overrides that take priority.

## File overview

```
InventoryAlerts/
├── main.py          Entry point — spins up all three components
├── config.py        Env vars and threshold loading
├── db.py            Database queries and inventory formula
├── monitor.py       Poll loop + alert logic
├── scheduler.py     Weekly Monday report
├── bot.py           Slack bot and message handlers
├── slack_client.py  Message formatting and Slack API wrapper
└── thresholds.json  Edit this to change alert levels
```
