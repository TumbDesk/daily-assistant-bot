"""Tests for occurrence keys and callback parsing."""
import unittest
import uuid
from datetime import datetime

from services.occurrence_util import (
    build_occ_callback,
    build_view_evt_callback,
    decode_occurrence,
    encode_occurrence,
    parse_view_evt_callback,
)


class TestOccurrenceUtil(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        dt = datetime(2026, 5, 29, 16, 0)
        key = encode_occurrence(dt)
        self.assertEqual(key, "202605291600")
        self.assertEqual(decode_occurrence(key), datetime(2026, 5, 29, 16, 0))

    def test_view_evt_callback_lengths(self):
        event_id = str(uuid.uuid4())
        self.assertLessEqual(len(build_view_evt_callback(event_id)), 64)
        self.assertLessEqual(
            len(build_view_evt_callback(event_id, datetime(2026, 5, 29, 16, 0))),
            64,
        )

    def test_parse_view_evt_without_occurrence(self):
        event_id = str(uuid.uuid4())
        parsed = parse_view_evt_callback(f"view_evt_{event_id}")
        self.assertEqual(parsed, (event_id, None))

    def test_parse_view_evt_with_occurrence(self):
        event_id = str(uuid.uuid4())
        occ = datetime(2026, 5, 29, 16, 0)
        data = build_view_evt_callback(event_id, occ)
        parsed = parse_view_evt_callback(data)
        self.assertEqual(parsed[0], event_id)
        self.assertEqual(parsed[1], occ)

    def test_build_occ_callback(self):
        event_id = str(uuid.uuid4())
        occ = datetime(2026, 6, 1, 9, 0)
        cb = build_occ_callback("del_one_", event_id, occ)
        self.assertTrue(cb.startswith("del_one_"))
        self.assertLessEqual(len(cb), 64)


if __name__ == "__main__":
    unittest.main()
