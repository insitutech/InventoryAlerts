"""
Thin wrapper around slack_sdk.WebClient for sending messages, alerts, and reports.
All outgoing messages go through this module so formatting stays consistent.
"""

import logging
from datetime import datetime
import pytz
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from config import Config

logger = logging.getLogger(__name__)

_client: WebClient | None = None


def get_client() -> WebClient:
    global _client
    if _client is None:
        _client = WebClient(token=Config.SLACK_BOT_TOKEN)
    return _client


# ── Low-level send ────────────────────────────────────────────────────────────

def send_message(channel: str, text: str, blocks: list | None = None) -> bool:
    """Post a message to *channel*. Returns True on success."""
    try:
        kwargs: dict = {"channel": channel, "text": text}
        if blocks:
            kwargs["blocks"] = blocks
        get_client().chat_postMessage(**kwargs)
        return True
    except SlackApiError as e:
        logger.error("Slack API error sending to %s: %s", channel, e.response["error"])
        return False
    except Exception as e:
        logger.error("Unexpected error sending Slack message: %s", e)
        return False


# ── Alerts ────────────────────────────────────────────────────────────────────

def send_batch_low_inventory_alert(parts: list[tuple[str, int, int]]) -> None:
    """
    ONE combined alert for all parts that went low in the same poll cycle.
    parts = list of (part_name, on_hand, threshold).
    Format:  *PART* - QTY
    """
    if not parts:
        return

    lines = [":warning: *Low Inventory Alert*", ""]
    for part_name, on_hand, _ in sorted(parts):
        lines.append(f"*{part_name}* - {on_hand}")

    logger.info("Sending low-inventory alert for %d part(s).", len(parts))
    send_message(Config.SLACK_ALERT_CHANNEL, "\n".join(lines))


def send_recovery_notice(part_name: str, on_hand: int, threshold: int) -> None:
    """Notify when a previously-alerted part recovers above threshold."""
    text = f":white_check_mark: *Inventory Recovered*\n*{part_name}* - {on_hand}"
    send_message(Config.SLACK_ALERT_CHANNEL, text)


# ── Reports ───────────────────────────────────────────────────────────────────

def _timestamp() -> str:
    tz = pytz.timezone(Config.REPORT_TIMEZONE)
    return datetime.now(tz).strftime("%Y-%m-%d %I:%M %p %Z")


def _threshold_for(name: str, thresholds: dict) -> int | None:
    part_thresh: dict = thresholds.get("part_thresholds", {})
    prefix_thresh: dict = thresholds.get("prefix_thresholds", {})
    if name in part_thresh:
        return part_thresh[name]
    for pfx, val in prefix_thresh.items():
        if name.upper().startswith(pfx.upper()):
            return val
    return None


def send_weekly_low_inventory_report(inventory: dict[str, int], thresholds: dict) -> None:
    """
    Monday 9 AM report — posts ONLY parts that are at or below their threshold.
    Format:  *PART* - QTY
    """
    low_parts = {
        part: qty for part, qty in inventory.items()
        if (t := _threshold_for(part, thresholds)) is not None and qty <= t
    }

    if not low_parts:
        send_message(
            Config.SLACK_ALERT_CHANNEL,
            f":white_check_mark: *Weekly Inventory Report* — _{_timestamp()}_\nAll monitored parts are above threshold.",
        )
        return

    lines = [f":warning: *Weekly Low Inventory Report* — _{_timestamp()}_", ""]
    for part in sorted(low_parts):
        lines.append(f"*{part}* - {low_parts[part]}")

    send_message(Config.SLACK_ALERT_CHANNEL, "\n".join(lines))


def send_full_inventory_report(
    inventory: dict[str, int],
    thresholds: dict,
    channel: str,
    title: str = "Full Inventory",
) -> None:
    """All monitored parts and their quantities, no emoji flags."""
    if not inventory:
        send_message(channel, f"*{title}*\nNo monitored parts found.")
        return

    lines = [f"*{title}* — _{_timestamp()}_", "```"]
    for part in sorted(inventory):
        qty = inventory[part]
        lines.append(f"  {part:<22} {qty:>5}")
    lines.append("```")

    send_message(channel, "\n".join(lines))


def send_production_report(
    data: dict[str, int],
    title: str,
    channel: str,
) -> None:
    """
    Post a horizontal ASCII bar chart of products created in a date range.
    Only products with qty >= 1 are shown (zeros already filtered by DB query).
    """
    if not data:
        send_message(channel, f"*{title}*\nNo products were created in this period.")
        return

    max_qty = max(data.values()) or 1
    bar_width = 28          # max bar length in characters
    name_width = max(len(k) for k in data) + 2

    lines = [f"*{title}*", "```"]
    lines.append("─" * (name_width + bar_width + 8))
    for product, qty in data.items():
        bars = round(qty / max_qty * bar_width)
        bar = "█" * bars
        lines.append(f"  {product:<{name_width}} {bar:<{bar_width}}  {qty}")
    lines.append("─" * (name_width + bar_width + 8))
    lines.append(f"  {'TOTAL':<{name_width}} {sum(data.values())} units across {len(data)} product(s)")
    lines.append("```")

    send_message(channel, "\n".join(lines))


def send_low_parts_report(
    inventory: dict[str, int],
    thresholds: dict,
    channel: str,
) -> None:
    """Only parts at or below threshold. Format: *PART* - QTY"""
    low = {
        part: qty for part, qty in inventory.items()
        if (t := _threshold_for(part, thresholds)) is not None and qty <= t
    }

    if not low:
        send_message(channel, ":white_check_mark: *Low Inventory* — All parts are above threshold.")
        return

    lines = [f":warning: *Low Inventory* — _{_timestamp()}_", ""]
    for part in sorted(low):
        lines.append(f"*{part}* - {low[part]}")

    send_message(channel, "\n".join(lines))
