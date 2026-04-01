"""
APScheduler-based job runner.

Scheduled jobs:
  weekly_inventory_report — Every Monday at 09:00 CST
      Posts a full inventory table to the configured Slack channel, with ⚠️ flags
      on any parts that are at or below their threshold.
"""

import logging
import pytz
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from config import Config
from db import get_all_inventory
from slack_client import send_message

logger = logging.getLogger(__name__)


def _threshold_for(name: str, thresholds: dict):
    part_thresh = thresholds.get("part_thresholds", {})
    prefix_thresh = thresholds.get("prefix_thresholds", {})
    if name in part_thresh:
        return part_thresh[name]
    for pfx, val in prefix_thresh.items():
        if name.upper().startswith(pfx.upper()):
            return val
    return None


def weekly_inventory_report() -> None:
    logger.info("Running scheduled weekly inventory report...")
    try:
        thresholds = Config.load_thresholds()
        inventory = get_all_inventory()

        tz = pytz.timezone(Config.REPORT_TIMEZONE)
        now_str = datetime.now(tz).strftime("%Y-%m-%d %I:%M %p %Z")

        low_parts = {
            part: qty for part, qty in inventory.items()
            if (t := _threshold_for(part, thresholds)) is not None and qty <= t
        }

        if not low_parts:
            send_message(
                Config.SLACK_ALERT_CHANNEL,
                f":white_check_mark: *Weekly Inventory Report* — _{now_str}_\nAll monitored parts are above threshold.",
            )
        else:
            lines = [f":warning: *Weekly Low Inventory Report* — _{now_str}_", ""]
            for part in sorted(low_parts):
                lines.append(f"*{part}* - {low_parts[part]}")
            send_message(Config.SLACK_ALERT_CHANNEL, "\n".join(lines))

        logger.info("Weekly report sent (%d parts checked).", len(inventory))
    except ConnectionError as e:
        logger.error("Weekly report failed — database unreachable: %s", e)
    except Exception as e:
        logger.error("Weekly report failed: %s", e, exc_info=True)


def start_scheduler() -> BackgroundScheduler:
    """
    Start the background scheduler and return it so main.py can shut it down
    cleanly on exit.
    """
    tz = pytz.timezone(Config.REPORT_TIMEZONE)

    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(
        weekly_inventory_report,
        trigger=CronTrigger(
            day_of_week=Config.REPORT_DAY_OF_WEEK,
            hour=Config.REPORT_HOUR,
            minute=Config.REPORT_MINUTE,
            timezone=tz,
        ),
        id="weekly_inventory_report",
        name="Weekly Inventory Report (Monday 9 AM CST)",
        replace_existing=True,
    )
    scheduler.start()

    next_run = scheduler.get_job("weekly_inventory_report").next_run_time
    logger.info(
        "Scheduler started — next weekly report: %s",
        next_run.strftime("%Y-%m-%d %H:%M %Z"),
    )
    return scheduler
