# InventoryAlerts

Real-time inventory monitor and Slack bot for InSitu balloon/stent parts.

- Polls the MS Access database (`Insitu Program MASTER.mdb`) every 60 seconds
- Sends a Slack alert when any monitored part drops **at or below** its configured threshold
- Responds to `inventory`, `thresholds`, and `help` commands in Slack
- Posts a **full inventory report every Monday at 9:00 AM CST**

> This folder is completely self-contained and independent of QBApp.

---

## Prerequisites

### 1. Python (64-bit or 32-bit — must match your Access driver)

Download from https://www.python.org/downloads/

> **Important — Access driver bitness:**  
> The QBApp uses the 32-bit Jet driver (`Microsoft.Jet.OLEDB.4.0`).  
> If you install **64-bit Python**, you also need the **64-bit** Microsoft Access Database Engine (ACE):  
> https://www.microsoft.com/en-us/download/details.aspx?id=54920  
> Choose `AccessDatabaseEngine_X64.exe`.  
>
> Alternatively, install **32-bit Python** — it will use the existing 32-bit Jet/ACE driver that QBApp already relies on.

### 2. Slack App setup

1. Go to https://api.slack.com/apps → **Create New App** → "From scratch"
2. **Enable Socket Mode** (Settings → Socket Mode → Enable)
   - Generate an **App-Level Token** with scope `connections:write` → copy it (starts with `xapp-`)
3. Under **OAuth & Permissions → Bot Token Scopes**, add:
   - `chat:write`
   - `channels:history`
   - `groups:history`
   - `im:history`
   - `mpim:history`
4. Under **Event Subscriptions → Subscribe to bot events**, add:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`
5. **Install the app** to your workspace → copy the **Bot User OAuth Token** (starts with `xoxb-`)
6. Invite the bot to the alert channel: `/invite @YourBotName`
7. Copy the channel ID (right-click channel in Slack → "Copy link", it ends with the ID like `C0123456789`)

---

## Installation

```powershell
cd InventoryAlerts

# Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

---

## Configuration

```powershell
copy .env.example .env
notepad .env
```

Fill in the four required values:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_ALERT_CHANNEL=C0123456789
ACCESS_DB_PATH=\\INSITU-SERV2022\NetServ_2\Manufacturing-Operations\DATABASE\Insitu Program MASTER.mdb
```

---

## Thresholds

Edit `thresholds.json` to set alert levels. No restart needed — thresholds are
re-read on every poll cycle.

```json
{
    "prefix_thresholds": {
        "19T":  10,
        "18":   10
    },
    "part_thresholds": {
        "19T2510": 15,
        "18M10":   12
    }
}
```

- **`prefix_thresholds`** — applies to all parts whose name starts with that prefix
- **`part_thresholds`** — exact overrides for a specific part number (takes priority)

---

## Running

```powershell
cd InventoryAlerts
.venv\Scripts\Activate.ps1
python main.py
```

Log output goes to both the console and `inventory_alerts.log`.

To run it silently in the background (no console window):

```powershell
Start-Process pythonw -ArgumentList "main.py" -WorkingDirectory "C:\path\to\InventoryAlerts"
```

Or set it up as a Windows Service / Task Scheduler task to auto-start with the machine.

---

## Slack Commands

Send any of these as a plain message in a channel where the bot is present,
or as a direct message to the bot:

| Message | Response |
|---------|----------|
| `inventory` | Full table of all monitored parts and on-hand quantities |
| `inventory 19T` | Filtered to parts starting with `19T` |
| `inventory 18M10` | Filtered to parts starting with `18M10` |
| `thresholds` | Shows the current alert thresholds |
| `help` | Shows available commands |

---

## How inventory is calculated

Mirrors the formula in `DHR.aspx.cs updateQty_Click` exactly:

```
on_hand = SUM(tblReceiving.QuantityReceived  WHERE PartNumber = <id>)
        - SUM(tblLotTracking.QuantityConverted
                JOIN tblLots ON tblLots.LotIssue = tblLotTracking.LotIssue
              WHERE tblLotTracking.PartNumber = <id>)
```

Parts monitored are those in `tblSupplies` whose `PartNumber` starts with:
`19T`, `19S`, `19N`, `22PM`, `22C`, `18`, `17` (excluding `*MM`), `15H`, `14C`

---

## File structure

```
InventoryAlerts/
├── main.py            Entry point — starts all three components
├── config.py          Loads .env and thresholds.json
├── db.py              Access database reader, inventory formula
├── monitor.py         Polling loop, threshold comparison, alert trigger
├── scheduler.py       APScheduler — Monday 9 AM CST weekly report
├── bot.py             Slack Socket Mode bot, message handlers
├── slack_client.py    Slack WebClient wrapper, message formatting
├── thresholds.json    Alert threshold configuration (edit freely at runtime)
├── requirements.txt
├── .env.example       Template — copy to .env and fill in secrets
└── README.md
```
