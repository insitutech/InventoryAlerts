"""
Thread-safe in-memory inventory cache.

The monitor thread writes here after every DB poll.
Bot commands read from here instantly — no DB round-trip needed.
"""

import threading
from datetime import datetime
from typing import Optional

_lock = threading.Lock()
_inventory: dict[str, int] = {}
_last_updated: Optional[datetime] = None


def update(inventory: dict[str, int]) -> None:
    """Called by the monitor thread after every successful DB poll."""
    global _inventory, _last_updated
    with _lock:
        _inventory = dict(inventory)
        _last_updated = datetime.now()


def get() -> tuple[dict[str, int], Optional[datetime]]:
    """Return a snapshot of the cached inventory and when it was last updated."""
    with _lock:
        return dict(_inventory), _last_updated


def is_ready() -> bool:
    """False only during the first 60 seconds before the first poll completes."""
    with _lock:
        return len(_inventory) > 0
