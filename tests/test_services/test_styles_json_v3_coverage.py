"""Defensive audit: ``data/styles.json`` must be 100% v3-clean.

This is the Phase 3.1 deliverable of the v1.70 tech-debt cleanup
roadmap. Before we retire ``_auto_promote_v2_specs`` (Phase 3.2) and
``register_v2_styles_from_json`` (Phase 3.3) the on-disk catalogue
must be proven to be all-v3 — otherwise removing those fallbacks
silently drops styles from production.

The assertion is intentionally narrow: every entry in
``data/styles.json`` must

* carry ``schema_version: 3`` (no v1 or v2 stragglers); and
* materialise into a ``StyleSpecV3`` via ``_to_v3`` (i.e. the loader
  accepts the row — not just that the schema flag is set).

Anything that diverges is a deploy blocker: prod boot fails fast in
``src/prompts/image_gen.py`` if the registry cannot be assembled, and
this CI gate guarantees we never land such a JSON without noticing.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.services.style_loader_v3 import _to_v3


_STYLES_JSON = Path(__file__).resolve().parents[2] / "data" / "styles.json"


def _load_entries() -> list[dict]:
    raw = json.loads(_STYLES_JSON.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if isinstance(raw.get("styles"), list):
            return raw["styles"]
        return list(raw.values())
    raise AssertionError(f"unexpected styles.json shape: {type(raw)!r}")


def test_styles_json_is_all_v3():
    entries = _load_entries()
    assert entries, "data/styles.json is empty"

    by_version: dict[object, list[str]] = {}
    for e in entries:
        v = e.get("schema_version")
        by_version.setdefault(v, []).append(
            str(e.get("id") or e.get("key") or "<no-id>"),
        )

    non_v3 = {v: keys for v, keys in by_version.items() if v != 3}
    assert not non_v3, (
        "data/styles.json must be 100% v3 before Phase 3 cleanups can "
        f"land. Non-v3 entries: {non_v3}"
    )


def test_every_entry_promotes_to_v3():
    entries = _load_entries()
    failures: list[tuple[str, str]] = []
    promoted = 0
    for e in entries:
        key = str(e.get("id") or e.get("key") or "<no-id>")
        try:
            spec = _to_v3(e)
        except Exception as exc:  # noqa: BLE001 — test wants every reason
            failures.append((key, repr(exc)))
            continue
        if spec is None:
            failures.append((key, "_to_v3 returned None"))
            continue
        promoted += 1

    assert not failures, (
        "data/styles.json has entries that fail _to_v3 — these would "
        "silently disappear if Phase 3 retired the v1/v2 fallbacks:\n"
        + "\n".join(f"  {k}: {reason}" for k, reason in failures[:10])
    )
    assert promoted == len(entries), (
        f"only {promoted}/{len(entries)} styles materialised — investigate"
    )
