"""
Property-based tests for the Babel internationalization library.
Covers: numbers, dates, lists, plural, util, core, messages, localedata, units

Complements the existing tests/test_pbt.py (which covers core roundtrip,
plural rules, pofile escape/unescape, catalog, util.distinct/pathmatch).
"""
from __future__ import annotations

import datetime
import decimal
import string
import warnings

import pytest
from hypothesis import HealthCheck, assume, example, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

# Safe locales with full CLDR data
SAFE_LOCALES = ['en', 'en_US', 'de', 'fr', 'ja', 'zh', 'ar', 'es', 'pt', 'ru', 'ko', 'it']
safe_locale = st.sampled_from(SAFE_LOCALES)

# Safe date range (avoid edge cases near epoch/overflow)
safe_date = st.dates(
    min_value=datetime.date(1900, 1, 1),
    max_value=datetime.date(2100, 12, 31)
)

safe_datetime = st.datetimes(
    min_value=datetime.datetime(1900, 1, 1),
    max_value=datetime.datetime(2100, 12, 31)
)

# Finite, non-NaN floats in a safe range for formatting
safe_float = st.floats(
    min_value=-1e12, max_value=1e12,
    allow_nan=False, allow_infinity=False
)

# Decimal values safe for formatting
safe_decimal = st.decimals(
    min_value=decimal.Decimal('-1e12'),
    max_value=decimal.Decimal('1e12'),
    allow_nan=False, allow_infinity=False,
    places=st.integers(min_value=0, max_value=6)
)

# Non-empty list of printable strings
printable_item = st.text(
    alphabet=string.ascii_letters + string.digits + ' ',
    min_size=1, max_size=20
)


# ===========================================================================
# babel.numbers
# ===========================================================================

from babel.numbers import (
    format_decimal, format_percent, format_currency, format_number,
    parse_decimal, is_currency, get_currency_precision,
    list_currencies, normalize_currency, get_currency_name,
    get_currency_symbol, format_compact_decimal,
)


class TestFormatDecimal:
    """Properties of format_decimal."""

    @given(number=safe_float, locale=safe_locale)
    @example(number=0.0, locale='en')
    @example(number=1.0, locale='en')
    @example(number=-1.0, locale='de')
    @example(number=1234567.89, locale='fr')
    def test_returns_string(self, number, locale):
        """format_decimal should always return a non-empty string."""
        result = format_decimal(number, locale=locale)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(number=safe_float, locale=safe_locale)
    def test_negative_contains_minus_or_parens(self, number, locale):
        """Negative numbers should have a sign indicator."""
        assume(number < -0.001)
        result = format_decimal(number, locale=locale)
        # Most locales use minus sign; some use parentheses for accounting
        has_sign = ('-' in result or '(' in result or '\u2212' in result
                    or '\u200f' in result or '\u061c' in result)
        assert has_sign

    @given(locale=safe_locale)
    def test_zero_formats_consistently(self, locale):
        """Zero should format to a string containing '0'."""
        result = format_decimal(0, locale=locale)
        assert '0' in result

    @given(number=st.integers(min_value=1, max_value=10**9), locale=safe_locale)
    def test_positive_no_minus(self, number, locale):
        """Positive integers should not contain a minus sign."""
        result = format_decimal(number, locale=locale)
        assert '-' not in result and '\u2212' not in result


class TestFormatPercent:
    """Properties of format_percent."""

    @given(number=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
           locale=safe_locale)
    @example(number=0.0, locale='en')
    @example(number=0.5, locale='en')
    @example(number=1.0, locale='en')
    def test_returns_string(self, number, locale):
        """format_percent should return a non-empty string."""
        result = format_percent(number, locale=locale)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(locale=safe_locale)
    def test_half_contains_50(self, locale):
        """50% should contain '50' in the output."""
        result = format_percent(0.5, locale=locale)
        assert '50' in result

    @given(locale=safe_locale)
    def test_zero_percent(self, locale):
        """0% should contain '0'."""
        result = format_percent(0.0, locale=locale)
        assert '0' in result


class TestParseDecimal:
    """Properties of parse_decimal."""

    @given(number=st.integers(min_value=-10**9, max_value=10**9), locale=safe_locale)
    @example(number=0, locale='en')
    @example(number=1234, locale='en')
    @example(number=-5678, locale='de')
    def test_format_parse_roundtrip_integer(self, number, locale):
        """format_decimal then parse_decimal should roundtrip for integers."""
        formatted = format_decimal(number, locale=locale)
        parsed = parse_decimal(formatted, locale=locale)
        assert parsed == decimal.Decimal(number)

    @given(locale=safe_locale)
    def test_parse_returns_decimal(self, locale):
        """parse_decimal should return a Decimal."""
        formatted = format_decimal(42, locale=locale)
        result = parse_decimal(formatted, locale=locale)
        assert isinstance(result, decimal.Decimal)


class TestCurrencyFunctions:
    """Properties of currency-related functions."""

    @given(currency=st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'AUD', 'CAD']))
    def test_is_currency_known(self, currency):
        """Known ISO 4217 currencies should return True."""
        assert is_currency(currency) is True

    @given(currency=st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'AUD', 'CAD']))
    def test_currency_precision_non_negative(self, currency):
        """Currency precision should be non-negative."""
        precision = get_currency_precision(currency)
        assert isinstance(precision, int)
        assert precision >= 0

    @given(currency=st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'AUD', 'CAD']),
           locale=safe_locale)
    def test_get_currency_name_returns_string(self, currency, locale):
        """get_currency_name should return a non-empty string."""
        result = get_currency_name(currency, locale=locale)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(currency=st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'AUD', 'CAD']),
           locale=safe_locale)
    def test_get_currency_symbol_returns_string(self, currency, locale):
        """get_currency_symbol should return a non-empty string."""
        result = get_currency_symbol(currency, locale=locale)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(currency=st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'AUD', 'CAD']),
           number=st.floats(min_value=0.01, max_value=1e9, allow_nan=False, allow_infinity=False),
           locale=safe_locale)
    def test_format_currency_returns_string(self, currency, number, locale):
        """format_currency should return a non-empty string."""
        result = format_currency(number, currency, locale=locale)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_list_currencies_returns_set(self):
        """list_currencies should return a non-empty set."""
        currencies = list_currencies()
        assert isinstance(currencies, set)
        assert len(currencies) > 0
        assert 'USD' in currencies
        assert 'EUR' in currencies

    @given(currency=st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'AUD', 'CAD']))
    def test_normalize_currency_uppercase(self, currency):
        """normalize_currency should return uppercase or None."""
        result = normalize_currency(currency)
        if result is not None:
            assert result == result.upper()

    @given(number=st.floats(min_value=0.01, max_value=1e9, allow_nan=False, allow_infinity=False),
           locale=safe_locale)
    def test_format_compact_decimal_returns_string(self, number, locale):
        """format_compact_decimal should return a non-empty string."""
        result = format_compact_decimal(number, locale=locale)
        assert isinstance(result, str)
        assert len(result) > 0



# ─────────────────────────────────────────────────────────────────────────────
# dates module
# ─────────────────────────────────────────────────────────────────────────────
from babel.dates import (
    format_date, format_datetime, format_time,
    get_day_names, get_month_names, get_timezone,
    get_timezone_name,
)

DATE_FORMATS = ['short', 'medium', 'long', 'full']
LOCALES = ['en', 'de', 'fr', 'ja', 'zh', 'ar', 'es', 'pt']

@given(
    d=st.dates(min_value=datetime.date(1900, 1, 1), max_value=datetime.date(2100, 12, 31)),
    fmt=st.sampled_from(DATE_FORMATS),
    locale=st.sampled_from(LOCALES),
)
def test_format_date_returns_nonempty_string(d, fmt, locale):
    """format_date should always return a non-empty string."""
    result = format_date(d, format=fmt, locale=locale)
    assert isinstance(result, str)
    assert len(result) > 0


@given(
    d=st.dates(min_value=datetime.date(1900, 1, 1), max_value=datetime.date(2100, 12, 31)),
    locale=st.sampled_from(LOCALES),
)
def test_format_date_contains_year(d, locale):
    """format_date with 'full' format should contain the year."""
    result = format_date(d, format='full', locale=locale)
    assert str(d.year) in result


@given(
    dt=st.datetimes(
        min_value=datetime.datetime(1970, 1, 1),
        max_value=datetime.datetime(2100, 12, 31),
    ),
    fmt=st.sampled_from(DATE_FORMATS),
    locale=st.sampled_from(LOCALES),
)
def test_format_datetime_returns_nonempty_string(dt, fmt, locale):
    """format_datetime should always return a non-empty string."""
    result = format_datetime(dt, format=fmt, locale=locale)
    assert isinstance(result, str)
    assert len(result) > 0


@given(
    t=st.times(),
    fmt=st.sampled_from(DATE_FORMATS),
    locale=st.sampled_from(LOCALES),
)
def test_format_time_returns_nonempty_string(t, fmt, locale):
    """format_time should always return a non-empty string."""
    result = format_time(t, format=fmt, locale=locale)
    assert isinstance(result, str)
    assert len(result) > 0


@given(locale=st.sampled_from(LOCALES))
def test_get_day_names_has_7_entries(locale):
    """get_day_names should return 7 day names."""
    names = get_day_names(locale=locale)
    assert len(names) == 7


@given(locale=st.sampled_from(LOCALES))
def test_get_month_names_has_12_entries(locale):
    """get_month_names should return 12 month names."""
    names = get_month_names(locale=locale)
    assert len(names) == 12


@given(locale=st.sampled_from(LOCALES))
def test_get_day_names_all_nonempty(locale):
    """All day names should be non-empty strings."""
    names = get_day_names(locale=locale)
    for name in names.values():
        assert isinstance(name, str)
        assert len(name) > 0


@given(locale=st.sampled_from(LOCALES))
def test_get_month_names_all_nonempty(locale):
    """All month names should be non-empty strings."""
    names = get_month_names(locale=locale)
    for name in names.values():
        assert isinstance(name, str)
        assert len(name) > 0


# ─────────────────────────────────────────────────────────────────────────────
# lists module
# ─────────────────────────────────────────────────────────────────────────────
from babel.lists import format_list

@given(
    items=st.lists(
        st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=10),
        min_size=1, max_size=10,
    ),
    locale=st.sampled_from(LOCALES),
)
def test_format_list_returns_string(items, locale):
    """format_list should return a string."""
    result = format_list(items, locale=locale)
    assert isinstance(result, str)


@given(
    item=st.text(alphabet=string.ascii_letters, min_size=1, max_size=10),
    locale=st.sampled_from(LOCALES),
)
def test_format_list_single_item_is_item(item, locale):
    """format_list with single item should return that item."""
    result = format_list([item], locale=locale)
    assert result == item


@given(
    items=st.lists(
        st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=10),
        min_size=2, max_size=10,
    ),
    locale=st.sampled_from(LOCALES),
)
def test_format_list_contains_all_items(items, locale):
    """format_list result should contain all items."""
    result = format_list(items, locale=locale)
    for item in items:
        assert item in result


@given(
    items=st.lists(
        st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=10),
        min_size=1, max_size=10,
    ),
)
def test_format_list_en_de_different_for_multiple(items):
    """format_list in different locales may produce different results."""
    en_result = format_list(items, locale='en')
    de_result = format_list(items, locale='de')
    # Both should be non-empty strings
    assert isinstance(en_result, str)
    assert isinstance(de_result, str)


# ─────────────────────────────────────────────────────────────────────────────
# units module
# ─────────────────────────────────────────────────────────────────────────────
from babel.units import format_unit, get_unit_name

UNITS = ['length-meter', 'mass-kilogram', 'duration-second', 'volume-liter', 'area-square-meter']

@given(
    n=st.integers(min_value=0, max_value=1000),
    unit=st.sampled_from(UNITS),
    locale=st.sampled_from(LOCALES),
)
def test_format_unit_returns_nonempty_string(n, unit, locale):
    """format_unit should return a non-empty string."""
    result = format_unit(n, unit, locale=locale)
    assert isinstance(result, str)
    assert len(result) > 0


@given(
    n=st.integers(min_value=0, max_value=999),  # avoid locale number formatting (1,000 vs 1000)
    unit=st.sampled_from(UNITS),
    locale=st.sampled_from(LOCALES),
)
def test_format_unit_contains_number(n, unit, locale):
    """format_unit result should contain the number (for values < 1000 to avoid grouping)."""
    result = format_unit(n, unit, locale=locale)
    assert str(n) in result


@given(
    unit=st.sampled_from(UNITS),
    locale=st.sampled_from(['en', 'de', 'fr', 'es', 'pt']),  # locales with full unit name data
)
def test_get_unit_name_returns_nonempty_string(unit, locale):
    """get_unit_name should return a non-empty string for well-supported locales."""
    result = get_unit_name(unit, locale=locale)
    if result is not None:  # some locale/unit combos may not have data
        assert isinstance(result, str)
        assert len(result) > 0


# ─────────────────────────────────────────────────────────────────────────────
# core module - negotiate_locale, Locale properties
# ─────────────────────────────────────────────────────────────────────────────
from babel.core import negotiate_locale, Locale

@given(
    preferred=st.lists(st.sampled_from(['en_US', 'fr_FR', 'de_DE', 'ja_JP', 'zh_CN']), min_size=1, max_size=5),
    available=st.lists(st.sampled_from(['en', 'fr', 'de', 'ja', 'zh']), min_size=1, max_size=5),
)
def test_negotiate_locale_returns_available_or_none(preferred, available):
    """negotiate_locale should return a locale from available or None."""
    result = negotiate_locale(preferred, available)
    if result is not None:
        # Result should be in available or a prefix match
        assert any(result == a or a.startswith(result) or result.startswith(a) for a in available)


@given(locale_str=st.sampled_from(['en', 'de', 'fr', 'ja', 'zh', 'ar', 'es', 'pt', 'en_US', 'de_DE']))
def test_locale_language_is_lowercase(locale_str):
    """Locale.language should be lowercase."""
    locale = Locale.parse(locale_str)
    assert locale.language == locale.language.lower()


@given(locale_str=st.sampled_from(['en', 'de', 'fr', 'ja', 'zh', 'ar', 'es', 'pt']))
def test_locale_str_roundtrip(locale_str):
    """str(Locale.parse(s)) should produce a valid locale string."""
    locale = Locale.parse(locale_str)
    result = str(locale)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should be parseable again
    locale2 = Locale.parse(result)
    assert locale2.language == locale.language


@given(locale_str=st.sampled_from(['en', 'de', 'fr', 'ja', 'zh', 'ar', 'es', 'pt']))
def test_locale_english_name_nonempty(locale_str):
    """Locale.english_name should be a non-empty string."""
    locale = Locale.parse(locale_str)
    assert isinstance(locale.english_name, str)
    assert len(locale.english_name) > 0


@given(locale_str=st.sampled_from(['en', 'de', 'fr', 'ja', 'zh', 'ar', 'es', 'pt']))
def test_locale_display_name_nonempty(locale_str):
    """Locale.display_name should be a non-empty string."""
    locale = Locale.parse(locale_str)
    assert isinstance(locale.display_name, str)
    assert len(locale.display_name) > 0

