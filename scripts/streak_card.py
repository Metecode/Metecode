"""Generate streak.svg from the GitHub contribution calendar (stdlib only).

Period covered ("all time"): every contribution-calendar day from the account
creation date up to *today*, fetched year by year via GraphQL (one
contributionsCollection window per calendar year, because GitHub limits a
window to one year).

Date semantics:
* Per-day counts are taken as GitHub reports them in contributionCalendar
  (`date` + `contributionCount`). The API exposes no per-contribution
  timestamps, so the days are never re-bucketed here.
* The query windows partition time without overlap (Jan 1 00:00:00Z ..
  Dec 31 23:59:59Z). If GitHub ever reports the same calendar date in two
  adjacent windows, the counts are summed, so nothing is double counted or lost.
* "Today" is the current date in Europe/Istanbul. Calendar days after today
  are ignored; a missing entry for today means 0 (no contribution yet).
* Current streak: if today has contributions the streak ends today; otherwise
  a streak that ended yesterday is still current; if yesterday is also empty
  the current streak is 0.

Usage:  GITHUB_TOKEN=... python scripts/streak_card.py [--user X] [--output Y]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from xml.sax.saxutils import escape

API_URL = "https://api.github.com/graphql"
DEFAULT_USER = "Metecode"
DEFAULT_OUTPUT = "streak.svg"

W, H = 490, 195
BG = "#0d1117"
BORDER = "#30363d"
ACCENT = "#39d353"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
FONT = "'Segoe UI',Ubuntu,'Helvetica Neue',Helvetica,Arial,sans-serif"


class StreakError(RuntimeError):
    """Any condition that must fail the run and keep the existing SVG."""


# --------------------------------------------------------------------------
# Time zone
# --------------------------------------------------------------------------

def istanbul_tz() -> tzinfo:
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Istanbul")
    except Exception:  # tzdata missing (e.g. bare Windows Python)
        # Turkey has been on permanent UTC+3 without DST since 2016-09-07.
        print("warning: tzdata unavailable, using fixed UTC+03:00", file=sys.stderr)
        return timezone(timedelta(hours=3), "Europe/Istanbul")


# --------------------------------------------------------------------------
# Streak computation (pure, unit tested)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Streak:
    length: int = 0
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class Stats:
    total: int
    current: Streak
    longest: Streak
    first_day: date
    today: date


def compute_stats(days: dict[date, int], today: date, first_day: date) -> Stats:
    """Compute totals/streaks over [first_day, today]. Missing days count as 0."""
    if first_day > today:
        raise StreakError(f"first day {first_day} is after today {today}")
    for d, c in days.items():
        if not isinstance(c, int) or isinstance(c, bool) or c < 0:
            raise StreakError(f"invalid contribution count for {d}: {c!r}")

    total = 0
    longest = Streak()
    run_len, run_start = 0, None
    d = first_day
    while d <= today:
        c = days.get(d, 0)
        total += c
        if c > 0:
            if run_len == 0:
                run_start = d
            run_len += 1
            # ">=" keeps the most recent streak on ties
            if run_len >= longest.length:
                longest = Streak(run_len, run_start, d)
        else:
            run_len = 0
        d += timedelta(days=1)

    if days.get(today, 0) > 0:
        anchor = today
    elif today - timedelta(days=1) >= first_day and days.get(today - timedelta(days=1), 0) > 0:
        anchor = today - timedelta(days=1)
    else:
        anchor = None

    current = Streak()
    if anchor is not None:
        start = anchor
        while start - timedelta(days=1) >= first_day and days.get(start - timedelta(days=1), 0) > 0:
            start -= timedelta(days=1)
        current = Streak((anchor - start).days + 1, start, anchor)

    return Stats(total, current, longest, first_day, today)


# --------------------------------------------------------------------------
# GitHub GraphQL
# --------------------------------------------------------------------------

def graphql(token: str, query: str, variables: dict, attempts: int = 3) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    last_err = "unknown error"
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            API_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "streak-card-generator",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
            if e.code in (400, 401, 404, 422):  # not transient, do not retry
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = f"{type(e).__name__}: {e}"
        else:
            if payload.get("errors"):
                msgs = "; ".join(str(err.get("message")) for err in payload["errors"])
                raise StreakError(f"GraphQL errors: {msgs}")
            if not isinstance(payload.get("data"), dict):
                raise StreakError("GraphQL response has no data")
            return payload["data"]
        if attempt < attempts:
            time.sleep(2 * attempt)
    raise StreakError(f"GitHub API request failed: {last_err}")


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def year_windows(created_at: datetime, now: datetime) -> list[tuple[str, datetime, datetime]]:
    """Non-overlapping one-year windows from account creation until now (UTC)."""
    if created_at > now:
        raise StreakError("account creation date is in the future")
    windows = []
    for y in range(created_at.year, now.year + 1):
        start = max(datetime(y, 1, 1, tzinfo=timezone.utc), created_at)
        end = min(datetime(y, 12, 31, 23, 59, 59, tzinfo=timezone.utc), now)
        windows.append((f"y{y}", start, end))
    return windows


def merge_calendars(collections: dict[str, dict]) -> dict[date, int]:
    """Validate each year's calendar and merge into {date: count}."""
    days: dict[date, int] = {}
    for alias, coll in collections.items():
        try:
            cal = coll["contributionCalendar"]
            total = cal["totalContributions"]
            weeks = cal["weeks"]
        except (TypeError, KeyError) as e:
            raise StreakError(f"{alias}: malformed calendar ({e})") from None
        if not isinstance(total, int) or total < 0 or not isinstance(weeks, list):
            raise StreakError(f"{alias}: malformed calendar")
        seen: set[date] = set()
        window_sum = 0
        for week in weeks:
            for day in (week or {}).get("contributionDays") or []:
                try:
                    d = date.fromisoformat(day["date"])
                    c = day["contributionCount"]
                except (TypeError, KeyError, ValueError) as e:
                    raise StreakError(f"{alias}: malformed day ({e})") from None
                if not isinstance(c, int) or isinstance(c, bool) or c < 0:
                    raise StreakError(f"{alias}: invalid count for {d}")
                if d in seen:
                    raise StreakError(f"{alias}: duplicate day {d}")
                seen.add(d)
                window_sum += c
                days[d] = days.get(d, 0) + c
        if not seen:
            raise StreakError(f"{alias}: calendar has no days")
        if window_sum != total:
            raise StreakError(
                f"{alias}: day counts ({window_sum}) != totalContributions ({total})"
            )
    return days


def check_coverage(days: dict[date, int], first_day: date, today: date) -> None:
    """Every day from first_day+1 to yesterday must be present (today may be absent)."""
    if not days:
        raise StreakError("no calendar days returned")
    d = first_day + timedelta(days=1)
    missing = []
    while d < today:
        if d not in days:
            missing.append(d)
        d += timedelta(days=1)
    if missing:
        raise StreakError(
            f"calendar is missing {len(missing)} day(s), e.g. {missing[0]}"
        )


def fetch_days(token: str, login: str, now: datetime) -> tuple[datetime, dict[date, int]]:
    data = graphql(token, "query($login:String!){user(login:$login){createdAt}}", {"login": login})
    user = data.get("user")
    if not user or not user.get("createdAt"):
        raise StreakError(f"user {login!r} not found")
    created_at = parse_dt(user["createdAt"])

    windows = year_windows(created_at, now)
    fields = "\n".join(
        f'{alias}: contributionsCollection(from:"{iso(s)}", to:"{iso(e)}")'
        "{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}"
        for alias, s, e in windows
    )
    data = graphql(token, f"query($login:String!){{user(login:$login){{{fields}}}}}", {"login": login})
    user = data.get("user")
    if not user:
        raise StreakError(f"user {login!r} not found")
    missing = [a for a, _, _ in windows if a not in user]
    if missing:
        raise StreakError(f"missing collections: {missing}")
    return created_at, merge_calendars({a: user[a] for a, _, _ in windows})


# --------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------

def fmt_date(d: date, with_year: bool) -> str:
    s = f"{d.strftime('%b')} {d.day}"
    return f"{s}, {d.year}" if with_year else s


def fmt_range(s: Streak, today: date, empty: str) -> str:
    if s.length == 0 or s.start is None or s.end is None:
        return empty
    end_year = s.end.year != today.year
    if s.start == s.end:
        return fmt_date(s.end, end_year)
    start_year = s.start.year != s.end.year or end_year
    return f"{fmt_date(s.start, start_year)} – {fmt_date(s.end, end_year)}"


def _text(x: float, y: float, content: str, fill: str, size: int,
          weight: str = "normal", max_width: int | None = None) -> str:
    fit = ""
    # rough average glyph width for the sans stack; squeeze only if needed
    if max_width and len(content) * size * 0.56 > max_width:
        fit = f' textLength="{max_width}" lengthAdjust="spacingAndGlyphs"'
    return (f'<text x="{x}" y="{y}" text-anchor="middle" fill="{fill}" '
            f'font-size="{size}" font-weight="{weight}"{fit}>{escape(content)}</text>')


def render_svg(stats: Stats, login: str) -> str:
    col = W / 3
    lx, cx, rx = round(col / 2, 1), W / 2, round(W - col / 2, 1)
    ring_y, ring_r = 76, 40
    total_range = f"{fmt_date(stats.first_day, True)} – Present"
    cur_range = fmt_range(stats.current, stats.today, "No active streak")
    long_range = fmt_range(stats.longest, stats.today, "No streak yet")
    desc = (f"GitHub contribution stats for {login} since account creation "
            f"({stats.first_day.isoformat()}): {stats.total} total contributions, "
            f"current streak {stats.current.length} days, longest streak "
            f"{stats.longest.length} days.")
    days = lambda n: f"{n:,}"  # noqa: E731

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{FONT}" role="img" aria-labelledby="t d">',
        '<title id="t">GitHub contribution streak</title>',
        f'<desc id="d">{escape(desc)}</desc>',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="8" fill="{BG}" stroke="{BORDER}"/>',
        f'<line x1="{round(col, 1)}" y1="28" x2="{round(col, 1)}" y2="167" stroke="{BORDER}"/>',
        f'<line x1="{round(2 * col, 1)}" y1="28" x2="{round(2 * col, 1)}" y2="167" stroke="{BORDER}"/>',
        # total
        _text(lx, 92, days(stats.total), TEXT, 28, "bold"),
        _text(lx, 125, "Total Contributions", MUTED, 14),
        _text(lx, 150, total_range, MUTED, 12, max_width=150),
        # current streak with ring + flame
        f'<circle cx="{cx}" cy="{ring_y}" r="{ring_r}" fill="none" stroke="{ACCENT}" stroke-width="5"/>',
        f'<circle cx="{cx}" cy="{ring_y - ring_r}" r="14" fill="{BG}"/>',
        f'<path transform="translate({cx} {ring_y - ring_r})" fill="{ACCENT}" '
        'd="M0,-13C3,-8 9,-4 9,4C9,10 5,13 0,13C-5,13 -9,10 -9,4C-9,-1 -6,-4 -4,-7'
        'C-3.5,-3.5 -2,-1.5 0,0C1.5,-4 1,-8 0,-13Z"/>',
        _text(cx, ring_y + 10, days(stats.current.length), TEXT, 28, "bold"),
        _text(cx, 145, "Current Streak", ACCENT, 14, "bold"),
        _text(cx, 168, cur_range, MUTED, 12, max_width=150),
        # longest
        _text(rx, 92, days(stats.longest.length), TEXT, 28, "bold"),
        _text(rx, 125, "Longest Streak", MUTED, 14),
        _text(rx, 150, long_range, MUTED, 12, max_width=150),
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


ALLOWED_TAGS = {"svg", "title", "desc", "rect", "line", "circle", "path", "text"}


def validate_svg(svg: str, stats: Stats, forbidden: tuple[str, ...] = ()) -> None:
    for secret in forbidden:
        if secret and secret in svg:
            raise StreakError("generated SVG contains a forbidden value")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        raise StreakError(f"generated SVG is not valid XML: {e}") from None
    ns = "{http://www.w3.org/2000/svg}"
    if root.tag != f"{ns}svg" or root.get("width") != str(W):
        raise StreakError("generated SVG has an unexpected root element")
    texts = []
    for el in root.iter():
        tag = el.tag.removeprefix(ns)
        if tag not in ALLOWED_TAGS:
            raise StreakError(f"disallowed SVG element: {tag}")
        for name, value in el.attrib.items():
            if "href" in name or name.lower().startswith("on") or "url(" in value:
                raise StreakError(f"disallowed SVG attribute: {name}")
        if tag == "text":
            texts.append(el.text or "")
    for expected in (f"{stats.total:,}", f"{stats.current.length:,}", f"{stats.longest.length:,}"):
        if expected not in texts:
            raise StreakError(f"generated SVG lacks value {expected}")


def write_atomic(path: str, content: str, validate) -> None:
    """Write to a temp file next to `path`, validate it, then os.replace()."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".streak-", suffix=".svg.tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, encoding="utf-8") as f:
            validate(f.read())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--user", default=os.environ.get("STREAK_USER") or DEFAULT_USER)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    args = ap.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("error: GITHUB_TOKEN is not set", file=sys.stderr)
        return 1

    try:
        tz = istanbul_tz()
        now = datetime.now(timezone.utc)
        today = now.astimezone(tz).date()
        created_at, days = fetch_days(token, args.user, now)
        # Windows start at createdAt, so nothing earlier is returned; GitHub's
        # day bucket for the first hours may still be the previous date.
        first_day = min(min(days), created_at.astimezone(tz).date())
        check_coverage(days, first_day, today)
        stats = compute_stats({d: c for d, c in days.items() if d <= today}, today, first_day)
        if stats.longest.length < stats.current.length:
            raise StreakError("inconsistent stats: longest < current")
        svg = render_svg(stats, args.user)
        write_atomic(args.output, svg, lambda s: validate_svg(s, stats, (token,)))
    except StreakError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"user={args.user} period={first_day}..{today} (Europe/Istanbul) "
          f"total={stats.total} current={stats.current.length} "
          f"longest={stats.longest.length} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
