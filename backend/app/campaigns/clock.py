"""Current business date for campaign lookup, activity and client ages."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

SINGAPORE = ZoneInfo("Asia/Singapore")


def current_date() -> date:
    # Evaluate per operation, so long-running services advance at midnight.
    return datetime.now(SINGAPORE).date()
