"""Timezone utilities and catalog support for TravelMemo.

Provenance: Generated from project deployed tzdata (version 2026.6, locked in requirements.lock.txt)
via importlib.resources tzdata.zoneinfo/zone.tab.
Provides fixed UTC offset canonicalization, bounds checking (-12:00 to +14:00),
IANA zoneinfo identifier validation, and timezone object resolution.
"""

import datetime
import importlib.resources
import re
import zoneinfo
from typing import Any

import tzdata

TZDATA_VERSION = tzdata.__version__

TZDATA_SOURCE = "tzdata.zoneinfo/zone.tab"

# Pattern for fixed UTC offsets: e.g. UTC+8, UTC-03:30, +08:00, -5, UTC+14
_FIXED_UTC_PATTERN = re.compile(
    r"^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE
)

# Cached available timezones
_AVAILABLE_TIMEZONES = zoneinfo.available_timezones()
_LOWER_TIMEZONE_MAP = {tz.lower(): tz for tz in _AVAILABLE_TIMEZONES}


def normalize_timezone(value: str) -> str:
    """Normalize and validate a timezone string.

    Supports:
    - Standard IANA identifiers (e.g. 'Asia/Taipei', 'Europe/London')
    - Case-insensitive matching for valid IANA identifiers
    - Plain 'UTC'
    - Fixed UTC offsets bounded to real-world range UTC-12:00 to UTC+14:00
      (e.g. 'UTC+8' -> 'UTC+08:00', 'UTC-03:30' -> 'UTC-03:30', '+08:00' -> 'UTC+08:00')

    Raises:
        ValueError: If timezone is invalid or out of bounded range.
    """
    if not isinstance(value, str):
        raise ValueError(f"無效的時區: {value}")  # noqa: TRY004 - Pydantic validator uses ValueError

    val = value.strip()
    if not val:
        raise ValueError(f"無效的時區: {value}")

    # Special check for plain UTC / GMT
    if val.upper() in ("UTC", "GMT", "ETC/UTC", "ETC/GMT"):
        return "UTC"

    # Fixed UTC offset check
    utc_match = _FIXED_UTC_PATTERN.match(val)
    if utc_match:
        sign, hours_str, minutes_str = utc_match.groups()
        hours = int(hours_str)
        minutes = int(minutes_str) if minutes_str is not None else 0

        if not (0 <= minutes <= 59):
            raise ValueError(f"無效的時區: {value}")

        total_minutes = (hours * 60 + minutes) * (-1 if sign == "-" else 1)
        # Bounded real-world range: UTC-12:00 to UTC+14:00 (-720 to 840 minutes)
        if not (-720 <= total_minutes <= 840):
            raise ValueError(f"無效的時區: {value}")

        if total_minutes == 0:
            return "UTC+00:00"

        return f"UTC{sign}{hours:02d}:{minutes:02d}"

    # Check case-insensitively in available zoneinfo
    canonical = _LOWER_TIMEZONE_MAP.get(val.lower())
    if canonical:
        try:
            zoneinfo.ZoneInfo(canonical)
            return canonical
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            pass

    # Direct ZoneInfo check
    try:
        zi = zoneinfo.ZoneInfo(val)
        return zi.key or val
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"無效的時區: {value}") from None


def resolve_timezone(value: str) -> zoneinfo.ZoneInfo | datetime.timezone:
    """Resolve a timezone string to a ZoneInfo or datetime.timezone instance.

    Raises:
        ValueError: If the timezone cannot be normalized or resolved.
    """
    normalized = normalize_timezone(value)

    if normalized == "UTC":
        return zoneinfo.ZoneInfo("UTC")

    utc_match = _FIXED_UTC_PATTERN.match(normalized)
    if utc_match:
        sign, hours_str, minutes_str = utc_match.groups()
        hours = int(hours_str)
        minutes = int(minutes_str) if minutes_str is not None else 0
        delta = datetime.timedelta(hours=hours, minutes=minutes)
        if sign == "-":
            delta = -delta
        return datetime.timezone(delta, name=normalized)

    return zoneinfo.ZoneInfo(normalized)


def get_timezone_catalog() -> list[dict[str, Any]]:
    """Return catalog of timezones generated from tzdata zone.tab."""
    try:
        lines = (
            importlib.resources.files("tzdata.zoneinfo")
            .joinpath("zone.tab")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    except (ImportError, FileNotFoundError):
        # Fallback if tzdata resource is unavailable
        return [{"zone": "UTC", "country": "", "coordinates": "+0000+00000", "comments": "Coordinated Universal Time"}]

    catalog: list[dict[str, Any]] = [
        {
            "zone": "UTC",
            "country": "",
            "coordinates": "+0000+00000",
            "comments": "Coordinated Universal Time",
        }
    ]

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        country = parts[0]
        coords = parts[1]
        zone = parts[2]
        comment = parts[3] if len(parts) > 3 else ""
        catalog.append(
            {
                "zone": zone,
                "country": country,
                "coordinates": coords,
                "comments": comment,
            }
        )

    return catalog
