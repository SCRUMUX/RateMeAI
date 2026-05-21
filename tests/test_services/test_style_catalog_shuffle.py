"""Tests for the per-seed catalog shuffle (v1.76).

The web ``GET /catalog/styles`` endpoint serves a deterministic
per-caller permutation of the styles list so different users do not
see identical top-N rows. The actual shuffle helper lives in
:func:`src.services.style_catalog.shuffle_styles_for_seed`; this
module exercises its contract:

1. Empty / ``None`` seed → original list (back-compat for bot,
   admin and scenario consumers that never opt in).
2. Same seed → same ordering, every call (UX: no jumping on
   refresh).
3. Different seeds → different orderings (the whole point of the
   feature — different users do not see identical top-2 cards).
4. The original list is **not** mutated (pure-function contract).
5. The shuffle covers the entire list (no entries dropped / dupes).
6. The function works for arbitrary types (dicts, tuples, primitives).
"""

from __future__ import annotations

import string

from src.services.style_catalog import (
    get_catalog_json,
    shuffle_styles_for_seed,
)


# ---------------------------------------------------------------------------
# unit tests on the helper
# ---------------------------------------------------------------------------


class TestShuffleStylesForSeed:
    def test_none_seed_returns_original_order(self):
        items = [{"k": 1}, {"k": 2}, {"k": 3}, {"k": 4}]
        out = shuffle_styles_for_seed(items, None)
        assert out == items

    def test_empty_seed_returns_original_order(self):
        items = list(range(10))
        assert shuffle_styles_for_seed(items, "") == items

    def test_empty_list_handled(self):
        assert shuffle_styles_for_seed([], "seed") == []

    def test_same_seed_yields_same_order(self):
        items = list(string.ascii_letters)
        a = shuffle_styles_for_seed(items, "user:abcd-1234")
        b = shuffle_styles_for_seed(items, "user:abcd-1234")
        assert a == b

    def test_different_seeds_yield_different_orders(self):
        items = list(range(60))
        a = shuffle_styles_for_seed(items, "user:abcd-1234")
        b = shuffle_styles_for_seed(items, "user:efgh-5678")
        assert a != b

    def test_shuffle_does_not_mutate_input(self):
        items = list(range(20))
        snapshot = list(items)
        _ = shuffle_styles_for_seed(items, "user:1")
        assert items == snapshot

    def test_shuffle_returns_new_list_when_seed_present(self):
        items = list(range(10))
        out = shuffle_styles_for_seed(items, "seed")
        assert out is not items

    def test_shuffle_returns_a_copy_when_seed_absent(self):
        """Even with no seed the helper returns a fresh list so the
        caller can safely mutate it (matches the same-shape contract
        of the seeded branch)."""
        items = list(range(10))
        out = shuffle_styles_for_seed(items, None)
        assert out is not items

    def test_shuffle_preserves_full_set(self):
        items = list(range(100))
        out = shuffle_styles_for_seed(items, "user:zzz")
        assert sorted(out) == items
        assert len(out) == len(items)

    def test_works_on_dicts(self):
        items = [{"key": f"s{i}"} for i in range(30)]
        out = shuffle_styles_for_seed(items, "ip:8.8.8.8:2026-05-21")
        assert {d["key"] for d in out} == {d["key"] for d in items}
        # extremely small chance of an identity permutation on 30
        # entries (~ 1 / 30!); flake-proof.
        assert out != items

    def test_unique_seeds_produce_diverse_top_n(self):
        """Strong-er contract: for many distinct seeds the top-2
        entries are not always the same. This is the actual product
        property the feature is meant to enforce — two different
        users should not consistently see the same top-2 styles."""
        items = [{"key": f"style_{i:03d}"} for i in range(60)]
        top_pairs: set[tuple[str, str]] = set()
        for i in range(50):
            seed = f"user:{i:08x}-aaaa-bbbb-cccc-dddddddddddd"
            ordering = shuffle_styles_for_seed(items, seed)
            top_pairs.add((ordering[0]["key"], ordering[1]["key"]))
        # 50 distinct seeds against a 60-item list should produce
        # well over a dozen distinct top-2 pairs in practice. The
        # threshold is generous to stay stable across Python's
        # ``random.Random`` algorithm changes; the failure scenario
        # we are guarding against is "every user sees the same top-2".
        assert len(top_pairs) >= 20


# ---------------------------------------------------------------------------
# integration with get_catalog_json
# ---------------------------------------------------------------------------


class TestGetCatalogJsonShuffleSeed:
    def test_default_call_is_canonical_order(self):
        """No seed → canonical ``data/styles.json`` ordering."""
        a = get_catalog_json("dating")
        b = get_catalog_json("dating")
        assert a == b
        # canonical order: the first dating style is `paris_eiffel`
        # (it is the first dating row in ``data/styles.json``). This
        # pin keeps the contract honest for any internal consumer
        # that still relies on the canonical order.
        assert a[0]["key"] == "paris_eiffel"

    def test_seeded_call_reorders(self):
        canonical = get_catalog_json("dating")
        shuffled = get_catalog_json("dating", shuffle_seed="user:abcd-1234")
        # same set of styles, different order. With ~74 dating
        # styles the chance of an identity permutation is 1 / 74!.
        assert {s["key"] for s in shuffled} == {s["key"] for s in canonical}
        assert shuffled != canonical

    def test_different_seeds_yield_different_orderings(self):
        a = get_catalog_json("dating", shuffle_seed="user:aaaa")
        b = get_catalog_json("dating", shuffle_seed="user:bbbb")
        assert a != b

    def test_same_seed_is_stable(self):
        a = get_catalog_json("cv", shuffle_seed="user:stable")
        b = get_catalog_json("cv", shuffle_seed="user:stable")
        assert a == b

    def test_seed_applied_across_modes_independently(self):
        """Seed applies per mode — the dating shuffle should not
        leak into the cv shuffle (different lists)."""
        dating = get_catalog_json("dating", shuffle_seed="user:x")
        cv = get_catalog_json("cv", shuffle_seed="user:x")
        # The two lists have disjoint keys (cv styles are not dating
        # styles); we only assert no entries cross-pollinate.
        d_keys = {s["key"] for s in dating}
        c_keys = {s["key"] for s in cv}
        assert d_keys.isdisjoint(c_keys)
