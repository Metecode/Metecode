"""Tests for streak_card.py.  Run: python -m unittest discover -s scripts -p "test_*.py" """

import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streak_card as sc  # noqa: E402


def span(start: date, counts: list[int]) -> dict[date, int]:
    return {start + timedelta(days=i): c for i, c in enumerate(counts)}


def calendar(days: dict[date, int]) -> dict:
    return {"contributionCalendar": {
        "totalContributions": sum(days.values()),
        "weeks": [{"contributionDays": [
            {"date": d.isoformat(), "contributionCount": c} for d, c in sorted(days.items())
        ]}],
    }}


class CurrentStreakTests(unittest.TestCase):
    def test_today_empty_yesterday_active_keeps_streak(self):
        today = date(2026, 11, 5)
        days = span(date(2026, 10, 30), [0, 2, 1, 3, 5, 4, 0])  # Oct 31 - Nov 4 active, Nov 5 empty
        s = sc.compute_stats(days, today, date(2026, 10, 30))
        self.assertEqual(s.current.length, 5)
        self.assertEqual((s.current.start, s.current.end), (date(2026, 10, 31), date(2026, 11, 4)))

    def test_today_missing_from_calendar_behaves_like_empty(self):
        today = date(2026, 11, 5)
        days = span(date(2026, 11, 1), [1, 1, 1, 1])  # Nov 1-4, no entry for Nov 5
        s = sc.compute_stats(days, today, date(2026, 11, 1))
        self.assertEqual(s.current.length, 4)

    def test_today_active_counts_today(self):
        today = date(2026, 11, 5)
        days = span(date(2026, 11, 1), [0, 0, 1, 1, 2])
        s = sc.compute_stats(days, today, date(2026, 11, 1))
        self.assertEqual(s.current, sc.Streak(3, date(2026, 11, 3), today))

    def test_today_and_yesterday_empty_resets_to_zero(self):
        today = date(2026, 11, 5)
        days = span(date(2026, 10, 25), [1] * 9 + [0, 0])  # Oct 25 - Nov 2 active
        s = sc.compute_stats(days, today, date(2026, 10, 25))
        self.assertEqual(s.current, sc.Streak())
        self.assertEqual(s.longest.length, 9)

    def test_future_days_are_ignored(self):
        today = date(2026, 11, 5)
        days = span(date(2026, 11, 3), [1, 1, 0, 9])
        s = sc.compute_stats(days, today, date(2026, 11, 3))
        self.assertEqual((s.total, s.current.length), (2, 2))


class CalendarEdgeTests(unittest.TestCase):
    def test_streak_across_year_boundary(self):
        days = span(date(2025, 12, 28), [0, 1, 1, 1, 1, 1, 0])  # Dec 29 - Jan 2
        s = sc.compute_stats(days, date(2026, 1, 3), date(2025, 12, 28))
        self.assertEqual(s.current, sc.Streak(5, date(2025, 12, 29), date(2026, 1, 2)))
        self.assertEqual(s.longest, s.current)

    def test_leap_day_is_part_of_streak(self):
        days = span(date(2024, 2, 27), [1, 1, 1, 1, 0])  # Feb 27, 28, 29, Mar 1
        self.assertIn(date(2024, 2, 29), days)
        s = sc.compute_stats(days, date(2024, 3, 2), date(2024, 2, 27))
        self.assertEqual(s.longest, sc.Streak(4, date(2024, 2, 27), date(2024, 3, 1)))
        self.assertEqual(s.current, sc.Streak(4, date(2024, 2, 27), date(2024, 3, 1)))

    def test_leap_day_missing_breaks_streak(self):
        days = span(date(2024, 2, 27), [1, 1, 0, 1, 1])
        s = sc.compute_stats(days, date(2024, 3, 2), date(2024, 2, 27))
        self.assertEqual(s.longest, sc.Streak(2, date(2024, 3, 1), date(2024, 3, 2)))

    def test_no_contributions(self):
        days = span(date(2026, 1, 1), [0] * 30)
        s = sc.compute_stats(days, date(2026, 1, 30), date(2026, 1, 1))
        self.assertEqual((s.total, s.current, s.longest), (0, sc.Streak(), sc.Streak()))

    def test_empty_calendar_dict(self):
        s = sc.compute_stats({}, date(2026, 1, 30), date(2026, 1, 1))
        self.assertEqual((s.total, s.current.length, s.longest.length), (0, 0, 0))

    def test_longest_prefers_most_recent_on_tie(self):
        days = span(date(2026, 1, 1), [1, 1, 0, 1, 1, 0, 0])
        s = sc.compute_stats(days, date(2026, 1, 7), date(2026, 1, 1))
        self.assertEqual(s.longest.start, date(2026, 1, 4))

    def test_total_ignores_days_before_first_day(self):
        days = span(date(2026, 1, 1), [5, 1, 1])
        s = sc.compute_stats(days, date(2026, 1, 3), date(2026, 1, 2))
        self.assertEqual(s.total, 2)

    def test_rejects_negative_counts(self):
        with self.assertRaises(sc.StreakError):
            sc.compute_stats({date(2026, 1, 1): -1}, date(2026, 1, 1), date(2026, 1, 1))


class FetchHelpersTests(unittest.TestCase):
    def test_year_windows_cover_all_years_since_creation(self):
        created = datetime(2019, 3, 12, 8, 0, tzinfo=timezone.utc)
        now = datetime(2026, 11, 5, 0, 0, 30, tzinfo=timezone.utc)
        w = sc.year_windows(created, now)
        self.assertEqual([a for a, _, _ in w], [f"y{y}" for y in range(2019, 2027)])
        self.assertEqual(w[0][1], created)
        self.assertEqual(w[-1][2], now)
        for (_, _, end), (_, start, _) in zip(w, w[1:]):
            self.assertEqual(start - end, timedelta(seconds=1))  # no overlap, no gap

    def test_merge_sums_boundary_day_reported_in_two_windows(self):
        a = calendar({date(2025, 12, 31): 2, date(2026, 1, 1): 1})
        b = calendar({date(2026, 1, 1): 3, date(2026, 1, 2): 0})
        merged = sc.merge_calendars({"y2025": a, "y2026": b})
        self.assertEqual(merged[date(2026, 1, 1)], 4)

    def test_merge_rejects_total_mismatch(self):
        cal = calendar({date(2026, 1, 1): 2})
        cal["contributionCalendar"]["totalContributions"] = 5
        with self.assertRaises(sc.StreakError):
            sc.merge_calendars({"y2026": cal})

    def test_merge_rejects_malformed_and_empty(self):
        with self.assertRaises(sc.StreakError):
            sc.merge_calendars({"y2026": {"contributionCalendar": None}})
        with self.assertRaises(sc.StreakError):
            sc.merge_calendars({"y2026": calendar({})})

    def test_coverage_detects_gap(self):
        days = span(date(2026, 1, 1), [1, 1, 1])
        del days[date(2026, 1, 2)]
        with self.assertRaises(sc.StreakError):
            sc.check_coverage(days, date(2026, 1, 1), date(2026, 1, 4))
        # today missing is fine
        sc.check_coverage(span(date(2026, 1, 1), [1, 1, 1]), date(2026, 1, 1), date(2026, 1, 4))


class SvgTests(unittest.TestCase):
    def stats(self):
        days = span(date(2025, 12, 20), [1] * 10 + [0] + [3] * 4)
        return sc.compute_stats(days, date(2026, 1, 3), date(2019, 3, 12))

    def test_render_is_valid_and_self_contained(self):
        st = self.stats()
        svg = sc.render_svg(st, "Metecode")
        sc.validate_svg(svg, st, ("ghs_secret",))
        for needle in ("<script", "href", "@import", "<image", "url("):
            self.assertNotIn(needle, svg)
        for color in ("#0d1117", "#39d353", "#c9d1d9", "#8b949e"):
            self.assertIn(color, svg)
        self.assertIn('width="490"', svg)
        self.assertIn("Dec 20, 2025 – Dec 29, 2025", svg)

    def test_validate_rejects_token_leak_and_bad_markup(self):
        st = self.stats()
        svg = sc.render_svg(st, "Metecode")
        with self.assertRaises(sc.StreakError):
            sc.validate_svg(svg.replace("</svg>", "<!-- tok123 --></svg>"), st, ("tok123",))
        with self.assertRaises(sc.StreakError):
            sc.validate_svg(svg.replace("</svg>", "<script>x</script></svg>"), st)
        with self.assertRaises(sc.StreakError):
            sc.validate_svg(svg[:-20], st)

    def test_atomic_write_keeps_old_file_on_validation_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "streak.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write("OLD")

            def fail(_):
                raise sc.StreakError("bad")

            with self.assertRaises(sc.StreakError):
                sc.write_atomic(path, "NEW", fail)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "OLD")
            self.assertEqual(os.listdir(d), ["streak.svg"])  # temp file cleaned up

            sc.write_atomic(path, "NEW", lambda s: None)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "NEW")

    def test_main_end_to_end_with_mocked_api(self):
        from unittest import mock

        today = datetime.now(timezone.utc).astimezone(sc.istanbul_tz()).date()
        created = datetime(today.year - 1, 6, 1, tzinfo=timezone.utc)
        calls = []

        def fake_graphql(token, query, variables, attempts=3):
            calls.append(query)
            if "createdAt" in query:
                return {"user": {"createdAt": "%sT00:00:00Z" % created.date()}}
            prev = span(created.date(), [1] * ((date(today.year, 1, 1) - created.date()).days))
            cur = span(date(today.year, 1, 1), [0] * ((today - date(today.year, 1, 1)).days + 1))
            return {"user": {f"y{today.year - 1}": calendar(prev), f"y{today.year}": calendar(cur)}}

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"GITHUB_TOKEN": "tok-xyz"}):
            out = os.path.join(d, "streak.svg")
            with mock.patch.object(sc, "graphql", fake_graphql):
                self.assertEqual(sc.main(["--output", out]), 0)
            with open(out, encoding="utf-8") as f:
                good = f.read()
            self.assertNotIn("tok-xyz", good)
            self.assertIn(f"y{today.year - 1}:", calls[1])  # all years requested

            def broken(*a, **k):
                raise sc.StreakError("HTTP 502")

            with mock.patch.object(sc, "graphql", broken):
                self.assertEqual(sc.main(["--output", out]), 1)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(f.read(), good)  # previous SVG untouched

    def test_main_fails_without_token(self):
        old = os.environ.pop("GITHUB_TOKEN", None)
        try:
            self.assertEqual(sc.main(["--output", os.devnull]), 1)
        finally:
            if old is not None:
                os.environ["GITHUB_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
