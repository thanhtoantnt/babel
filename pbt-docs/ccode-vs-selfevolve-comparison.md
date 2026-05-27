# Babel PBT Mutation Score Comparison: ccode vs self-evolve

## Setup

Both suites were tested against the **same 73 mutants** (max 6 per target)
generated from the same source files using the `pbt-scorer` framework.

| | ccode | self-evolve |
|--|--|--|
| **Branch** | `ccode` @ `thanhtoantnt/babel` | `self-evolve` @ `thanhtoantnt/babel` |
| **Test file** | `tests/test_pbt.py` | `tests/test_pbt_babel.py` |
| **Test count** | 75 | 53 |
| **Lines of code** | 1,064 | 482 |

## Overall Score

| Metric | ccode | self-evolve | Δ |
|--------|-------|-------------|---|
| **Mutation Score** | **94.0%** | **22.1%** | **-71.9pp** ❌ |
| Killed | 63 | 15 | -48 |
| Survived | 4 | 53 | +49 |
| Timeout | 0 | 0 | — |
| Error | 6 | 5 | -1 |
| Tested | 67 | 68 | +1 |
| Runtime | ~9 min | ~6 min | -3 min |

## Per-Target Breakdown

| Target | ccode | self-evolve | Δ | Winner |
|--------|-------|-------------|---|--------|
| `core.get_locale_identifier` | 100% (2/2) | 100% (4/4) | 0pp | 🤝 Tie |
| `plural.cldr_modulo` | 100% (6/6) | **0% (0/6)** | -100pp | 🏆 ccode |
| `plural.extract_operands` | 100% (6/6) | 60% (3/5) | -40pp | 🏆 ccode |
| `plural.in_range_list` | 100% (6/6) | 66.7% (4/6) | -33.3pp | 🏆 ccode |
| `plural.within_range_list` | 100% (3/3) | 33.3% (1/3) | -66.7pp | 🏆 ccode |
| `pofile.denormalize` | 100% (6/6) | **0% (0/6)** | -100pp | 🏆 ccode |
| `pofile.escape` | 100% (6/6) | **0% (0/6)** | -100pp | 🏆 ccode |
| `pofile.normalize` | 100% (6/6) | **0% (0/6)** | -100pp | 🏆 ccode |
| `pofile.unescape` | 100% (6/6) | **0% (0/6)** | -100pp | 🏆 ccode |
| `util.distinct` | 100% (4/4) | **0% (0/4)** | -100pp | 🏆 ccode |
| `util.pathmatch` | 100% (6/6) | **0% (0/6)** | -100pp | 🏆 ccode |
| `core.parse_locale` | 100% (4/4) | 40% (2/5) | -60pp | 🏆 ccode |
| `localedata.merge` | 33.3% (2/6) | 20% (1/5) | -13.3pp | 🏆 ccode |

## Summary

| Outcome | Count | Targets |
|---------|-------|---------|
| 🏆 ccode wins | 12 | All except 1 tie |
| 🤝 Tie | 1 | `core.get_locale_identifier` |
| 🏆 self-evolve wins | 0 | — |

## Analysis

### Catastrophic self-evolve failure

self-evolve achieves **7/13 targets at 0%** mutation score:
- `plural.cldr_modulo`
- `pofile.denormalize`, `pofile.escape`, `pofile.normalize`, `pofile.unescape`
- `util.distinct`, `util.pathmatch`

These are **complete coverage gaps** — the tests do not exercise these functions
at all, or only exercise trivial paths.

### Where self-evolve has partial coverage

- `plural.in_range_list` (66.7%) — best non-100% target
- `plural.extract_operands` (60%)
- `core.parse_locale` (40%)
- `plural.within_range_list` (33.3%)
- `localedata.merge` (20%)

Even these are **far below ccode's 100%** (except `localedata.merge` where
ccode also struggles at 33.3%).

### Why ccode dominates

ccode's test suite is **2.2x larger** (1,064 LOC vs 482) and has **22 more tests**
(75 vs 53). More importantly, it has **comprehensive coverage** of all target
functions with property-based tests that exercise edge cases.

self-evolve's tests appear to focus on a **narrow subset** of the API surface,
leaving entire modules (pofile, util) untested or under-tested.

### Test efficiency

Despite being smaller and faster (~6 min vs ~9 min), self-evolve's test suite
is **dramatically less effective** at catching bugs. This is the opposite of
the arrow result, where self-evolve was both smaller and more effective.

## Conclusion

**ccode dominates on Babel** with a **94.0% mutation score** vs self-evolve's 22.1%.

This is a **-71.9pp gap** — the largest observed across all projects, and the
**only project where self-evolve loses decisively**.

The self-evolve test suite has **critical coverage gaps** in:
- All `pofile.*` functions (escape/unescape/normalize/denormalize)
- All `util.*` functions (distinct/pathmatch)
- `plural.cldr_modulo`

These gaps suggest self-evolve either:
1. Did not receive clear requirements for these modules
2. Generated tests but they were not property-based or mutation-resistant
3. Focused on integration tests rather than unit-level property tests

## Recommendation

For Babel, **ccode's test suite is production-ready**. The self-evolve suite
should be **discarded or completely rewritten** with explicit coverage targets
for the missing modules.
