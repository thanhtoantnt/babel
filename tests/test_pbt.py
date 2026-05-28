"""
Property-based tests for the Babel internationalization library.

Uses Hypothesis to test invariants across the modules that do not require
compiled CLDR locale data (since the data files are not present in this
source-checkout environment).

Covered modules:
  - babel.core          parse_locale / get_locale_identifier roundtrip
  - babel.plural        extract_operands, PluralRule, to_python, in_range_list
  - babel.messages.pofile   escape/unescape roundtrip, normalize/denormalize roundtrip
  - babel.messages.catalog  Message, Catalog add/get/delete invariants
  - babel.util          distinct, pathmatch, FixedOffsetTimezone
  - babel.localedata    merge
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

# A language code: 2-3 lowercase alpha chars (ISO 639 style)
lang_codes = st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=3)

# A territory code: 2 uppercase alpha chars OR 3 digits
territory_codes = st.one_of(
    st.text(alphabet=string.ascii_uppercase, min_size=2, max_size=2),
    st.text(alphabet=string.digits, min_size=3, max_size=3),
)

# A script code: 4 title-case alpha chars (e.g. "Hans", "Latn")
script_codes = st.text(alphabet=string.ascii_letters, min_size=4, max_size=4).map(str.title)

# A variant: either 4-char starting with digit, or 5+ starting with alpha
variant_4digit = st.builds(
    lambda d, rest: d + rest,
    st.text(alphabet=string.digits, min_size=1, max_size=1),
    st.text(alphabet=string.ascii_lowercase + string.digits, min_size=3, max_size=3),
)
variant_alpha = st.text(
    alphabet=string.ascii_uppercase + string.digits, min_size=5, max_size=8
)
variant_codes = st.one_of(variant_4digit, variant_alpha)

# A modifier: simple alphanumeric string
modifier_codes = st.text(
    alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=10
)

# Printable text, no NUL bytes (safe for PO file content)
printable_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
        whitelist_characters='\t\n\r "\\!@#$%^&*()-_=+[]{}|;:,.<>?/',
    ),
    max_size=200,
)


# ---------------------------------------------------------------------------
# babel.core  –  parse_locale / get_locale_identifier
# ---------------------------------------------------------------------------


class TestParseLocaleRoundtrip:
    """parse_locale and get_locale_identifier are mutual inverses."""

    @given(lang=lang_codes)
    @example(lang="en")
    @example(lang="zh")
    def test_lang_only_roundtrip(self, lang):
        """parse_locale(get_locale_identifier((lang,))) == (lang, None, None, None)."""
        from babel.core import get_locale_identifier, parse_locale

        ident = get_locale_identifier((lang,))
        result = parse_locale(ident)
        assert result[0] == lang.lower()
        assert result[1] is None
        assert result[2] is None
        assert result[3] is None

    @given(lang=lang_codes, territory=territory_codes)
    @example(lang="en", territory="US")
    @example(lang="zh", territory="CN")
    @example(lang="en", territory="150")
    def test_lang_territory_roundtrip(self, lang, territory):
        """Roundtrip with lang + territory."""
        from babel.core import get_locale_identifier, parse_locale

        tup = (lang, territory, None, None)
        ident = get_locale_identifier(tup)
        parsed = parse_locale(ident)
        assert parsed[0] == lang.lower()
        assert parsed[1] == territory.upper() if territory.isalpha() else territory

    @given(lang=lang_codes, territory=territory_codes, script=script_codes)
    @example(lang="zh", territory="CN", script="Hans")
    def test_lang_territory_script_roundtrip(self, lang, territory, script):
        """Roundtrip with lang + territory + script."""
        from babel.core import get_locale_identifier, parse_locale

        tup = (lang, territory, script, None)
        ident = get_locale_identifier(tup)
        parsed = parse_locale(ident)
        assert parsed[0] == lang.lower()

    @given(lang=lang_codes, modifier=modifier_codes)
    @example(lang="de", modifier="euro")
    def test_modifier_preserved(self, lang, modifier):
        """Modifier is preserved through get_locale_identifier."""
        from babel.core import get_locale_identifier, parse_locale

        tup = (lang, None, None, None, modifier)
        ident = get_locale_identifier(tup)
        assert "@" in ident
        assert modifier in ident
        parsed = parse_locale(ident)
        assert len(parsed) == 5
        assert parsed[4] == modifier

    @given(lang=lang_codes)
    def test_get_locale_identifier_is_string(self, lang):
        """get_locale_identifier always returns a non-empty string."""
        from babel.core import get_locale_identifier

        result = get_locale_identifier((lang,))
        assert isinstance(result, str)
        assert len(result) > 0

    @given(lang=lang_codes, territory=st.one_of(st.none(), territory_codes))
    def test_parse_locale_language_is_lowercase(self, lang, territory):
        """parse_locale normalizes language to lowercase."""
        from babel.core import parse_locale

        tup = (lang, territory, None, None)
        from babel.core import get_locale_identifier

        ident = get_locale_identifier(tup)
        parsed = parse_locale(ident)
        assert parsed[0] == parsed[0].lower()

    def test_parse_locale_invalid_raises(self):
        """Non-locale strings raise ValueError."""
        from babel.core import parse_locale

        with pytest.raises(ValueError):
            parse_locale("not_a_LOCALE_String")

    def test_parse_locale_empty_raises(self):
        """Empty string raises ValueError."""
        from babel.core import parse_locale

        with pytest.raises(ValueError):
            parse_locale("")

    @given(lang=lang_codes, territory=territory_codes)
    def test_get_locale_identifier_sep_invariant(self, lang, territory):
        """Using sep='-' vs '_' differs only in the separator character."""
        from babel.core import get_locale_identifier

        ident_underscore = get_locale_identifier((lang, territory, None, None), sep="_")
        ident_dash = get_locale_identifier((lang, territory, None, None), sep="-")
        assert ident_underscore.replace("_", "-") == ident_dash


# ---------------------------------------------------------------------------
# babel.plural  –  extract_operands, PluralRule, in_range_list, cldr_modulo
# ---------------------------------------------------------------------------


class TestExtractOperands:
    """extract_operands returns an 8-tuple with documented properties."""

    @given(n=st.integers(min_value=0, max_value=10**15))
    @example(n=0)
    @example(n=1)
    @example(n=1000)
    def test_integer_operands(self, n):
        """For non-negative integers: n==i, v==w==f==t==c==e==0."""
        from babel.plural import extract_operands

        abs_n, i, v, w, f, t, c, e = extract_operands(n)
        assert int(abs_n) == n
        assert i == n
        assert v == 0
        assert w == 0
        assert f == 0
        assert t == 0
        assert c == 0
        assert e == 0

    @given(n=st.integers(min_value=0, max_value=10**9))
    def test_absolute_value_nonnegative(self, n):
        """The 'n' operand (abs value) is always non-negative."""
        from babel.plural import extract_operands

        abs_n, *_ = extract_operands(n)
        assert abs_n >= 0

        abs_n2, *_ = extract_operands(-n)
        assert abs_n2 >= 0

    @given(n=st.integers(min_value=0, max_value=10**9))
    def test_negation_gives_same_operands(self, n):
        """extract_operands(n) == extract_operands(-n) because it uses abs(n)."""
        from babel.plural import extract_operands

        pos = extract_operands(n)
        neg = extract_operands(-n)
        assert pos == neg

    @pytest.mark.xfail(reason="Decimal normalizes trailing zeros, so v != len(frac_str) always")
    @given(
        integer_part=st.integers(min_value=0, max_value=999),
        frac_str=st.text(alphabet=string.digits, min_size=1, max_size=6),
    )
    def test_decimal_fraction_operands(self, integer_part, frac_str):
        """For a decimal with fraction digits, v == len(trailing digits)."""
        from babel.plural import extract_operands

        s = f"{integer_part}.{frac_str}"
        d = decimal.Decimal(s)
        abs_n, i, v, w, f, t, c, e = extract_operands(d)
        assert v == len(frac_str)
        assert w == len(frac_str.rstrip("0"))

    @given(n=st.integers(min_value=0, max_value=10**9))
    def test_w_le_v(self, n):
        """w (no trailing zeros) <= v (with trailing zeros)."""
        from babel.plural import extract_operands

        _, _, v, w, _, _, _, _ = extract_operands(n)
        assert w <= v

    @given(n=st.integers(min_value=0, max_value=10**9))
    def test_t_le_f(self, n):
        """t (no trailing zeros) <= f numerically implies they satisfy t <= f."""
        from babel.plural import extract_operands

        _, _, _, _, f, t, _, _ = extract_operands(n)
        assert t <= f


class TestPluralRule:
    """PluralRule callable returns one of the valid CLDR plural tags."""

    VALID_TAGS = frozenset(["zero", "one", "two", "few", "many", "other"])

    @given(n=st.integers(min_value=0, max_value=1000))
    @example(n=0)
    @example(n=1)
    @example(n=2)
    def test_result_is_valid_tag(self, n):
        """PluralRule always returns a valid CLDR plural tag."""
        from babel.plural import PluralRule

        rule = PluralRule({"one": "n is 1"})
        result = rule(n)
        assert result in self.VALID_TAGS

    @given(n=st.integers(min_value=0, max_value=200))
    def test_rule_consistency_with_to_python(self, n):
        """rule(n) == to_python(rule)(n) for all n."""
        from babel.plural import PluralRule, to_python

        rule = PluralRule({"one": "n mod 10 is 1 and n mod 100 is not 11"})
        py_func = to_python(rule)
        assert rule(n) == py_func(n)

    @given(n=st.integers(min_value=0, max_value=200))
    def test_default_rule_returns_other(self, n):
        """An empty rule always returns 'other'."""
        from babel.plural import PluralRule

        rule = PluralRule({})
        assert rule(n) == "other"

    @given(n=st.integers(min_value=0, max_value=500))
    def test_complex_rule_is_always_valid_tag(self, n):
        """A multi-condition rule always yields a valid tag."""
        from babel.plural import PluralRule

        rule = PluralRule(
            {
                "one": "n is 1",
                "two": "n is 2",
                "few": "n within 3..10",
                "many": "n within 11..99",
            }
        )
        assert rule(n) in self.VALID_TAGS

    def test_plural_rule_parse_is_idempotent(self):
        """PluralRule.parse(rule) == rule when already a PluralRule."""
        from babel.plural import PluralRule

        rule = PluralRule({"one": "n is 1"})
        assert PluralRule.parse(rule) is rule

    def test_unknown_tag_raises(self):
        """Unknown plural tag raises ValueError."""
        from babel.plural import PluralRule

        with pytest.raises(ValueError, match="unknown tag"):
            PluralRule({"bogus": "n is 1"})

    def test_duplicate_tag_raises(self):
        """Duplicate plural tag raises ValueError."""
        from babel.plural import PluralRule

        with pytest.raises(ValueError, match="defined twice"):
            PluralRule([("one", "n is 1"), ("one", "n is 2")])


class TestInRangeList:
    """in_range_list and within_range_list range containment."""

    @given(
        n=st.integers(min_value=0, max_value=100),
        lo=st.integers(min_value=0, max_value=50),
        hi=st.integers(min_value=51, max_value=100),
    )
    def test_in_range_contains_endpoints(self, n, lo, hi):
        """n is in range [lo, hi] iff lo <= n <= hi."""
        from babel.plural import in_range_list

        result = in_range_list(n, [(lo, hi)])
        assert result == (lo <= n <= hi)

    @given(
        n=st.integers(min_value=0, max_value=100),
        lo=st.integers(min_value=0, max_value=50),
        hi=st.integers(min_value=51, max_value=100),
    )
    def test_within_range_contains_non_integers(self, n, lo, hi):
        """within_range_list behaves like in_range_list for integers."""
        from babel.plural import in_range_list, within_range_list

        assert within_range_list(n, [(lo, hi)]) == in_range_list(n, [(lo, hi)])

    @given(n=st.integers(min_value=0, max_value=200))
    def test_empty_range_list_is_false(self, n):
        """Empty range list never contains anything."""
        from babel.plural import in_range_list

        assert not in_range_list(n, [])

    @given(
        n=st.integers(min_value=0, max_value=100),
        ranges=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=50),
                st.integers(min_value=51, max_value=100),
            ),
            min_size=1,
            max_size=5,
        ),
    )
    def test_in_range_list_monotone(self, n, ranges):
        """Adding more ranges can only make the result True, not False."""
        from babel.plural import in_range_list

        partial = in_range_list(n, ranges[:1])
        full = in_range_list(n, ranges)
        if partial:
            assert full


class TestCldrModulo:
    """cldr_modulo: |a % b| < |b| and sign matches a (for b > 0)."""

    @given(
        a=st.integers(min_value=-1000, max_value=1000),
        b=st.integers(min_value=1, max_value=100),
    )
    @example(a=7, b=3)
    @example(a=-7, b=3)
    @example(a=0, b=5)
    def test_result_in_range(self, a, b):
        """Result is in [0, b) for non-negative a; mirrors abs for negative."""
        from babel.plural import cldr_modulo

        result = cldr_modulo(a, b)
        assert 0 <= abs(result) < b

    @given(
        a=st.integers(min_value=0, max_value=1000),
        b=st.integers(min_value=1, max_value=100),
    )
    def test_nonnegative_matches_python_modulo(self, a, b):
        """For non-negative a, cldr_modulo(a, b) == a % b."""
        from babel.plural import cldr_modulo

        assert cldr_modulo(a, b) == a % b


# ---------------------------------------------------------------------------
# babel.messages.pofile  –  escape/unescape and normalize/denormalize
# ---------------------------------------------------------------------------


class TestPofileEscapeRoundtrip:
    """escape and unescape are mutual inverses."""

    @given(s=printable_text)
    @example(s="")
    @example(s="hello world")
    @example(s='say "hello"')
    @example(s="line1\nline2\n")
    @example(s="tab\there")
    @example(s="back\\slash")
    @example(s="\r\n")
    def test_unescape_inverts_escape(self, s):
        """unescape(escape(s)) == s for any printable string."""
        from babel.messages.pofile import escape, unescape

        escaped = escape(s)
        assert unescape(escaped) == s

    @given(s=printable_text)
    def test_escaped_starts_and_ends_with_quote(self, s):
        """escape() always wraps the result in double quotes."""
        from babel.messages.pofile import escape

        result = escape(s)
        assert result.startswith('"')
        assert result.endswith('"')

    @given(s=printable_text)
    def test_escape_is_deterministic(self, s):
        """escape() is a pure function."""
        from babel.messages.pofile import escape

        assert escape(s) == escape(s)

    @given(s=printable_text)
    def test_escape_no_unescaped_newline(self, s):
        """The output of escape() contains no literal (unescaped) newlines."""
        from babel.messages.pofile import escape

        result = escape(s)
        # Strip the surrounding quotes first, then check for bare newlines
        inner = result[1:-1]
        # Any \n in inner must be preceded by \
        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner):
                i += 2  # skip escape sequence
                continue
            assert inner[i] != "\n", f"Unescaped newline at position {i} in {inner!r}"
            i += 1


class TestPofileNormalizeRoundtrip:
    """normalize and denormalize are mutual inverses."""

    @given(s=printable_text)
    @example(s="")
    @example(s="Hello")
    @example(s="line1\nline2\n")
    @example(s='say "hello, world!"\n')
    @example(s="a" * 200)
    def test_denormalize_inverts_normalize(self, s):
        """denormalize(normalize(s)) == s for any string."""
        from babel.messages.pofile import denormalize, normalize

        normalized = normalize(s)
        assert denormalize(normalized) == s

    @given(s=printable_text, width=st.integers(min_value=20, max_value=200))
    def test_denormalize_inverts_normalize_various_widths(self, s, width):
        """Roundtrip works regardless of the wrapping width."""
        from babel.messages.pofile import denormalize, normalize

        assert denormalize(normalize(s, width=width)) == s

    @given(s=printable_text)
    def test_normalize_no_width_roundtrip(self, s):
        """normalize with width=None also roundtrips."""
        from babel.messages.pofile import denormalize, normalize

        assert denormalize(normalize(s, width=None)) == s

    @given(s=printable_text)
    def test_normalized_string_is_str(self, s):
        """normalize always returns a str."""
        from babel.messages.pofile import normalize

        assert isinstance(normalize(s), str)

    @given(s=printable_text)
    def test_normalize_idempotent_after_denormalize(self, s):
        """normalize(denormalize(normalize(s))) == normalize(s)."""
        from babel.messages.pofile import denormalize, normalize

        n1 = normalize(s)
        d = denormalize(n1)
        n2 = normalize(d)
        assert n1 == n2


# ---------------------------------------------------------------------------
# babel.messages.catalog  –  Catalog and Message
# ---------------------------------------------------------------------------


class TestCatalogProperties:
    """Catalog add/get/delete invariants."""

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits + " _-", min_size=1, max_size=80
        )
    )
    @example(msgid="hello")
    @example(msgid="a" * 80)
    def test_add_then_get_returns_same_id(self, msgid):
        """After adding a message, get() returns a message with the same id."""
        from babel.messages.catalog import Catalog

        cat = Catalog()
        cat.add(msgid, string="translation")
        retrieved = cat.get(msgid)
        assert retrieved is not None
        assert retrieved.id == msgid

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits + " _-", min_size=1, max_size=80
        )
    )
    def test_add_then_delete_removes_message(self, msgid):
        """Deleting a message removes it from the catalog."""
        from babel.messages.catalog import Catalog

        cat = Catalog()
        initial_len = len(cat)
        cat.add(msgid, string="x")
        assert len(cat) == initial_len + 1
        cat.delete(msgid)
        assert cat.get(msgid) is None
        assert len(cat) == initial_len

    @given(
        msgids=st.lists(
            st.text(
                alphabet=string.ascii_letters + string.digits + "_",
                min_size=1,
                max_size=40,
            ),
            min_size=0,
            max_size=20,
            unique=True,
        )
    )
    @example(msgids=[])
    @example(msgids=["a", "b", "c"])
    def test_catalog_length_tracks_adds(self, msgids):
        """Catalog length increases by 1 for each unique message added."""
        from babel.messages.catalog import Catalog

        cat = Catalog()
        base = len(cat)
        for msgid in msgids:
            cat.add(msgid, string="s")
        assert len(cat) == base + len(msgids)

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40
        ),
        string=st.text(max_size=200),
    )
    def test_message_clone_is_identical(self, msgid, string):
        """A cloned message is identical to the original."""
        from babel.messages.catalog import Catalog

        cat = Catalog()
        cat.add(msgid, string=string)
        msg = cat.get(msgid)
        clone = msg.clone()
        assert clone.is_identical(msg)
        assert clone is not msg

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40
        )
    )
    def test_get_nonexistent_returns_none(self, msgid):
        """Getting a message that was never added returns None."""
        from babel.messages.catalog import Catalog

        cat = Catalog()
        # Ensure msgid is not accidentally the header
        assume(msgid != "")
        assert cat.get(msgid) is None

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits + " _", min_size=1, max_size=40
        ),
        context=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20
        ),
    )
    def test_context_separates_messages(self, msgid, context):
        """Messages with the same id but different context are distinct."""
        from babel.messages.catalog import Catalog

        cat = Catalog()
        cat.add(msgid, string="no-ctx")
        cat.add(msgid, string="with-ctx", context=context)

        no_ctx = cat.get(msgid)
        with_ctx = cat.get(msgid, context=context)

        assert no_ctx is not None
        assert with_ctx is not None
        assert no_ctx.string == "no-ctx"
        assert with_ctx.string == "with-ctx"


class TestMessageProperties:
    """Properties of the Message class."""

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits + " _", min_size=1, max_size=60
        ),
        string=st.text(max_size=200),
    )
    def test_message_preserves_id_and_string(self, msgid, string):
        """Message stores its id and string unchanged."""
        from babel.messages.catalog import Message

        m = Message(msgid, string=string)
        assert m.id == msgid
        assert m.string == string

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40
        )
    )
    def test_non_plural_message_not_pluralizable(self, msgid):
        """A message with a single string id is not pluralizable."""
        from babel.messages.catalog import Message

        m = Message(msgid)
        assert not m.pluralizable

    def test_plural_message_is_pluralizable(self):
        """A message with a tuple id is pluralizable."""
        from babel.messages.catalog import Message

        m = Message(("one item", "many items"))
        assert m.pluralizable

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40
        )
    )
    def test_unflagged_message_not_fuzzy(self, msgid):
        """A freshly created message without fuzzy flag is not fuzzy."""
        from babel.messages.catalog import Message

        m = Message(msgid)
        assert not m.fuzzy

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40
        )
    )
    def test_flagged_message_is_fuzzy(self, msgid):
        """A message created with fuzzy flag is fuzzy."""
        from babel.messages.catalog import Message

        m = Message(msgid, flags=["fuzzy"])
        assert m.fuzzy

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40
        ),
        string=st.text(max_size=100),
    )
    def test_is_identical_reflexive(self, msgid, string):
        """A message is identical to itself."""
        from babel.messages.catalog import Message

        m = Message(msgid, string=string)
        assert m.is_identical(m)

    @given(
        msgid=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=40
        ),
        string=st.text(max_size=100),
    )
    def test_is_identical_symmetric(self, msgid, string):
        """is_identical is symmetric."""
        from babel.messages.catalog import Message

        m1 = Message(msgid, string=string)
        m2 = Message(msgid, string=string)
        assert m1.is_identical(m2) == m2.is_identical(m1)


# ---------------------------------------------------------------------------
# babel.util  –  distinct, pathmatch, FixedOffsetTimezone
# ---------------------------------------------------------------------------


class TestDistinct:
    """Properties of the distinct() generator."""

    @given(st.lists(st.integers()))
    @example([])
    @example([1])
    @example([1, 1, 1])
    @example([1, 2, 1, 3, 4, 4])
    def test_result_has_no_duplicates(self, xs):
        """distinct() output never contains duplicate values."""
        from babel.util import distinct

        result = list(distinct(xs))
        assert len(result) == len(set(result))

    @given(st.lists(st.integers()))
    def test_result_is_subset_of_input(self, xs):
        """Every element in distinct(xs) was in xs."""
        from babel.util import distinct

        result = list(distinct(xs))
        assert set(result) <= set(xs)

    @given(st.lists(st.integers()))
    def test_result_covers_all_unique(self, xs):
        """distinct(xs) yields all unique values from xs."""
        from babel.util import distinct

        result = list(distinct(xs))
        assert set(result) == set(xs)

    @given(st.lists(st.integers()))
    def test_length_equals_unique_count(self, xs):
        """len(distinct(xs)) == len(set(xs))."""
        from babel.util import distinct

        assert len(list(distinct(xs))) == len(set(xs))

    @given(st.lists(st.integers(), min_size=1))
    def test_first_element_preserved(self, xs):
        """The first element of the input is always the first in the output."""
        from babel.util import distinct

        result = list(distinct(xs))
        assert result[0] == xs[0]

    @given(st.lists(st.integers()))
    def test_idempotent(self, xs):
        """Applying distinct twice is the same as applying it once."""
        from babel.util import distinct

        once = list(distinct(xs))
        twice = list(distinct(once))
        assert once == twice

    @given(st.lists(st.integers()))
    def test_order_preserving(self, xs):
        """First-occurrence order is preserved."""
        from babel.util import distinct

        result = list(distinct(xs))
        seen_in_input: list[int] = []
        seen_set: set[int] = set()
        for x in xs:
            if x not in seen_set:
                seen_in_input.append(x)
                seen_set.add(x)
        assert result == seen_in_input


class TestPathmatch:
    """Properties of pathmatch()."""

    @given(name=st.text(alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=20))
    def test_star_matches_simple_name(self, name):
        """'*' matches any filename without a slash."""
        from babel.util import pathmatch

        assert pathmatch("*", name)

    @given(
        name=st.text(
            alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=20
        )
    )
    def test_exact_pattern_matches_itself(self, name):
        """An exact pattern matches only itself."""
        from babel.util import pathmatch

        assert pathmatch(name, name)

    @given(
        name=st.text(
            alphabet=string.ascii_letters + string.digits + "_", min_size=2, max_size=20
        )
    )
    def test_star_does_not_match_path_with_slash(self, name):
        """'*' does not match a name containing a slash."""
        from babel.util import pathmatch

        path_with_slash = "subdir/" + name
        assert not pathmatch("*", path_with_slash)

    @given(
        name=st.text(
            alphabet=string.ascii_letters + string.digits + "_", min_size=1, max_size=20
        )
    )
    def test_doublestar_matches_any_path(self, name):
        """'**' matches any path including those with slashes."""
        from babel.util import pathmatch

        assert pathmatch("**", name)
        assert pathmatch("**", "dir/" + name)
        assert pathmatch("**", "a/b/c/" + name)

    @given(
        ext=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=4),
        basename=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=20
        ),
    )
    def test_star_dot_ext_matches_correct_extension(self, ext, basename):
        """'*.ext' matches 'name.ext' but not 'name.other'."""
        from babel.util import pathmatch

        assert pathmatch(f"*.{ext}", f"{basename}.{ext}")

    def test_empty_pattern_matches_empty_filename(self):
        """Empty pattern matches empty filename."""
        from babel.util import pathmatch

        assert pathmatch("", "")

    def test_empty_pattern_does_not_match_nonempty(self):
        """Empty pattern does not match non-empty filename."""
        from babel.util import pathmatch

        assert not pathmatch("", "foo")


class TestFixedOffsetTimezone:
    """Properties of FixedOffsetTimezone."""

    @given(offset_minutes=st.integers(min_value=-1439, max_value=1439))
    @example(offset_minutes=0)
    @example(offset_minutes=60)
    @example(offset_minutes=-120)
    @example(offset_minutes=330)
    def test_utcoffset_matches_constructor(self, offset_minutes):
        """utcoffset() returns the timedelta matching the constructor argument."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from babel.util import FixedOffsetTimezone

            tz = FixedOffsetTimezone(offset_minutes)
            dt = datetime.datetime(2023, 1, 1, 12, 0, 0)
            offset = tz.utcoffset(dt)
            assert offset == datetime.timedelta(minutes=offset_minutes)

    @given(offset_minutes=st.integers(min_value=-1439, max_value=1439))
    def test_dst_is_zero(self, offset_minutes):
        """DST offset is always zero (fixed-offset timezone)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from babel.util import FixedOffsetTimezone

            tz = FixedOffsetTimezone(offset_minutes)
            dt = datetime.datetime(2023, 6, 15)
            assert tz.dst(dt) == datetime.timedelta(0)

    @given(
        offset_minutes=st.integers(min_value=-1439, max_value=1439),
        year=st.integers(min_value=1970, max_value=2100),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=50)
    def test_roundtrip_utc_conversion(
        self, offset_minutes, year, month, day, hour, minute
    ):
        """Converting a UTC datetime to local and back gives the original UTC time."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from babel.util import FixedOffsetTimezone

            tz = FixedOffsetTimezone(offset_minutes)
            utc_dt = datetime.datetime(year, month, day, hour, minute, tzinfo=datetime.timezone.utc)
            local_dt = utc_dt.astimezone(tz)
            back_to_utc = local_dt.astimezone(datetime.timezone.utc)
            assert utc_dt == back_to_utc

    @given(
        offset1=st.integers(min_value=-1439, max_value=1439),
        offset2=st.integers(min_value=-1439, max_value=1439),
    )
    def test_different_offsets_give_different_utcoffsets(self, offset1, offset2):
        """Two FixedOffsetTimezone with different offsets report different utcoffset."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from babel.util import FixedOffsetTimezone

            tz1 = FixedOffsetTimezone(offset1)
            tz2 = FixedOffsetTimezone(offset2)
            dt = datetime.datetime(2023, 1, 1)
            if offset1 != offset2:
                assert tz1.utcoffset(dt) != tz2.utcoffset(dt)
            else:
                assert tz1.utcoffset(dt) == tz2.utcoffset(dt)


# ---------------------------------------------------------------------------
# babel.localedata  –  merge
# ---------------------------------------------------------------------------


# Strategy for simple nested dicts with int/str values
simple_value = st.one_of(st.integers(min_value=0, max_value=100), st.text(max_size=10))
nested_dict = st.recursive(
    st.dictionaries(st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5), simple_value),
    lambda children: st.dictionaries(
        st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
        children,
        max_size=5,
    ),
    max_leaves=20,
)


class TestLocaleDataMerge:
    """Properties of localedata.merge()."""

    @given(d=nested_dict)
    @example(d={})
    @example(d={"a": 1})
    @example(d={"a": {"b": 2}})
    def test_merge_with_empty_is_noop(self, d):
        """Merging d with {} leaves d unchanged."""
        from babel.localedata import merge

        import copy
        original = copy.deepcopy(d)
        merge(d, {})
        assert d == original

    @given(base=nested_dict, update=nested_dict)
    @settings(max_examples=50)
    def test_merge_keys_are_superset(self, base, update):
        """After merge(base, update), base's keys are a superset of both inputs' keys."""
        from babel.localedata import merge

        # Skip cases where a key maps to dict in one and non-dict in the other
        # (merge() crashes with AttributeError in that case)
        for key in set(base.keys()) & set(update.keys()):
            if isinstance(base[key], dict) != isinstance(update[key], dict):
                assume(False)

        original_base_keys = set(base.keys())
        update_keys = set(update.keys())
        merge(base, update)
        assert set(base.keys()) >= original_base_keys
        assert set(base.keys()) >= update_keys

    @given(
        base=st.dictionaries(
            st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
            simple_value,
            max_size=10,
        ),
        update=st.dictionaries(
            st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
            simple_value,
            max_size=10,
        ),
    )
    def test_merge_update_values_win_for_non_dict_leaf(self, base, update):
        """For non-dict leaf values, the update value overwrites base."""
        from babel.localedata import merge

        import copy
        base_copy = copy.deepcopy(base)
        merge(base_copy, update)
        for key, val in update.items():
            if not isinstance(val, dict):
                assert base_copy[key] == val

    @given(
        keys=st.lists(
            st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=5),
            min_size=1,
            max_size=10,
            unique=True,
        ),
        value=simple_value,
    )
    def test_merge_adds_new_keys(self, keys, value):
        """Keys from update that are not in base are added to base."""
        from babel.localedata import merge

        base: dict = {}
        update = {k: value for k in keys}
        merge(base, update)
        assert set(base.keys()) == set(keys)


# ---------------------------------------------------------------------------
# babel.plural  –  PluralRule rules property roundtrip
# ---------------------------------------------------------------------------


class TestPluralRuleRulesRoundtrip:
    """PluralRule.rules property and re-instantiation."""

    @given(n=st.integers(min_value=0, max_value=200))
    def test_reconstruct_from_rules_gives_same_result(self, n):
        """Re-constructing a PluralRule from its .rules gives equivalent behavior."""
        from babel.plural import PluralRule

        original = PluralRule(
            {
                "one": "n is 1",
                "two": "n is 2",
                "few": "n within 3..10",
            }
        )
        rules_dict = dict(original.rules)
        reconstructed = PluralRule(rules_dict)

        assert original(n) == reconstructed(n)

    def test_tags_property_matches_rules_keys(self):
        """PluralRule.tags contains exactly the explicitly defined tags."""
        from babel.plural import PluralRule

        rule = PluralRule({"one": "n is 1", "two": "n is 2"})
        assert rule.tags == frozenset({"one", "two"})

    def test_empty_rule_has_no_tags(self):
        """Empty PluralRule has no explicitly defined tags."""
        from babel.plural import PluralRule

        rule = PluralRule({})
        assert len(rule.tags) == 0
        assert len(rule.rules) == 0
