"""
Slack bot — Socket Mode (no public URL required).

Commands (type in any channel the bot is in, or DM the bot):

  full inventory         → all monitored parts and quantities
  low inventory          → only parts currently below threshold
  <PART> qty             → quantity of a specific part or prefix
                           e.g.  "15H23 qty"  or  "19T qty"
  thresholds             → show configured alert thresholds
  help                   → show this command list

Bot responses are instant — inventory is served from an in-memory cache that
the monitor thread refreshes every POLL_INTERVAL seconds.
"""

import logging
import calendar
import pytz
from datetime import datetime, date, timedelta
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import cache
from config import Config
from db import get_all_inventory, get_production_report
from slack_client import send_full_inventory_report, send_low_parts_report, send_production_report

logger = logging.getLogger(__name__)

app = App(token=Config.SLACK_BOT_TOKEN)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _channel_id(message: dict) -> str:
    return message.get("channel", Config.SLACK_ALERT_CHANNEL)


def _age_str(last_updated: datetime | None) -> str:
    """Human-readable 'updated X seconds ago' string."""
    if last_updated is None:
        return "not yet updated"
    tz = pytz.timezone(Config.REPORT_TIMEZONE)
    now_str = datetime.now(tz).strftime("%I:%M %p %Z")
    seconds = int((datetime.now() - last_updated).total_seconds())
    if seconds < 60:
        return f"as of {now_str} ({seconds}s ago)"
    return f"as of {now_str} ({seconds // 60}m ago)"


def _get_cached_or_fetch(say) -> tuple[dict | None, dict | None]:
    """
    Return (inventory, thresholds) from cache if ready.
    On cold start (first 60s), falls back to a live DB query with a notice.
    """
    thresholds = Config.load_thresholds()

    if cache.is_ready():
        inventory, _ = cache.get()
        return inventory, thresholds

    # Cache not populated yet — first poll hasn't finished
    say("_One moment, loading inventory for the first time..._")
    try:
        inventory = get_all_inventory()
        cache.update(inventory)
        return inventory, thresholds
    except ConnectionError as e:
        say(f":x: *Database unreachable.*\n```{e}```")
        return None, None
    except Exception as e:
        say(f":x: *Error reading inventory.*\n```{e}```")
        return None, None


# ── full inventory ─────────────────────────────────────────────────────────────

@app.message(r"(?i)^full inventory")
def handle_full_inventory(message, say):
    inventory, thresholds = _get_cached_or_fetch(say)
    if inventory is None:
        return
    _, last_updated = cache.get()
    send_full_inventory_report(
        inventory, thresholds,
        channel=_channel_id(message),
        title=f"Full Inventory — {_age_str(last_updated)}",
    )


# ── low inventory ──────────────────────────────────────────────────────────────

@app.message(r"(?i)^low inventory")
def handle_low_inventory(message, say):
    inventory, thresholds = _get_cached_or_fetch(say)
    if inventory is None:
        return
    _, last_updated = cache.get()
    send_low_parts_report(
        inventory, thresholds,
        channel=_channel_id(message),
    )


# ── <PART> qty ─────────────────────────────────────────────────────────────────

@app.message(r"(?i)^(\S+)\s+qty$")
def handle_part_qty(message, say):
    text: str = message.get("text", "").strip()
    query = text.rsplit(" ", 1)[0].strip().upper()

    inventory, thresholds = _get_cached_or_fetch(say)
    if inventory is None:
        return

    matches = {k: v for k, v in inventory.items() if k.upper().startswith(query)}

    if not matches:
        say(f":mag: No monitored parts found matching `{query}`.")
        return

    lines = []
    for part in sorted(matches):
        lines.append(f"*{part}* - {matches[part]}")

    _, last_updated = cache.get()
    lines.append(f"_{_age_str(last_updated)}_")
    say("\n".join(lines))


# ── report ────────────────────────────────────────────────────────────────────

_MONTH_NAMES = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTH_ABBR  = {name.lower(): i for i, name in enumerate(calendar.month_abbr)  if name}

def _parse_report_range(text: str) -> tuple[date, date, str] | None:
    """
    Parse the date range from a 'report ...' command.
    Supported formats:
      report                → last 30 days
      report march          → March of current year (or previous if in future)
      report march 2025     → March 2025
      report 2025-03        → March 2025

    Returns (start, end_exclusive, label) or None on parse failure.
    """
    parts = text.strip().split()
    today = date.today()

    # "report" with nothing after → last 30 days
    if len(parts) == 0:
        start = today - timedelta(days=30)
        label = f"Last 30 Days (since {start.strftime('%b %d, %Y')})"
        return start, today + timedelta(days=1), label

    # "report 2025-03"
    if len(parts) == 1 and "-" in parts[0]:
        try:
            yr, mo = parts[0].split("-")
            year, month = int(yr), int(mo)
        except ValueError:
            return None
    else:
        # "report march" or "report march 2025" or "report mar 2025"
        token = parts[0].lower()
        month = _MONTH_NAMES.get(token) or _MONTH_ABBR.get(token)
        if not month:
            return None
        year = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else today.year
        # If requested month is in the future this year, use previous year
        if year == today.year and month > today.month:
            year -= 1

    if not (1 <= month <= 12):
        return None

    _, last_day = calendar.monthrange(year, month)
    start = date(year, month, 1)
    end   = date(year, month, last_day) + timedelta(days=1)
    label = f"{calendar.month_name[month]} {year}"
    return start, end, label


@app.message(r"(?i)^report\b")
def handle_report(message, say):
    text: str = message.get("text", "").strip()
    # Strip the leading "report" keyword
    args = text[len("report"):].strip()

    parsed = _parse_report_range(args)
    if parsed is None:
        say(
            ":x: Couldn't parse that date. Try:\n"
            "```\n"
            "  report                 Last 30 days\n"
            "  report march           March this year\n"
            "  report march 2025      March 2025\n"
            "  report 2025-03         March 2025\n"
            "```"
        )
        return

    start, end, label = parsed
    say(f"_Pulling production data for {label}..._")

    try:
        data = get_production_report(start, end)
    except ConnectionError as e:
        say(f":x: *Database unreachable.*\n```{e}```")
        return
    except Exception as e:
        say(f":x: *Error reading production data.*\n```{e}```")
        return

    send_production_report(
        data,
        title=f"Products Created — {label}",
        channel=_channel_id(message),
    )


# ── thresholds ─────────────────────────────────────────────────────────────────

@app.message(r"(?i)^thresholds?\b")
def handle_thresholds(message, say):
    try:
        thresholds = Config.load_thresholds()
    except Exception as e:
        say(f":x: Could not load thresholds.json\n```{e}```")
        return

    prefix_thresh: dict = thresholds.get("prefix_thresholds", {})
    part_thresh: dict = thresholds.get("part_thresholds", {})

    lines = ["*Configured Thresholds*", "", "```"]
    for pfx, val in sorted(prefix_thresh.items()):
        lines.append(f"  {pfx + '*':<24} {val}")
    if part_thresh:
        lines.append("")
        for part, val in sorted(part_thresh.items()):
            lines.append(f"  {part:<24} {val}  (exact override)")
    lines.append("```")

    say("\n".join(lines))


# ── help ───────────────────────────────────────────────────────────────────────

@app.message(r"(?i)^help\b")
def handle_help(message, say):
    say(
        "*Inventory Alert Bot — Commands*\n"
        "```\n"
        "  full inventory       All parts and on-hand quantities\n"
        "  low inventory        Only parts currently below threshold\n"
        "  <PART> qty           Quantity for a specific part or prefix\n"
        "                       e.g.  15H23 qty  |  19T qty\n"
        "\n"
        "  report               Bar chart — products created in last 30 days\n"
        "  report march         Bar chart — products created in March (this year)\n"
        "  report march 2025    Bar chart — products created in March 2025\n"
        "  report 2025-03       Same as above (YYYY-MM format)\n"
        "\n"
        "  thresholds           Show alert thresholds\n"
        "  help                 Show this message\n"
        "```\n"
        "_Automatic alerts fire when inventory drops at or below threshold.\n"
        "Weekly low-inventory report posts every Monday at 9 AM CST._"
    )


# ── Socket Mode entry-point ───────────────────────────────────────────────────

def start_bot() -> None:
    logger.info("Starting Slack bot via Socket Mode...")
    handler = SocketModeHandler(app, Config.SLACK_APP_TOKEN)
    handler.start()
