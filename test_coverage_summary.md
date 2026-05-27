# Property-Based Test Coverage Summary for Babel

## Test Statistics
- **Total Tests**: 66 property-based tests
- **Status**: All tests passing ✓
- **Framework**: Hypothesis 6.152.9

## Modules Covered

### 1. babel.util (8 tests)
- `distinct()` - uniqueness, order preservation, idempotency
- `pathmatch()` - pattern matching with wildcards
- `odict` - ordered dictionary operations

### 2. babel.plural (6 tests)
- `extract_operands()` - number decomposition into operands
- `PluralRule.parse()` - plural rule parsing and validation
- `to_javascript()` - JavaScript code generation

### 3. babel.core (12 tests)
- `parse_locale()` - locale identifier parsing and roundtrip
- `get_locale_identifier()` - locale identifier construction
- `Locale.parse()` - locale object creation
- `default_locale()` - default locale detection
- `negotiate_locale()` - locale negotiation

### 4. babel.numbers (10 tests)
- `get_currency_name()` - currency name retrieval
- `get_currency_symbol()` - currency symbol retrieval
- `is_currency()` - currency code validation
- `get_decimal_symbol()` - decimal separator retrieval
- `get_group_symbol()` - thousands separator retrieval
- `format_number()` - number formatting
- `format_decimal()` - decimal formatting
- `format_currency()` - currency formatting
- `format_percent()` - percentage formatting

### 5. babel.dates (5 tests)
- `get_timezone()` - timezone object retrieval
- `get_month_names()` - month name dictionaries
- `get_day_names()` - day name dictionaries
- `get_period_names()` - AM/PM period names

### 6. babel.lists (3 tests)
- `format_list()` - list formatting with locale-specific patterns

### 7. babel.units (3 tests)
- `_find_unit_pattern()` - unit pattern lookup
- `format_unit()` - unit value formatting
- `get_unit_name()` - unit display name retrieval

### 8. babel.languages (2 tests)
- `get_official_languages()` - official language codes by territory
- `get_territory_language_info()` - language information by territory

### 9. babel.support (2 tests)
- `Format.decimal()` - decimal formatting via Format class
- `Format.percent()` - percentage formatting via Format class

### 10. babel.messages.catalog (2 tests)
- `Message()` - message object creation and preservation

## Property Types Tested

1. **Invariants**
   - `distinct()` removes duplicates
   - `pathmatch()` handles exact matches
   - Currency symbols are non-empty strings
   - Locale parsing preserves language codes

2. **Roundtrips**
   - `parse_locale()` ↔ `get_locale_identifier()`
   - Locale string parsing and reconstruction

3. **Idempotency**
   - `distinct()` applied twice yields same result
   - Locale parsing of already-parsed locales

4. **Type Safety**
   - All formatting functions return strings
   - All retrieval functions return expected types
   - Numeric functions handle edge cases (0, negatives, decimals)

5. **Edge Cases**
   - Empty lists in `format_list()`
   - Single-item lists
   - Zero values in number formatting
   - Negative numbers
   - Very large numbers

## Key Findings

1. **Robust Error Handling**: Functions properly validate inputs and raise appropriate exceptions
2. **Locale Data Integrity**: CLDR data is correctly loaded and accessible
3. **Type Consistency**: All functions maintain type contracts
4. **Edge Case Handling**: Functions handle boundary conditions correctly

## Test File Location
`/Users/thanhtoantnt/self-evolve/pbt-benchmark/Babel/test_pbt_comprehensive.py`

## Running the Tests
```bash
cd /Users/thanhtoantnt/self-evolve/pbt-benchmark/Babel
python -m pytest test_pbt_comprehensive.py -v
```
