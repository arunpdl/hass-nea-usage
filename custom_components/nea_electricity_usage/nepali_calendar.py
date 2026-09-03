"""Best-effort Bikram Sambat (Nepali calendar) month -> Gregorian mapping.

NEA reports months as "Falgun/2082" etc. Nepali New Year (1 Baisakh) falls
around mid-April and drifts by a day or so year to year, so this maps at
MONTH granularity only (+/- roughly two weeks) - good enough to place a
month on a chart's time axis in the right place relative to its neighbours,
not a precise day-level Bikram Sambat <-> Gregorian converter.
"""
from datetime import datetime, timezone

NEPALI_MONTHS_ORDER = [
    "Baisakh", "Jestha", "Ashad", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
]


def bs_month_to_gregorian_start(month_label: str) -> datetime | None:
    """Convert a "Month/BSYear" label to the 1st of the matching Gregorian
    month (UTC midnight). Returns None if the label can't be parsed.
    """
    name, sep, year_str = month_label.partition("/")
    if not sep:
        return None

    try:
        bs_year = int(year_str)
        index = NEPALI_MONTHS_ORDER.index(name) + 1  # Baisakh=1 .. Chaitra=12
    except (ValueError, IndexError):
        return None

    # Baisakh (index 1) starts ~mid-April, i.e. Gregorian month 4, in the
    # Gregorian year that is (BS year - 57). Each later Nepali month shifts
    # one Gregorian month later, rolling into (BS year - 56) once past
    # December.
    raw_month = index + 3
    if raw_month <= 12:
        ad_month, ad_year = raw_month, bs_year - 57
    else:
        ad_month, ad_year = raw_month - 12, bs_year - 56

    return datetime(ad_year, ad_month, 1, tzinfo=timezone.utc)


def _demo() -> None:
    """Minimal self-check - run directly with `python3 nepali_calendar.py`."""
    # Known real anchor: BS 2082 New Year (1 Baisakh 2082) fell on 2025-04-14.
    assert bs_month_to_gregorian_start("Baisakh/2082") == datetime(2025, 4, 1, tzinfo=timezone.utc)
    assert bs_month_to_gregorian_start("Chaitra/2082") == datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert bs_month_to_gregorian_start("Falgun/2082") == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert bs_month_to_gregorian_start("Shrawan/2083") == datetime(2026, 7, 1, tzinfo=timezone.utc)
    assert bs_month_to_gregorian_start("NotAMonth/2082") is None
    assert bs_month_to_gregorian_start("no-slash") is None
    print("nepali_calendar: OK")


if __name__ == "__main__":
    _demo()
