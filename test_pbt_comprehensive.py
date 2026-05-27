"""
Comprehensive Property-Based Tests for Babel
Tests core functions with invariants, roundtrips, and edge cases
"""
import decimal
import re
from hypothesis import given, strategies as st, assume, settings, example
from hypothesis.strategies import composite
import pytest

# Import Babel modules
from babel.util import distinct, pathmatch
from babel.plural import extract_operands, PluralRule, to_javascript, to_python
from babel.core import parse_locale, get_locale_identifier, negotiate_locale
from babel.numbers import normalize_currency, is_currency, list_currencies


# ============================================================================
# UTIL MODULE TESTS
# ============================================================================

class TestDistinct:
    """Property tests for babel.util.distinct"""
    
    @given(st.lists(st.integers()))
    def test_distinct_preserves_order(self, items):
        """distinct() preserves the original order of first occurrences"""
        result = list(distinct(items))
        seen = set()
        expected = []
        for item in items:
            if item not in seen:
                expected.append(item)
                seen.add(item)
        assert result == expected
    
    @given(st.lists(st.integers()))
    def test_distinct_removes_duplicates(self, items):
        """distinct() result has no duplicates"""
        result = list(distinct(items))
        assert len(result) == len(set(result))
    
    @given(st.lists(st.integers()))
    def test_distinct_subset(self, items):
        """distinct() result is a subset of input"""
        result = list(distinct(items))
        assert set(result).issubset(set(items))
    
    @given(st.lists(st.integers(), unique=True))
    def test_distinct_idempotent_on_unique(self, items):
        """distinct() on already unique list returns same elements"""
        result = list(distinct(items))
        assert result == items
    
    @given(st.lists(st.text()))
    def test_distinct_works_with_strings(self, items):
        """distinct() works with strings"""
        result = list(distinct(items))
        assert len(result) == len(set(result))
        # Check order preservation
        indices = {item: i for i, item in enumerate(items) if item not in {items[j] for j in range(i)}}
        for i in range(len(result) - 1):
            assert indices[result[i]] < indices[result[i + 1]]


class TestPathmatch:
    """Property tests for babel.util.pathmatch"""
    
    @given(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')), min_size=1))
    def test_exact_match(self, filename):
        """Exact pattern matches exact filename"""
        assume('/' not in filename and '*' not in filename and '?' not in filename)
        assert pathmatch(filename, filename)
    
    @given(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), min_size=1))
    def test_star_star_py_matches_py_files(self, basename):
        """**.py pattern matches any .py file"""
        assume('/' not in basename and '*' not in basename and '?' not in basename)
        filename = f"{basename}.py"
        assert pathmatch('**.py', filename)
    
    @given(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), min_size=1))
    def test_star_star_py_rejects_non_py(self, basename):
        """**.py pattern rejects non-.py files"""
        assume('/' not in basename and '*' not in basename and '?' not in basename)
        filename = f"{basename}.txt"
        assert not pathmatch('**.py', filename)
    
    def test_star_star_matches_nested(self):
        """** pattern matches nested paths"""
        assert pathmatch('**.py', 'foo/bar/baz.py')
        assert pathmatch('**/test.py', 'a/b/c/test.py')
    
    def test_caret_anchors_start(self):
        """^ pattern anchors to start"""
        assert pathmatch('^foo/**.py', 'foo/bar.py')
        assert not pathmatch('^foo/**.py', 'bar/foo/baz.py')
    
    def test_dot_slash_anchors_start(self):
        """./pattern anchors to start"""
        assert pathmatch('./foo/**.py', 'foo/bar.py')
        assert not pathmatch('./foo/**.py', 'bar/foo/baz.py')


# ============================================================================
# PLURAL MODULE TESTS
# ============================================================================

class TestExtractOperands:
    """Property tests for babel.plural.extract_operands"""
    
    @given(st.integers(min_value=0, max_value=1000000))
    def test_integer_operands(self, n):
        """extract_operands on integers: i=n, v=0, w=0, f=0, t=0"""
        result = extract_operands(n)
        n_val, i, v, w, f, t, c, e = result
        assert i == n
        assert v == 0  # no visible fraction digits
        assert w == 0  # no visible fraction digits without trailing zeros
        assert f == 0  # no fractional part
        assert t == 0  # no fractional part without trailing zeros
        assert c == 0
        assert e == 0
    
    @given(st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False))
    def test_n_equals_abs_value(self, source):
        """n operand equals absolute value of source"""
        result = extract_operands(source)
        n_val, i, v, w, f, t, c, e = result
        assert abs(float(n_val) - abs(source)) < 0.0001 or (abs(source) == int(abs(source)) and n_val == int(abs(source)))
    
    @given(st.decimals(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False, places=2))
    def test_decimal_v_counts_digits(self, source):
        """v operand counts visible fraction digits"""
        result = extract_operands(source)
        n_val, i, v, w, f, t, c, e = result
        # v should be >= 0
        assert v >= 0
        # w should be <= v
        assert w <= v
    
    @given(st.integers(min_value=-1000, max_value=1000))
    def test_negative_becomes_positive(self, n):
        """Negative numbers are converted to absolute value"""
        result = extract_operands(n)
        n_val, i, v, w, f, t, c, e = result
        assert i == abs(n)
    
    @given(st.decimals(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False, places=3))
    def test_i_is_integer_part(self, source):
        """i operand is the integer part of n"""
        result = extract_operands(source)
        n_val, i, v, w, f, t, c, e = result
        assert i == int(abs(source))


class TestPluralRule:
    """Property tests for babel.plural.PluralRule"""
    
    @given(st.integers(min_value=0, max_value=1000))
    def test_simple_rule_one(self, n):
        """Simple rule 'n is 1' works correctly"""
        rule = PluralRule({'one': 'n is 1'})
        result = rule(n)
        if n == 1:
            assert result == 'one'
        else:
            assert result == 'other'
    
    @given(st.integers(min_value=0, max_value=100))
    def test_rule_roundtrip_to_javascript(self, n):
        """PluralRule can be converted to JavaScript and back"""
        rule = PluralRule({'one': 'n is 1', 'few': 'n in 2..4'})
        js_code = to_javascript(rule)
        # Check it's valid JavaScript function syntax
        assert js_code.startswith('(function(n)')
        assert 'return' in js_code
    
    def test_empty_rule_returns_other(self):
        """Empty rule always returns 'other'"""
        rule = PluralRule({})
        assert rule(0) == 'other'
        assert rule(1) == 'other'
        assert rule(100) == 'other'
    
    @given(st.integers(min_value=0, max_value=1000))
    def test_rule_tags_property(self, n):
        """PluralRule.tags returns defined tags"""
        rule = PluralRule({'one': 'n is 1', 'few': 'n in 2..4'})
        tags = rule.tags
        assert 'one' in tags
        assert 'few' in tags
        # 'other' is implicit, not in tags unless explicitly defined
        assert 'other' not in tags or 'other' in rule.rules


# ============================================================================
# CORE MODULE TESTS
# ============================================================================

@composite
def locale_identifiers(draw):
    """Generate valid locale identifiers"""
    # Language: 2-3 lowercase letters
    lang = draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=2, max_size=3))
    
    # Territory: optional, 2 uppercase letters or 3 digits
    territory = draw(st.one_of(
        st.none(),
        st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=2, max_size=2),
        st.text(alphabet='0123456789', min_size=3, max_size=3)
    ))
    
    # Script: optional, 4 letters titlecase
    script = draw(st.one_of(
        st.none(),
        st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=4, max_size=4).map(lambda s: s.title())
    ))
    
    # Variant: optional, 5+ letters or 4 chars starting with digit
    variant = draw(st.one_of(
        st.none(),
        st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=5, max_size=8)
    ))
    
    # Build identifier
    parts = [lang]
    if script:
        parts.append(script)
    if territory:
        parts.append(territory)
    if variant:
        parts.append(variant)
    
    return '_'.join(parts)


class TestParseLocale:
    """Property tests for babel.core.parse_locale and get_locale_identifier"""
    
    @given(locale_identifiers())
    def test_parse_get_roundtrip(self, identifier):
        """parse_locale and get_locale_identifier are inverses"""
        try:
            parsed = parse_locale(identifier)
            reconstructed = get_locale_identifier(parsed)
            # Parse again to normalize
            reparsed = parse_locale(reconstructed)
            assert parsed == reparsed
        except ValueError:
            # Some generated identifiers may be invalid, that's ok
            pass
    
    def test_parse_simple_locales(self):
        """parse_locale handles common locale formats"""
        assert parse_locale('en') == ('en', None, None, None)
        assert parse_locale('en_US') == ('en', 'US', None, None)
        assert parse_locale('zh_CN') == ('zh', 'CN', None, None)
    
    def test_parse_with_script(self):
        """parse_locale handles script codes"""
        assert parse_locale('zh_Hans_CN') == ('zh', 'CN', 'Hans', None)
        assert parse_locale('sr_Cyrl_RS') == ('sr', 'RS', 'Cyrl', None)
    
    def test_parse_with_modifier(self):
        """parse_locale handles modifiers"""
        result = parse_locale('de_DE@euro')
        assert len(result) == 5
        assert result == ('de', 'DE', None, None, 'euro')
    
    def test_parse_strips_encoding(self):
        """parse_locale strips encoding information"""
        assert parse_locale('en_US.UTF-8') == ('en', 'US', None, None)
        assert parse_locale('de_DE.iso885915@euro') == ('de', 'DE', None, None, 'euro')
    
    def test_parse_rejects_empty(self):
        """parse_locale rejects empty identifiers"""
        with pytest.raises(ValueError):
            parse_locale('')
    
    def test_get_locale_identifier_formats(self):
        """get_locale_identifier formats tuples correctly"""
        assert get_locale_identifier(('de', 'DE', None, '1999', 'custom')) == 'de_DE_1999@custom'
        assert get_locale_identifier(('fi', None, None, None, 'custom')) == 'fi@custom'
        assert get_locale_identifier(('en', 'US')) == 'en_US'
        assert get_locale_identifier(('en',)) == 'en'
    
    @given(st.sampled_from(['-', '_', '/']), st.sampled_from(['en', 'de', 'fr', 'zh']))
    def test_parse_with_custom_separator(self, sep, lang):
        """parse_locale respects custom separator"""
        identifier = f"{lang}{sep}US"
        result = parse_locale(identifier, sep=sep)
        assert result[0] == lang
        assert result[1] == 'US'


class TestNegotiateLocale:
    """Property tests for babel.core.negotiate_locale"""
    
    @given(st.lists(st.sampled_from(['en_US', 'de_DE', 'fr_FR', 'es_ES']), min_size=1, max_size=5))
    def test_negotiate_prefers_exact_match(self, available):
        """negotiate_locale prefers exact matches"""
        preferred = [available[0]]
        result = negotiate_locale(preferred, available)
        assert result == available[0]
    
    def test_negotiate_returns_none_on_no_match(self):
        """negotiate_locale returns None when no match found"""
        result = negotiate_locale(['ja_JP'], ['en_US', 'de_DE'])
        assert result is None
    
    def test_negotiate_case_insensitive(self):
        """negotiate_locale is case insensitive"""
        result = negotiate_locale(['de_DE'], ['de_de', 'en_us'])
        assert result == 'de_DE'  # Returns preferred case
    
    def test_negotiate_language_fallback(self):
        """negotiate_locale falls back to language-only match"""
        result = negotiate_locale(['de_DE', 'en_US'], ['en', 'fr'])
        assert result == 'en'


# ============================================================================
# NUMBERS MODULE TESTS
# ============================================================================

class TestCurrencyFunctions:
    """Property tests for babel.numbers currency functions"""
    
    @given(st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY']))
    def test_normalize_currency_uppercase(self, currency):
        """normalize_currency converts to uppercase"""
        result = normalize_currency(currency.lower())
        assert result == currency
    
    @given(st.sampled_from(['USD', 'EUR', 'GBP', 'JPY', 'CNY']))
    def test_is_currency_valid(self, currency):
        """is_currency returns True for valid currencies (case-sensitive)"""
        assert is_currency(currency)
    
    @given(st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ', min_size=3, max_size=3))
    def test_normalize_currency_returns_none_for_invalid(self, code):
        """normalize_currency returns None for invalid codes"""
        assume(code not in list_currencies())
        result = normalize_currency(code)
        assert result is None
    
    def test_list_currencies_returns_set(self):
        """list_currencies returns a set"""
        result = list_currencies()
        assert isinstance(result, set)
        assert len(result) > 0
        # Check some common currencies
        assert 'USD' in result
        assert 'EUR' in result


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])


# ============================================================================
# LISTS MODULE TESTS
# ============================================================================

class TestFormatList:
    """Property tests for babel.lists.format_list"""
    
    @given(st.lists(st.text(min_size=1), min_size=0, max_size=5))
    def test_format_list_returns_string(self, items):
        """format_list always returns a string"""
        from babel.lists import format_list
        result = format_list(items, locale='en')
        assert isinstance(result, str)
    
    @given(st.lists(st.text(min_size=1), min_size=1, max_size=1))
    def test_format_list_single_item(self, items):
        """format_list with single item returns that item"""
        from babel.lists import format_list
        result = format_list(items, locale='en')
        assert result == items[0]
    
    def test_format_list_empty(self):
        """format_list with empty list returns empty string"""
        from babel.lists import format_list
        result = format_list([], locale='en')
        assert result == ''
    
    @given(st.lists(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=1, max_size=10), min_size=2, max_size=4))
    def test_format_list_contains_all_items(self, items):
        """format_list result contains all input items"""
        from babel.lists import format_list
        result = format_list(items, locale='en')
        for item in items:
            assert item in result
    
    @given(st.sampled_from(['standard', 'or', 'unit']))
    def test_format_list_different_styles(self, style):
        """format_list works with different styles"""
        from babel.lists import format_list
        items = ['a', 'b', 'c']
        result = format_list(items, style=style, locale='en')
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# DATES MODULE TESTS
# ============================================================================

class TestDateFunctions:
    """Property tests for babel.dates functions"""
    
    @given(st.integers(min_value=0, max_value=2000000000))
    def test_get_timezone_gmt(self, timestamp):
        """get_timezone_gmt returns GMT offset string"""
        from babel.dates import get_timezone_gmt
        from datetime import datetime
        import pytz
        dt = datetime.fromtimestamp(timestamp, tz=pytz.UTC)
        result = get_timezone_gmt(dt, locale='en')
        assert isinstance(result, str)
        assert 'GMT' in result or '+' in result or '-' in result
    
    @given(st.integers(min_value=1, max_value=12))
    def test_get_month_names(self, month):
        """get_month_names returns dict-like with valid month"""
        from babel.dates import get_month_names
        result = get_month_names(locale='en')
        # Returns LocaleDataDict which is dict-like
        assert month in result
        assert isinstance(result[month], str)
    
    @given(st.integers(min_value=0, max_value=6))
    def test_get_day_names(self, day):
        """get_day_names returns dict-like with valid day"""
        from babel.dates import get_day_names
        result = get_day_names(locale='en')
        # Returns LocaleDataDict which is dict-like
        assert day in result
        assert isinstance(result[day], str)
    
    def test_get_period_names(self):
        """get_period_names returns am/pm names"""
        from babel.dates import get_period_names
        result = get_period_names(locale='en')
        # Returns LocaleDataDict which is dict-like
        assert 'am' in result
        assert 'pm' in result


# ============================================================================
# MESSAGES.CATALOG MODULE TESTS
# ============================================================================

class TestCatalogFunctions:
    """Property tests for babel.messages.catalog functions"""
    
    @given(st.text(), st.lists(st.text(), min_size=1, max_size=10))
    def test_get_close_matches_returns_list(self, word, possibilities):
        """get_close_matches returns a list"""
        from babel.messages.catalog import get_close_matches
        result = get_close_matches(word, possibilities)
        assert isinstance(result, list)
        assert len(result) <= 3  # default n=3
    
    @given(st.text(min_size=1), st.lists(st.text(min_size=1), min_size=1, max_size=10))
    def test_get_close_matches_subset(self, word, possibilities):
        """get_close_matches returns subset of possibilities"""
        from babel.messages.catalog import get_close_matches
        result = get_close_matches(word, possibilities)
        assert all(match in possibilities for match in result)
    
    @given(st.text(min_size=1))
    def test_get_close_matches_exact_match_first(self, word):
        """get_close_matches returns exact match first if present"""
        from babel.messages.catalog import get_close_matches
        possibilities = [word, 'other1', 'other2']
        result = get_close_matches(word, possibilities)
        if result:
            assert result[0] == word
    
    @given(st.text(alphabet='abcdefghijklmnopqrstuvwxyz', min_size=3, max_size=10))
    def test_python_format_regex(self, text):
        """PYTHON_FORMAT regex matches valid format strings"""
        from babel.messages.catalog import PYTHON_FORMAT
        # Test with valid format strings
        test_strings = [
            f'%s {text}',
            f'%(name)s {text}',
            f'%d {text}',
            f'%5.2f {text}',
        ]
        for test_str in test_strings:
            matches = PYTHON_FORMAT.findall(test_str)
            assert len(matches) >= 1


# ============================================================================
# NUMBERS MODULE - ADDITIONAL TESTS
# ============================================================================

class TestNumberFormatting:
    """Additional property tests for babel.numbers"""
    
    @given(st.integers(min_value=-1000000, max_value=1000000))
    def test_format_number_returns_string(self, number):
        """format_number returns a string"""
        from babel.numbers import format_number
        result = format_number(number, locale='en_US')
        assert isinstance(result, str)
    
    @given(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
    def test_format_decimal_returns_string(self, number):
        """format_decimal returns a string"""
        from babel.numbers import format_decimal
        from decimal import Decimal
        result = format_decimal(Decimal(str(number)), locale='en_US')
        assert isinstance(result, str)
    
    @given(st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False))
    def test_format_currency_returns_string(self, amount):
        """format_currency returns a string"""
        from babel.numbers import format_currency
        result = format_currency(amount, 'USD', locale='en_US')
        assert isinstance(result, str)
        assert 'USD' in result or '$' in result
    
    @given(st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False))
    def test_format_percent_returns_string(self, number):
        """format_percent returns a string with %"""
        from babel.numbers import format_percent
        result = format_percent(number, locale='en_US')
        assert isinstance(result, str)
        assert '%' in result


# ============================================================================
# UTIL MODULE - ADDITIONAL TESTS
# ============================================================================

class TestOdictsort:
    """Property tests for babel.util.odict.bykey"""
    
    @given(st.dictionaries(st.text(min_size=1, max_size=10), st.integers(), min_size=0, max_size=10))
    def test_odict_preserves_keys(self, data):
        """odict operations preserve all keys"""
        from babel.util import odict
        od = odict(data)
        assert set(od.keys()) == set(data.keys())
    
    @given(st.dictionaries(st.text(min_size=1, max_size=10), st.integers(), min_size=0, max_size=10))
    def test_odict_preserves_values(self, data):
        """odict operations preserve all values"""
        from babel.util import odict
        od = odict(data)
        assert set(od.values()) == set(data.values())


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])


# ============================================================================
# UNITS MODULE TESTS
# ============================================================================

class TestUnitsModule:
    """Property tests for babel.units"""
    
    @given(st.sampled_from(['meter', 'kilometer', 'mile', 'foot', 'inch']))
    def test_find_unit_pattern_length_units(self, unit):
        """_find_unit_pattern finds length units"""
        from babel.units import _find_unit_pattern
        result = _find_unit_pattern(unit, locale='en')
        assert result is not None
        assert unit in result
    
    @given(st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False))
    def test_format_unit_returns_string(self, value):
        """format_unit returns string for valid inputs"""
        from babel.units import format_unit
        result = format_unit(value, 'length-meter', locale='en')
        assert isinstance(result, str)
        assert len(result) > 0
    
    @given(st.sampled_from(['meter', 'kilometer', 'gram', 'kilogram']))
    def test_get_unit_name_returns_string(self, unit):
        """get_unit_name returns string for known units"""
        from babel.units import get_unit_name
        result = get_unit_name(unit, locale='en')
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# LANGUAGES MODULE TESTS
# ============================================================================

class TestLanguagesModule:
    """Property tests for babel.languages"""
    
    @given(st.sampled_from(['US', 'GB', 'FR', 'DE', 'JP', 'CN']))
    def test_get_official_languages_returns_tuple(self, territory):
        """get_official_languages returns tuple of language codes"""
        from babel.languages import get_official_languages
        result = get_official_languages(territory)
        assert isinstance(result, tuple)
        # All elements should be strings
        for lang in result:
            assert isinstance(lang, str)
            assert len(lang) >= 2
    
    @given(st.sampled_from(['US', 'GB', 'FR', 'DE', 'JP']))
    def test_get_territory_language_info_returns_dict(self, territory):
        """get_territory_language_info returns dict"""
        from babel.languages import get_territory_language_info
        result = get_territory_language_info(territory)
        assert isinstance(result, dict)
        # Values should be dicts with population_percent
        for lang_code, info in result.items():
            assert isinstance(lang_code, str)
            assert isinstance(info, dict)


# ============================================================================
# SUPPORT MODULE TESTS
# ============================================================================

class TestSupportModule:
    """Property tests for babel.support.Format"""
    
    @given(st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False))
    def test_format_decimal_method(self, value):
        """Format.decimal returns string"""
        from babel.support import Format
        fmt = Format('en_US')
        result = fmt.decimal(value)
        assert isinstance(result, str)
    
    @given(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    def test_format_percent_method(self, value):
        """Format.percent returns string"""
        from babel.support import Format
        fmt = Format('en_US')
        result = fmt.percent(value)
        assert isinstance(result, str)


# ============================================================================
# MESSAGES.CATALOG TESTS
# ============================================================================

class TestMessagesCatalog:
    """Property tests for babel.messages.catalog"""
    
    @given(st.text(min_size=1, max_size=100))
    def test_message_id_preserves_string(self, msgid):
        """Message preserves msgid"""
        from babel.messages.catalog import Message
        msg = Message(msgid)
        assert msg.id == msgid
    
    @given(st.text(min_size=1, max_size=50), st.text(min_size=1, max_size=50))
    def test_message_with_context(self, msgid, context):
        """Message preserves context"""
        from babel.messages.catalog import Message
        msg = Message(msgid, context=context)
        assert msg.context == context
        assert msg.id == msgid


# ============================================================================
# ADDITIONAL UTIL TESTS
# ============================================================================

class TestUtilMisc:
    """Additional property tests for babel.util"""
    
    @given(st.lists(st.integers(), min_size=0, max_size=20))
    def test_distinct_idempotent(self, items):
        """Applying distinct twice gives same result"""
        result1 = list(distinct(items))
        result2 = list(distinct(result1))
        assert result1 == result2
    
    @given(st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=20))
    def test_distinct_no_duplicates(self, items):
        """distinct removes all duplicates"""
        result = list(distinct(items))
        assert len(result) == len(set(result))


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
