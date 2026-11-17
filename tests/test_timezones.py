"""Focused tests for backend timezone normalization, resolution, catalog, and validation."""

import datetime
import zoneinfo

import pytest

from backend.timezones import (
    TZDATA_VERSION,
    get_timezone_catalog,
    normalize_timezone,
    resolve_timezone,
)
from backend.travel import TripCreate


class TestNormalizeTimezone:
    def test_valid_iana_identifiers(self):
        assert normalize_timezone("Asia/Taipei") == "Asia/Taipei"
        assert normalize_timezone("America/New_York") == "America/New_York"
        assert normalize_timezone("Europe/London") == "Europe/London"
        assert normalize_timezone("UTC") == "UTC"

    def test_case_insensitive_iana(self):
        assert normalize_timezone("asia/taipei") == "Asia/Taipei"
        assert normalize_timezone("europe/paris") == "Europe/Paris"
        assert normalize_timezone("utc") == "UTC"

    def test_fixed_utc_offsets_positive(self):
        assert normalize_timezone("UTC+8") == "UTC+08:00"
        assert normalize_timezone("UTC+08:00") == "UTC+08:00"
        assert normalize_timezone("+08:00") == "UTC+08:00"
        assert normalize_timezone("+8") == "UTC+08:00"
        assert normalize_timezone("UTC+5:30") == "UTC+05:30"
        assert normalize_timezone("UTC+14") == "UTC+14:00"
        assert normalize_timezone("UTC+14:00") == "UTC+14:00"

    def test_fixed_utc_offsets_negative(self):
        assert normalize_timezone("UTC-3:30") == "UTC-03:30"
        assert normalize_timezone("UTC-03:30") == "UTC-03:30"
        assert normalize_timezone("-05:00") == "UTC-05:00"
        assert normalize_timezone("-5") == "UTC-05:00"
        assert normalize_timezone("UTC-12") == "UTC-12:00"
        assert normalize_timezone("UTC-12:00") == "UTC-12:00"

    def test_fixed_utc_offset_zero(self):
        assert normalize_timezone("UTC+0") == "UTC+00:00"
        assert normalize_timezone("UTC-0") == "UTC+00:00"
        assert normalize_timezone("UTC+00:00") == "UTC+00:00"

    def test_bounded_utc_limits_rejected(self):
        # Exceeding UTC+14:00
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("UTC+15")
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("UTC+14:01")

        # Exceeding UTC-12:00
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("UTC-13")
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("UTC-12:01")

    def test_invalid_minutes_rejected(self):
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("UTC+1:60")
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("UTC-5:99")

    def test_invalid_identifiers_rejected(self):
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("Mars/Phobos")
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("")
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone("   ")
        with pytest.raises(ValueError, match="無效的時區"):
            normalize_timezone(123)  # type: ignore


class TestResolveTimezone:
    def test_resolve_iana(self):
        tz = resolve_timezone("Asia/Taipei")
        assert isinstance(tz, zoneinfo.ZoneInfo)
        assert tz.key == "Asia/Taipei"

    def test_resolve_utc(self):
        tz = resolve_timezone("UTC")
        assert isinstance(tz, (zoneinfo.ZoneInfo, datetime.timezone))
        dt = datetime.datetime.now(tz)
        assert dt.tzinfo is not None

    def test_resolve_fixed_offset(self):
        tz = resolve_timezone("UTC+8")
        assert isinstance(tz, datetime.timezone)
        dt = datetime.datetime.now(tz)
        assert dt.utcoffset() == datetime.timedelta(hours=8)

        tz_neg = resolve_timezone("UTC-03:30")
        assert isinstance(tz_neg, datetime.timezone)
        dt_neg = datetime.datetime.now(tz_neg)
        assert dt_neg.utcoffset() == datetime.timedelta(hours=-3, minutes=-30)


class TestCatalogAndProvenance:
    def test_provenance_version(self):
        assert TZDATA_VERSION == "2026.6"

    def test_catalog_structure(self):
        catalog = get_timezone_catalog()
        assert len(catalog) >= 418

        # Has UTC
        utc_entry = next((e for e in catalog if e["zone"] == "UTC"), None)
        assert utc_entry is not None

        # Has Taipei
        taipei_entry = next((e for e in catalog if e["zone"] == "Asia/Taipei"), None)
        assert taipei_entry is not None
        assert taipei_entry["country"] == "TW"


class TestTravelValidatorIntegration:
    def test_trip_create_iana_timezone(self):
        trip = TripCreate(
            name="Tokyo Trip",
            start_date="2026-05-01",
            end_date="2026-05-05",
            timezone="Asia/Tokyo",
            description="",
        )
        assert trip.timezone == "Asia/Tokyo"

    def test_trip_create_canonicalizes_fixed_utc(self):
        trip = TripCreate(
            name="Taiwan Trip",
            start_date="2026-05-01",
            end_date="2026-05-05",
            timezone="UTC+8",
            description="",
        )
        assert trip.timezone == "UTC+08:00"

        trip_half = TripCreate(
            name="Newfoundland Trip",
            start_date="2026-05-01",
            end_date="2026-05-05",
            timezone="UTC-3:30",
            description="",
        )
        assert trip_half.timezone == "UTC-03:30"

    def test_trip_create_rejects_invalid_timezone(self):
        with pytest.raises(ValueError, match="無效的時區"):
            TripCreate(
                name="Bad Zone Trip",
                start_date="2026-05-01",
                end_date="2026-05-05",
                timezone="Invalid/Timezone",
                description="",
            )

        with pytest.raises(ValueError, match="無效的時區"):
            TripCreate(
                name="Out of Bounds Trip",
                start_date="2026-05-01",
                end_date="2026-05-05",
                timezone="UTC+15",
                description="",
            )
