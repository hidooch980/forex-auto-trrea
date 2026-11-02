from datetime import datetime, timedelta, timezone

from modules.market_data_quality import validate_bars


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def bars(count=3):
    return [
        {"time": NOW - timedelta(minutes=3 - i), "open": 1.1, "high": 1.12,
         "low": 1.09, "close": 1.11, "tick_volume": 100, "spread": 12}
        for i in range(count)
    ]


def test_valid_chronological_bars_pass():
    report = validate_bars(bars(), as_of=NOW, max_age_seconds=180, expected_interval_seconds=60)
    assert report.valid
    assert report.duplicate_timestamps == 0


def test_duplicate_timestamp_fails_closed():
    sample = bars()
    sample[2]["time"] = sample[1]["time"]
    report = validate_bars(sample, as_of=NOW)
    assert not report.valid
    assert "duplicate_timestamps_present" in report.errors


def test_out_of_order_rows_fail():
    sample = list(reversed(bars()))
    report = validate_bars(sample, as_of=NOW)
    assert not report.valid and report.out_of_order_rows > 0


def test_invalid_ohlc_fails():
    sample = bars()
    sample[0]["high"] = 1.0
    report = validate_bars(sample, as_of=NOW)
    assert not report.valid and report.invalid_ohlc_rows == 1


def test_stale_and_future_data_fail():
    old = [{"time": NOW - timedelta(hours=1), "open": 1, "high": 2, "low": .5, "close": 1.5}]
    assert validate_bars(old, as_of=NOW, max_age_seconds=60).stale
    future = bars()
    future[-1]["time"] = NOW + timedelta(minutes=5)
    assert not validate_bars(future, as_of=NOW).valid


def test_gaps_are_reported():
    sample = bars()
    sample[2]["time"] = sample[1]["time"] + timedelta(minutes=5)
    report = validate_bars(sample, as_of=NOW, expected_interval_seconds=60)
    assert report.gap_count == 1 and not report.valid


def test_empty_input_fails_closed():
    assert not validate_bars([], as_of=NOW).valid


def test_naive_timestamp_rejected():
    sample = bars()
    sample[0]["time"] = datetime(2026, 11, 2, 11, 58)
    assert not validate_bars(sample, as_of=NOW).valid
