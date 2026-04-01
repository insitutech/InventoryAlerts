"""
Real-time inventory monitor.

Polls the Access database every POLL_INTERVAL_SECONDS seconds.
When a part's on-hand quantity drops AT OR BELOW its configured threshold,
a Slack alert is sent.

Alert de-duplication:
  - A part enters "alerted" state the first time it hits/crosses its threshold.
  - No further alert is sent until the part recovers ABOVE the threshold
    and then drops again (prevents spamming on every poll cycle).
"""

import logging
import time
import cache
from config import Config
from db import get_all_inventory
from slack_client import send_batch_low_inventory_alert, send_recovery_notice

logger = logging.getLogger(__name__)


def _threshold_for(part_name: str, thresholds: dict) -> int | None:
    """Return the threshold for *part_name*, checking exact match before prefix."""
    part_thresh: dict = thresholds.get("part_thresholds", {})
    prefix_thresh: dict = thresholds.get("prefix_thresholds", {})

    if part_name in part_thresh:
        return part_thresh[part_name]

    for prefix, value in prefix_thresh.items():
        if part_name.upper().startswith(prefix.upper()):
            return value

    return None


def run_monitor() -> None:
    """
    Blocking loop. Intended to run in a background daemon thread from main.py.
    Re-loads thresholds.json on every poll so you can adjust thresholds at
    runtime without restarting the process.

    All parts that newly cross below threshold in the same poll cycle are
    batched into ONE Slack message to avoid notification spam.
    """
    alerted_parts: set[str] = set()   # parts currently in "alerted" state

    logger.info(
        "Inventory monitor started — polling every %d s.", Config.POLL_INTERVAL
    )

    while True:
        try:
            thresholds = Config.load_thresholds()
            inventory = get_all_inventory()

            # Update the in-memory cache so bot commands respond instantly
            cache.update(inventory)

            # Collect all parts that are newly below threshold this cycle
            newly_low: list[tuple[str, int, int]] = []   # (part, qty, threshold)

            for part, qty in inventory.items():
                threshold = _threshold_for(part, thresholds)
                if threshold is None:
                    continue

                if qty <= threshold:
                    if part not in alerted_parts:
                        logger.warning(
                            "LOW INVENTORY: %s = %d unit(s) (threshold: %d)",
                            part, qty, threshold,
                        )
                        newly_low.append((part, qty, threshold))
                        alerted_parts.add(part)
                    else:
                        logger.debug("Still low (suppressed): %s = %d", part, qty)
                else:
                    if part in alerted_parts:
                        logger.info(
                            "RECOVERED: %s = %d unit(s) (threshold: %d)",
                            part, qty, threshold,
                        )
                        send_recovery_notice(part, qty, threshold)
                        alerted_parts.discard(part)

            # Send ONE combined alert for everything that went low this cycle
            if newly_low:
                send_batch_low_inventory_alert(newly_low)

        except ConnectionError as e:
            logger.error("Database unreachable: %s", e)
        except Exception as e:
            logger.error("Unexpected monitor error: %s", e, exc_info=True)

        time.sleep(Config.POLL_INTERVAL)
