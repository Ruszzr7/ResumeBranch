"""Helpers for serializing database timestamps across the API boundary."""

from datetime import datetime, timezone


def serialize_utc_datetime(value: datetime | None) -> str | None:
    """Serialize naive database UTC timestamps with an explicit UTC marker.

    Existing SQLAlchemy columns use naive ``datetime.utcnow()`` values.  An
    explicit ``Z`` prevents browsers from interpreting those values as local
    time, which would otherwise introduce an eight-hour shift in China.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
