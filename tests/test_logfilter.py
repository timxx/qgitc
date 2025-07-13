import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from qgitc.logsfetchergitworker import LogFilter


class TestLogFilter(unittest.TestCase):
    def test_setupFilters_with_author(self):
        log_filter = LogFilter()
        log_filter.setupFilters(["--author=John Doe"])

        self.assertEqual(log_filter.author, "john doe")
        self.assertIsNone(log_filter.since)
        self.assertIsNone(log_filter.max_count)

    def test_setupFilters_with_max_count(self):
        log_filter = LogFilter()
        log_filter.setupFilters(["--max-count=10"])

        self.assertIsNone(log_filter.author)
        self.assertIsNone(log_filter.since)
        self.assertEqual(log_filter.max_count, 10)

    def test_setupFilters_with_since(self):
        log_filter = LogFilter()
        log_filter.setupFilters(["--since=2022-01-01"])
        self.assertIsNotNone(log_filter.since)

    def test_parse_date_formats(self):
        log_filter = LogFilter()

        # Test various formats
        self.assertEqual(
            log_filter._parse_date("2023-01-15"),
            datetime(2023, 1, 15, tzinfo=timezone.utc)
        )

        self.assertEqual(
            log_filter._parse_date("2023-01-15 14:30"),
            datetime(2023, 1, 15, 14, 30,
                     tzinfo=timezone.utc)
        )

        self.assertEqual(
            log_filter._parse_date("2023/01/15"),
            datetime(2023, 1, 15, tzinfo=timezone.utc)
        )

        self.assertEqual(
            log_filter._parse_date("2023"),
            datetime(2023, 1, 1, tzinfo=timezone.utc)
        )

        self.assertEqual(
            log_filter._parse_date("15 Jan 2023"),
            datetime(2023, 1, 15, tzinfo=timezone.utc)
        )

    def test_isFiltered(self):
        log_filter = LogFilter()
        log_filter.author = "john"

        # Create mock commit with matching author
        mock_commit_match = mock.MagicMock()
        mock_commit_match.author.name = "John Doe"

        # Create mock commit with non-matching author
        mock_commit_no_match = mock.MagicMock()
        mock_commit_no_match.author.name = "Alice Smith"

        self.assertFalse(log_filter.isFiltered(mock_commit_match))
        self.assertTrue(log_filter.isFiltered(mock_commit_no_match))

    def test_isStop(self):
        # Test stop by date
        log_filter = LogFilter()
        log_filter.since = time.time()  # current timestamp

        mock_commit_old = mock.MagicMock()
        mock_commit_old.commit_time = log_filter.since - 1000  # older commit

        mock_commit_new = mock.MagicMock()
        mock_commit_new.commit_time = log_filter.since + 1000  # newer commit

        self.assertTrue(log_filter.isStop(mock_commit_old))
        self.assertFalse(log_filter.isStop(mock_commit_new))

        # Test stop by max count
        log_filter = LogFilter()
        log_filter.since = None
        log_filter.max_count = 2

        mock_commit = mock.MagicMock()

        self.assertFalse(log_filter.isStop(mock_commit))  # count becomes 1
        self.assertFalse(log_filter.isStop(mock_commit))  # count becomes 0
        self.assertTrue(log_filter.isStop(mock_commit))   # count becomes -1

    def test_parse_relative_date_days(self):
        log_filter = LogFilter()

        # Test with singular form
        now = datetime.now(timezone.utc)
        result = log_filter._parse_relative_date("1 day ago")
        expected = now - timedelta(days=1)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

        # Test with plural form
        result = log_filter._parse_relative_date("5 days ago")
        expected = now - timedelta(days=5)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

    def test_parse_relative_date_weeks(self):
        log_filter = LogFilter()
        now = datetime.now(timezone.utc)

        # Test with singular form
        result = log_filter._parse_relative_date("1 week ago")
        expected = now - timedelta(weeks=1)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

        # Test with plural form
        result = log_filter._parse_relative_date("3 weeks ago")
        expected = now - timedelta(weeks=3)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

    def test_parse_relative_date_months_years(self):
        log_filter = LogFilter()
        now = datetime.now(timezone.utc)

        # Test months
        result = log_filter._parse_relative_date("1 month ago")
        expected = now - timedelta(days=30)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

        result = log_filter._parse_relative_date("6 months ago")
        expected = now - timedelta(days=6*30)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

        # Test years
        result = log_filter._parse_relative_date("1 year ago")
        expected = now - timedelta(days=365)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

        result = log_filter._parse_relative_date("2 years ago")
        expected = now - timedelta(days=2*365)
        self.assertAlmostEqual(
            result.timestamp(), expected.timestamp(), delta=2)

    def test_parse_relative_date_invalid_format(self):
        log_filter = LogFilter()

        # Test with wrong number of parts
        with self.assertRaises(ValueError):
            log_filter._parse_relative_date("1 day")

        with self.assertRaises(ValueError):
            log_filter._parse_relative_date("day ago")

        # Test with non-numeric quantity
        with self.assertRaises(ValueError):
            log_filter._parse_relative_date("abc day ago")

        # Test with invalid unit
        with self.assertRaises(ValueError):
            log_filter._parse_relative_date("1 century ago")
