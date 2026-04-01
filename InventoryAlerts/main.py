"""
InventoryAlerts — entry point.

Starts three concurrent components:
  1. Inventory monitor  — background thread, polls Access DB every N seconds,
                          sends Slack alerts when parts drop below threshold.
  2. Weekly scheduler   — background thread, posts full inventory report to Slack
                          every Monday at 9:00 AM CST.
  3. Slack bot          — main thread, Socket Mode handler that responds to
                          "inventory", "thresholds", and "help" commands.

Run:
    python main.py
"""

import logging
import signal
import sys
import threading

from config import Config
from monitor import run_monitor
from scheduler import start_scheduler
from bot import start_bot

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("inventory_alerts.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ── Graceful shutdown ─────────────────────────────────────────────────────────

_scheduler = None

def _shutdown(signum, frame):
    logger.info("Shutdown signal received — stopping scheduler...")
    if _scheduler:
        _scheduler.shutdown(wait=False)
    logger.info("Bye.")
    sys.exit(0)

signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("=" * 60)
    logger.info("  InSitu InventoryAlerts starting up")
    logger.info("=" * 60)

    # Validate .env before going any further
    Config.validate()

    logger.info("Access DB : %s", Config.ACCESS_DB_PATH)
    logger.info("Slack channel : %s", Config.SLACK_ALERT_CHANNEL)
    logger.info("Poll interval : %d s", Config.POLL_INTERVAL)

    # 1. Weekly scheduler (background)
    global _scheduler
    _scheduler = start_scheduler()

    # 2. Inventory monitor (background daemon thread)
    monitor_thread = threading.Thread(
        target=run_monitor,
        name="InventoryMonitor",
        daemon=True,
    )
    monitor_thread.start()
    logger.info("Inventory monitor thread started.")

    # 3. Slack bot — blocks the main thread via Socket Mode
    start_bot()


if __name__ == "__main__":
    main()
