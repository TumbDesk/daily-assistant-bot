"""Tests for hourly rain block analysis."""
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from services.weather import (
    RainBlock,
    TodaysWeather,
    find_rain_blocks,
    format_rain_risk_lines,
    parse_hourly_for_today,
    summarize_rain_periods,
)

TZ = ZoneInfo("Europe/Berlin")
TEST_DAY = "2026-05-25"


def _build_hourly_mock(day: str = TEST_DAY) -> dict:
    probs = [0] * 24
    for hour in range(10, 12):
        probs[hour] = 80
    for hour in range(18, 20):
        probs[hour] = 60
    times = [f"{day}T{hour:02d}:00" for hour in range(24)]
    return {"time": times, "precipitation_probability": probs}


def _parse_and_summarize(hourly: dict, fake_now: datetime) -> list[RainBlock]:
    with patch("services.weather.datetime") as mock_dt:
        mock_dt.fromisoformat.side_effect = datetime.fromisoformat
        mock_dt.now.return_value = fake_now
        hours = parse_hourly_for_today(hourly, tz=TZ)
    return summarize_rain_periods(hours)


def _build_outlook_section(
    blocks: tuple[RainBlock, ...], *, precipitation_sum: float = 2.4
) -> str:
    rain_lines = format_rain_risk_lines(80, blocks)
    return (
        "☔ Aussichten für heute:\n"
        + "\n".join(f"• {line}" for line in rain_lines)
        + f"\n• Regenmenge: {precipitation_sum:.1f} mm"
    )


def _hour(hour: int, prob: int, day: str = "2026-05-24") -> tuple[datetime, int]:
    return (
        datetime.fromisoformat(f"{day}T{hour:02d}:00").replace(tzinfo=TZ),
        prob,
    )


def _block(
    start_hour: int,
    end_hour: int,
    *,
    max_probability: int = 80,
    avg_probability: int = 70,
    hour_count: int = 2,
    day: str = "2026-05-24",
) -> RainBlock:
    start = datetime.fromisoformat(f"{day}T{start_hour:02d}:00").replace(tzinfo=TZ)
    end = datetime.fromisoformat(f"{day}T{end_hour:02d}:00").replace(tzinfo=TZ)
    return RainBlock(
        max_probability=max_probability,
        avg_probability=avg_probability,
        start=start,
        end=end,
        hour_count=hour_count,
    )


class TestFindRainBlocks(unittest.TestCase):
    def test_no_blocks_below_threshold(self):
        hours = [_hour(h, 10) for h in range(8, 12)]
        self.assertEqual(find_rain_blocks(hours), [])

    def test_single_block_uses_actual_clock_time(self):
        hours = [
            _hour(10, 40),
            _hour(11, 80),
            _hour(12, 50),
        ]
        blocks = find_rain_blocks(hours)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].start_time, "10:00")
        self.assertEqual(blocks[0].end_time, "13:00")
        self.assertEqual(blocks[0].avg_probability, 57)


class TestSummarizeRainPeriods(unittest.TestCase):
    def test_splits_by_intensity_tiers(self):
        hours = [
            _hour(0, 46),
            _hour(1, 72),
            _hour(2, 92),
            _hour(3, 99),
            _hour(4, 40),
            _hour(5, 38),
        ]
        periods = summarize_rain_periods(hours)
        self.assertGreaterEqual(len(periods), 2)
        self.assertEqual(periods[0].start_time, "00:00")
        self.assertEqual(periods[-1].start_time, "04:00")

    def test_two_separate_windows(self):
        hours = [
            _hour(10, 80),
            _hour(11, 70),
            _hour(12, 10),
            _hour(13, 10),
            _hour(18, 60),
            _hour(19, 55),
        ]
        periods = summarize_rain_periods(hours)
        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0].start_time, "10:00")
        self.assertEqual(periods[1].start_time, "18:00")

    def test_filtered_hours_keep_clock_time_not_list_index(self):
        hours = [_hour(h, 80, day="2026-05-25") for h in range(13, 18)]
        periods = summarize_rain_periods(hours)
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].start_time, "13:00")
        self.assertEqual(periods[0].end_time, "18:00")
        self.assertNotEqual(periods[0].start_time, "00:00")


class TestFormatRainRiskLines(unittest.TestCase):
    def test_below_threshold(self):
        self.assertEqual(
            format_rain_risk_lines(25, ()),
            ["Regenrisiko: 25 %"],
        )

    def test_multiple_period_lines(self):
        blocks = (
            _block(10, 12, max_probability=80, avg_probability=75),
            _block(18, 20, max_probability=60, avg_probability=58),
        )
        lines = format_rain_risk_lines(80, blocks)
        self.assertEqual(len(lines), 2)
        self.assertIn("10:00–12:00 Uhr", lines[0])
        self.assertIn("Ø 75 %", lines[0])
        self.assertIn("18:00–20:00 Uhr", lines[1])

    def test_shows_max_when_higher_than_average(self):
        block = _block(
            2, 17, max_probability=100, avg_probability=85, hour_count=15
        )
        lines = format_rain_risk_lines(100, (block,))
        self.assertIn("Ø 85 %", lines[0])
        self.assertIn("max. 100 %", lines[0])


class TestParseHourlyForToday(unittest.TestCase):
    def test_filters_to_today_only(self):
        hourly = {
            "time": [
                "2026-05-24T10:00",
                "2026-05-24T11:00",
                "2026-05-25T10:00",
            ],
            "precipitation_probability": [40, 50, 90],
        }
        fake_now = datetime(2026, 5, 24, 8, 0, tzinfo=TZ)
        with patch("services.weather.datetime") as mock_dt:
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.now.return_value = fake_now
            result = parse_hourly_for_today(hourly, tz=TZ)
        self.assertEqual(len(result), 2)

    def test_excludes_past_hours_of_today(self):
        hourly = {
            "time": [
                "2026-05-24T08:00",
                "2026-05-24T09:00",
                "2026-05-24T10:00",
            ],
            "precipitation_probability": [80, 70, 60],
        }
        fake_now = datetime(2026, 5, 24, 9, 30, tzinfo=TZ)
        with patch("services.weather.datetime") as mock_dt:
            mock_dt.fromisoformat.side_effect = datetime.fromisoformat
            mock_dt.now.return_value = fake_now
            result = parse_hourly_for_today(hourly, tz=TZ)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0].hour, 9)


class TestRainOutlookWithDryGap(unittest.TestCase):
    def test_two_rain_blocks_with_dry_gap(self):
        hourly = _build_hourly_mock()
        fake_now = datetime(2026, 5, 25, 0, 0, tzinfo=TZ)
        blocks = _parse_and_summarize(hourly, fake_now)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].start_time, "10:00")
        self.assertEqual(blocks[0].end_time, "12:00")
        self.assertEqual(blocks[0].avg_probability, 80)
        self.assertEqual(blocks[1].start_time, "18:00")
        self.assertEqual(blocks[1].end_time, "20:00")
        self.assertEqual(blocks[1].avg_probability, 60)

        lines = format_rain_risk_lines(80, tuple(blocks))
        self.assertEqual(len(lines), 2)
        for dry_hour in range(13, 18):
            for line in lines:
                self.assertNotIn(f"{dry_hour:02d}:00", line)

        outlook = _build_outlook_section(tuple(blocks))
        self.assertEqual(
            outlook.splitlines(),
            [
                "☔ Aussichten für heute:",
                "• Regenrisiko 10:00–12:00 Uhr: 80 %",
                "• Regenrisiko 18:00–20:00 Uhr: 60 %",
                "• Regenmenge: 2.4 mm",
            ],
        )

        weather = TodaysWeather(
            observed_at=f"{TEST_DAY}T00:00",
            temperature=15.0,
            apparent_temperature=14.0,
            temperature_min=10.0,
            temperature_max=20.0,
            humidity=50,
            wind_speed=10.0,
            weather_code=3,
            precipitation_probability=80,
            precipitation_sum=2.4,
            rain_blocks=tuple(blocks),
        )
        self.assertEqual(len(weather.rain_blocks), 2)

    def test_afternoon_query_skips_morning_block(self):
        hourly = _build_hourly_mock()
        fake_now = datetime(2026, 5, 25, 13, 0, tzinfo=TZ)
        blocks = _parse_and_summarize(hourly, fake_now)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].start_time, "18:00")
        self.assertEqual(blocks[0].end_time, "20:00")
        self.assertEqual(blocks[0].avg_probability, 60)
        self.assertNotEqual(blocks[0].start_time, "00:00")

        lines = format_rain_risk_lines(80, tuple(blocks))
        self.assertEqual(len(lines), 1)
        self.assertIn("18:00–20:00 Uhr", lines[0])
        self.assertNotIn("10:00", lines[0])


if __name__ == "__main__":
    unittest.main()
