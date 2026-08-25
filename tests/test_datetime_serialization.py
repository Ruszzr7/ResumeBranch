import unittest
from datetime import datetime, timedelta, timezone

from backend.datetime_utils import serialize_utc_datetime


class DateTimeSerializationTests(unittest.TestCase):
    def test_naive_database_utc_is_marked_as_utc(self):
        value = serialize_utc_datetime(datetime(2026, 8, 25, 2, 0, 0))
        self.assertEqual(value, "2026-08-25T02:00:00Z")

    def test_aware_datetime_is_normalized_to_utc(self):
        value = serialize_utc_datetime(
            datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone(timedelta(hours=8)))
        )
        self.assertEqual(value, "2026-08-25T02:00:00Z")

    def test_none_remains_none(self):
        self.assertIsNone(serialize_utc_datetime(None))
