"""Menu / recipe knowledge base — extensible, provenance-vetted (D-K).

Static world knowledge ("a latte contains milk") — the same in every home, so it
does **not** live in tempomem's scene graph. Mirrors bodylink's `load_manifest`
shape: builtin dict fallback + an owner-supplied YAML path, lazy PyYAML.

Trust model (D-K, reusing the skill-card primitive): every entry carries a
``provenance``; `MenuKB.allergens` returns a *known* allergen set only for entries
whose provenance the caller trusts. An unvetted entry reads as **unknown** (None)
— it can add caution, never remove it. The allergen invariant itself (block when
``allergens(item) ∩ allergic_to(person) ≠ ∅``, fail-closed on unknown) is enforced
by `Phylax`, not here (D-L: universal invariant vs per-role procedure). Stdlib-only.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

_log = logging.getLogger("mindloop.menu")

# name -> (allergens, provenance). The builtin menu is deliberately small — an
# owner extends/overrides it with a YAML, exactly like a custom body manifest.
_BUILTIN_MENU: dict[str, tuple[frozenset[str], str]] = {
    "water": (frozenset(), "builtin"),
    "green tea": (frozenset(), "builtin"),
    "black tea": (frozenset(), "builtin"),
    "coffee": (frozenset(), "builtin"),
    "espresso": (frozenset(), "builtin"),
    "latte": (frozenset({"milk"}), "builtin"),
    "cappuccino": (frozenset({"milk"}), "builtin"),
    "hot chocolate": (frozenset({"milk"}), "builtin"),
    "orange juice": (frozenset(), "builtin"),
    "soy milk": (frozenset({"soy"}), "builtin"),
    "peanut smoothie": (frozenset({"peanut"}), "builtin"),
}


class MenuKB:
    """Recipe lookup: drink/dish name -> allergen set, gated by entry provenance."""

    def __init__(self, entries: Mapping[str, tuple[frozenset[str], str]]) -> None:
        self._entries = {k.lower(): v for k, v in entries.items()}

    def allergens(self, item: str, *, trusted: frozenset[str]) -> frozenset[str] | None:
        """The item's allergen set, or **None when unknown** — item absent, or its
        entry's provenance is not in `trusted` (an unreviewed recipe never counts
        as confirmed allergen-free, D-K)."""
        entry = self._entries.get(item.lower())
        if entry is None:
            return None
        allergens, provenance = entry
        if provenance not in trusted:
            _log.warning(
                "menu entry %r has untrusted provenance %r — treating allergens as unknown",
                item,
                provenance,
            )
            return None
        return allergens

    def __contains__(self, item: str) -> bool:
        return item.lower() in self._entries


def load_menu(name_or_path: str | Path = "builtin") -> MenuKB:
    """Resolve a `MenuKB` by builtin name or external YAML path.

    The YAML shape is ``{items: [{name, allergens?: [...], provenance?}, ...]}``;
    entries default to ``provenance: owner``. Mirrors `bodylink.load_manifest`.
    """
    if name_or_path == "builtin":
        return MenuKB(_BUILTIN_MENU)
    path = Path(name_or_path)
    try:
        import yaml  # lazy: PyYAML only needed for external menus
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("loading a YAML menu requires PyYAML (pip install pyyaml)") from e
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = dict(_BUILTIN_MENU)
    for item in data.get("items", ()):
        entries[str(item["name"]).lower()] = (
            frozenset(str(a) for a in item.get("allergens", ())),
            str(item.get("provenance", "owner")),
        )
    return MenuKB(entries)
