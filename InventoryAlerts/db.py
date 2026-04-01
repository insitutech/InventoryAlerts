"""
Access database reader.

Inventory formula mirrors DHR.aspx.cs updateQty_Click exactly:

  on_hand = SUM(tblReceiving.QuantityReceived  WHERE PartNumber = <part_id>)
          - SUM(tblLotTracking.QuantityConverted
                  JOIN tblLots ON tblLots.LotIssue = tblLotTracking.LotIssue
                WHERE tblLotTracking.PartNumber = <part_id>)

Parts monitored are those whose PartNumber in tblSupplies matches the same
prefix rules used in DHR.aspx.cs rpItems_ItemDataBound / updateQty_Click.

Supplier 155 ("InSitu FIZ - Inventory Adjust") is included in QuantityReceived
totals (same as qtyTotal in the original code).
"""

import logging
import pyodbc
from datetime import date, datetime
from config import Config

logger = logging.getLogger(__name__)

# ── Part-prefix filter ────────────────────────────────────────────────────────
# Only track the prefixes requested: 19T, 19S, 22PM, 15H, 18 (covers 18M too)
_MONITORED_PREFIXES = ("19T", "19S", "22PM", "15H", "18")


def is_monitored_part(part_name: str) -> bool:
    """Return True if this part's prefix is in the monitored set."""
    if not part_name:
        return False
    p = part_name.upper()
    for prefix in _MONITORED_PREFIXES:
        if p.startswith(prefix.upper()):
            return True
    return False


# ── Connection ────────────────────────────────────────────────────────────────

def _get_connection() -> pyodbc.Connection:
    """
    Open a read-only ODBC connection to the MS Access .mdb file.
    Tries the 64-bit ACE driver first, then the legacy 32-bit Jet driver.
    The machine running QBApp already has at least one of these installed.
    """
    db_path = Config.ACCESS_DB_PATH
    drivers_to_try = [
        f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={db_path};",
        f"DRIVER={{Microsoft Access Driver (*.mdb)}};DBQ={db_path};",
        f"Provider=Microsoft.ACE.OLEDB.12.0;Data Source={db_path};",
    ]
    last_err = None
    for conn_str in drivers_to_try:
        try:
            conn = pyodbc.connect(conn_str, readonly=True)
            logger.debug("Connected with: %s", conn_str.split(";")[0])
            return conn
        except pyodbc.Error as e:
            last_err = e
            continue
    raise ConnectionError(
        f"Could not connect to Access database at:\n  {db_path}\n"
        f"Last error: {last_err}\n"
        "Make sure the Microsoft Access Database Engine (ACE/Jet) is installed\n"
        "and that the .mdb file path is accessible from this machine."
    ) from last_err


# ── Core inventory query ──────────────────────────────────────────────────────

def get_all_inventory() -> dict[str, int]:
    """
    Return {part_name: on_hand_qty} for every monitored part found in tblSupplies.

    Uses 3 bulk queries (not one per part) to keep response time fast over a
    network share.

    Raises ConnectionError if the database is unreachable.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # ── Query 1: all parts from tblSupplies ───────────────────────────────
        cursor.execute("SELECT PartID, PartNumber FROM tblSupplies WHERE PartNumber IS NOT NULL")
        all_supplies = cursor.fetchall()

        monitored = {int(row[0]): str(row[1]) for row in all_supplies if is_monitored_part(row[1])}
        if not monitored:
            return {}
        logger.debug("Monitored parts in tblSupplies: %d", len(monitored))

        # ── Query 2: total received per part (all suppliers) ──────────────────
        cursor.execute(
            "SELECT PartNumber, SUM(QuantityReceived) "
            "FROM tblReceiving "
            "WHERE QuantityReceived IS NOT NULL "
            "GROUP BY PartNumber"
        )
        received: dict[int, int] = {
            int(row[0]): int(row[1])
            for row in cursor.fetchall()
            if row[0] is not None and row[1] is not None
        }

        # ── Query 3: total converted per part (kitted via lot tracking) ───────
        cursor.execute(
            "SELECT lt.PartNumber, SUM(lt.QuantityConverted) "
            "FROM tblLots AS l "
            "INNER JOIN tblLotTracking AS lt ON l.LotIssue = lt.LotIssue "
            "WHERE lt.QuantityConverted IS NOT NULL "
            "GROUP BY lt.PartNumber"
        )
        converted: dict[int, int] = {
            int(row[0]): int(row[1])
            for row in cursor.fetchall()
            if row[0] is not None and row[1] is not None
        }

        # ── Compute on_hand in Python ─────────────────────────────────────────
        inventory: dict[str, int] = {}
        for part_id, part_name in monitored.items():
            qty_total = received.get(part_id, 0)
            qty_converted = converted.get(part_id, 0)
            on_hand = qty_total - qty_converted
            inventory[part_name] = on_hand
            logger.debug(
                "%s (id=%d): received=%d  converted=%d  on_hand=%d",
                part_name, part_id, qty_total, qty_converted, on_hand,
            )

        return inventory

    finally:
        conn.close()


def get_part_inventory(part_name: str) -> int | None:
    """Return on-hand quantity for a single part, or None if not found."""
    inventory = get_all_inventory()
    return inventory.get(part_name)


def get_production_report(start: date, end: date) -> dict[str, int]:
    """
    Return {catalog_number: total_qty_created} for all products kitted
    between *start* (inclusive) and *end* (exclusive) with qty > 0.

    Queries: tblLots JOIN tblProducts
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT p.CatalogNumber, SUM(l.QuantityCreated) "
            "FROM tblLots AS l "
            "INNER JOIN tblProducts AS p ON l.ProductNumber = p.ProductID "
            "WHERE l.DateCreated >= ? AND l.DateCreated < ? "
            "  AND l.QuantityCreated IS NOT NULL "
            "  AND l.QuantityCreated > 0 "
            "GROUP BY p.CatalogNumber "
            "ORDER BY SUM(l.QuantityCreated) DESC",
            start, end,
        )
        rows = cursor.fetchall()
        return {str(row[0]): int(row[1]) for row in rows if row[0] and row[1]}
    finally:
        conn.close()
