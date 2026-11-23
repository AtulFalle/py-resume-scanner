"""Deterministic total-experience calculation.

The LLM is good at reading dates off a resume but unreliable at arithmetic,
so it only extracts the raw strings and the numbers are computed here.
"""

import re
from collections.abc import Iterable
from datetime import date

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

PRESENT_WORDS = (
    "present",
    "current",
    "currently",
    "now",
    "till date",
    "to date",
    "today",
    "ongoing",
    "continuing",
)

RANGE_SEPARATOR = re.compile(r"\s+(?:-|–|—|to|till|until)\s+|\s*[–—]\s*", re.IGNORECASE)

MONTH_NAME_YEAR = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?[\s,'’-]*(\d{4}|\d{2})\b",
    re.IGNORECASE,
)
MONTH_SLASH_YEAR = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{4})\b")
YEAR_SLASH_MONTH = re.compile(r"\b(\d{4})\s*[/.\-]\s*(\d{1,2})\b")
YEAR_ONLY = re.compile(r"\b(19[6-9]\d|20\d{2})\b")

# "5 years", "5+ yrs", "5.5 years", "8 years 6 months", "18 months"
STATED_YEARS = re.compile(
    r"(\d{1,2}(?:\.\d{1,2})?)\s*\+?\s*(?:years?|yrs?)(?:\s*(?:and\s*)?(\d{1,2})\s*(?:months?|mos?))?",
    re.IGNORECASE,
)
STATED_MONTHS_ONLY = re.compile(r"\b(\d{1,3})\s*(?:months?|mos?)\b", re.IGNORECASE)

MIN_YEAR = 1960
MAX_JOB_MONTHS = 50 * 12

# Month index = year * 12 + (month - 1)
MonthIndex = int


def _month_index(year: int, month: int) -> MonthIndex:
    return year * 12 + (month - 1)


def _normalize_year(year_text: str, today: date) -> int | None:
    year = int(year_text)

    if len(year_text) == 2:
        # '19 -> 2019, '98 -> 1998
        year += 2000 if year <= today.year % 100 else 1900

    if year < MIN_YEAR or year > today.year + 1:
        return None

    return year


def parse_resume_date(value: str | None, today: date | None = None) -> MonthIndex | None:
    """Parse a single resume date ("Jan 2019", "03/2020", "2018", "Present")."""
    if not value:
        return None

    today = today or date.today()
    text = value.strip().lower()

    if not text:
        return None

    if any(word in text for word in PRESENT_WORDS):
        return _month_index(today.year, today.month)

    if match := MONTH_NAME_YEAR.search(text):
        year = _normalize_year(match.group(2), today)
        if year is not None:
            return _month_index(year, MONTHS[match.group(1)[:3].lower()])

    if match := MONTH_SLASH_YEAR.search(text):
        month, year = int(match.group(1)), _normalize_year(match.group(2), today)
        if year is not None and 1 <= month <= 12:
            return _month_index(year, month)

    if match := YEAR_SLASH_MONTH.search(text):
        year, month = _normalize_year(match.group(1), today), int(match.group(2))
        if year is not None and 1 <= month <= 12:
            return _month_index(year, month)

    if match := YEAR_ONLY.search(text):
        year = _normalize_year(match.group(1), today)
        if year is not None:
            # Year only: assume mid-year so "2018 - 2020" counts as ~2 years.
            return _month_index(year, 6)

    return None


def _split_range(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    """Handle "Jan 2018 - Mar 2020" written entirely in start_date."""
    if start and not end:
        parts = RANGE_SEPARATOR.split(start, maxsplit=1)
        if len(parts) == 2:
            return parts[0], parts[1]
    return start, end


def compute_experience_years(
    jobs: Iterable[tuple[str | None, str | None]],
    today: date | None = None,
) -> float | None:
    """Total years across jobs, merging overlapping periods.

    Returns None when no job has parseable dates.
    """
    today = today or date.today()
    intervals: list[tuple[MonthIndex, MonthIndex]] = []

    for raw_start, raw_end in jobs:
        start_text, end_text = _split_range(raw_start, raw_end)
        start = parse_resume_date(start_text, today)
        end = parse_resume_date(end_text, today)

        if start is None or end is None:
            continue

        if end < start or end - start > MAX_JOB_MONTHS:
            continue

        # Inclusive of the end month ("Jan 2020 - Dec 2020" = 12 months).
        intervals.append((start, end + 1))

    if not intervals:
        return None

    intervals.sort()
    total_months = 0
    current_start, current_end = intervals[0]

    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total_months += current_end - current_start
            current_start, current_end = start, end

    total_months += current_end - current_start

    return round(total_months / 12, 1)


def parse_stated_experience(*texts: str | None) -> float | None:
    """Extract an explicitly stated total ("8+ years of experience")."""
    for text in texts:
        if not text:
            continue

        if match := STATED_YEARS.search(text):
            years = float(match.group(1))
            months = int(match.group(2)) if match.group(2) else 0
            if 0 < years <= 60:
                return round(years + months / 12, 1)

        if match := STATED_MONTHS_ONLY.search(text):
            months = int(match.group(1))
            if 0 < months <= 600:
                return round(months / 12, 1)

    return None


def parse_years_from_query(query: str) -> tuple[float | None, float | None]:
    """Fallback for queries: "5+ years" → (5, None), "3-5 years" → (3, 5)."""
    range_match = re.search(
        r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)",
        query,
        re.IGNORECASE,
    )
    if range_match:
        low, high = float(range_match.group(1)), float(range_match.group(2))
        if low <= high:
            return low, high

    min_match = re.search(
        r"(?:at\s+least|minimum(?:\s+of)?|min\.?|over|more\s+than)?\s*(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)",
        query,
        re.IGNORECASE,
    )
    if min_match:
        return float(min_match.group(1)), None

    return None, None
