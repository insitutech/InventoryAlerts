import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this file
_BASE_DIR = Path(__file__).parent
load_dotenv(_BASE_DIR / ".env")


class Config:
    # ── Slack ──────────────────────────────────────────────────────────────────
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_APP_TOKEN: str = os.getenv("SLACK_APP_TOKEN", "")
    SLACK_ALERT_CHANNEL: str = os.getenv("SLACK_ALERT_CHANNEL", "")

    # ── Access Database ────────────────────────────────────────────────────────
    ACCESS_DB_PATH: str = os.getenv(
        "ACCESS_DB_PATH",
        r"\\INSITU-SERV2022\NetServ_2\Manufacturing-Operations\DATABASE\Insitu Program MASTER.mdb",
    )

    # ── Monitor ────────────────────────────────────────────────────────────────
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

    # ── Scheduler ─────────────────────────────────────────────────────────────
    REPORT_DAY_OF_WEEK: str = "mon"
    REPORT_HOUR: int = 9
    REPORT_MINUTE: int = 0
    REPORT_TIMEZONE: str = "US/Central"

    # ── Thresholds file ───────────────────────────────────────────────────────
    _THRESHOLDS_PATH: Path = _BASE_DIR / "thresholds.json"

    @classmethod
    def load_thresholds(cls) -> dict:
        if not cls._THRESHOLDS_PATH.exists():
            return {"prefix_thresholds": {}, "part_thresholds": {}}
        with open(cls._THRESHOLDS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Strip comment keys
        data.pop("_comment", None)
        return data

    @classmethod
    def validate(cls) -> None:
        """Exit with a clear error message if required settings are missing."""
        missing = []
        if not cls.SLACK_BOT_TOKEN:
            missing.append("SLACK_BOT_TOKEN")
        if not cls.SLACK_APP_TOKEN:
            missing.append("SLACK_APP_TOKEN")
        if not cls.SLACK_ALERT_CHANNEL:
            missing.append("SLACK_ALERT_CHANNEL")
        if missing:
            print(
                f"[ERROR] Missing required environment variables: {', '.join(missing)}\n"
                f"Copy .env.example to .env and fill in the values.",
                file=sys.stderr,
            )
            sys.exit(1)
