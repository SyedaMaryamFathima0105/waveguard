import unittest
from datetime import datetime, timezone, timedelta

from monitoring_engine import MonitoringEngine


class TestMonitoringEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MonitoringEngine(
            stale_after_seconds=10,
            maximum_rate_per_second=5
        )

        self.engine.register_zone("Road Zone")
        self.engine.register_zone("Underpass Zone")
        self.engine.register_zone("Drainage Zone")

        self.start_time = datetime(
            2026, 10, 21, 10, 0, 0,
            tzinfo=timezone.utc
        )

    def test_normal_reading(self):
        result = self.engine.process_reading(
            "Road Zone", 15, self.start_time
        )

        self.assertEqual(result.state, "NORMAL")
        self.assertEqual(result.value, 15.0)

    def test_warning_threshold(self):
        result = self.engine.process_reading(
            "Road Zone", 25, self.start_time
        )

        self.assertEqual(result.state, "WARNING")

    def test_danger_threshold(self):
        result = self.engine.process_reading(
            "Road Zone", 40, self.start_time
        )

        self.assertEqual(result.state, "DANGER")

    def test_negative_reading_is_invalid(self):
        result = self.engine.process_reading(
            "Road Zone", -5, self.start_time
        )

        self.assertEqual(result.state, "INVALID")

    def test_reading_above_maximum_is_invalid(self):
        result = self.engine.process_reading(
            "Road Zone", 55, self.start_time
        )

        self.assertEqual(result.state, "INVALID")

    def test_missing_reading_is_unavailable(self):
        result = self.engine.process_reading(
            "Road Zone", None, self.start_time
        )

        self.assertEqual(result.state, "UNAVAILABLE")

    def test_sudden_spike_is_suspicious(self):
        self.engine.process_reading(
            "Road Zone", 10, self.start_time
        )

        result = self.engine.process_reading(
            "Road Zone",
            30,
            self.start_time + timedelta(seconds=1)
        )

        self.assertEqual(result.state, "SUSPICIOUS")

    def test_stale_reading_detection(self):
        self.engine.process_reading(
            "Road Zone", 15, self.start_time
        )

        status = self.engine.get_zone_status(
            "Road Zone",
            self.start_time + timedelta(seconds=15)
        )

        self.assertEqual(status["state"], "STALE")

    def test_zones_keep_separate_readings(self):
        self.engine.process_reading(
            "Road Zone", 20, self.start_time
        )

        self.engine.process_reading(
            "Underpass Zone", 35, self.start_time
        )

        road = self.engine.get_zone_status(
            "Road Zone", self.start_time
        )

        underpass = self.engine.get_zone_status(
            "Underpass Zone", self.start_time
        )

        self.assertEqual(road["last_valid_value"], 20.0)
        self.assertEqual(underpass["last_valid_value"], 35.0)

    def test_event_log_records_readings(self):
        self.engine.process_reading(
            "Road Zone", 15, self.start_time
        )

        events = self.engine.get_events()

        self.assertTrue(
            any(event["event"] == "NORMAL" for event in events)
        )

    def test_unknown_zone_raises_error(self):
        with self.assertRaises(KeyError):
            self.engine.process_reading(
                "Unknown Zone", 10, self.start_time
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
    