"""RoleBundle — packaged service roles, double-key granted (4b, D-O).

A home robot **holds a set** of granted roles and **activates one per task**
(`SafetyContext.robot_service`, D-A) — Unix-groups style: permissions never
union. A bundle is a *manifest of references* (Episteme card ids, a knowledge
KB name, a verb need-list), mirroring `load_manifest`/`load_menu`: builtin
dict fallback + owner YAML, lazy PyYAML.

Trust model (D-O):
* **Double-key**: the bundle declares what the role *needs*; the owner-side
  grant (body manifest, `Policy`) declares what it *gets*; effective capability
  is the **intersection** (`effective_verbs`). A malicious bundle claiming
  extra verbs or regions is inert — nothing granted, nothing gained.
* **Provenance-vetted activation**: `Phylax.vet_role` refuses a bundle whose
  `provenance` is untrusted, same primitive as skill cards (P3) and menu
  entries (D-K).

Role-set *changes* (grant/revoke) are owner-privileged, task-boundary-only,
zero-inheritance, and never reachable from a replan or a Clarifier answer —
enforced by the callers that manage the granted set, not by this data type.
Stdlib-only.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .execute import CapabilityManifest

_log = logging.getLogger("mindloop.role")

# Builtin role bundles — deliberately small; an owner extends with YAML.
_BUILTIN_ROLES: dict[str, dict[str, object]] = {
    "cleaner": {
        "verbs": [
            "navigate",
            "sweep",
            "vacuum",
            "mop",
            "warn_wet_floor",
            "wipe",
            "restock",
            "dispose",
            "grasp",
            "place",
            "detect",
        ],
        "skill_cards": ["cleaner-first-entry-knock"],
        "knowledge": {},
    },
    "host": {
        "verbs": [
            "navigate",
            "greet",
            "take_order",
            "offer",
            "deliver",
            "pour",
            "grasp",
            "place",
            "detect",
        ],
        "skill_cards": ["receptionist-first-visit-allergy-ask"],
        "knowledge": {"menu": "builtin"},
    },
    "guide": {
        "verbs": ["navigate", "present", "detect"],
        "skill_cards": [],
        "knowledge": {},
    },
}


@dataclass(frozen=True, slots=True)
class RoleBundle:
    """One packaged service role: verb needs + referenced cards/knowledge."""

    role: str
    verbs: frozenset[str] = frozenset()
    skill_cards: tuple[str, ...] = ()  # Episteme card ids — referenced, never embedded
    knowledge: Mapping[str, str] = field(default_factory=dict)  # e.g. {"menu": "builtin"}
    provenance: str = "builtin"


def effective_verbs(bundle: RoleBundle, manifest: CapabilityManifest) -> frozenset[str]:
    """Double-key grant (D-O): what the role may plan = need ∩ body grant.

    A bundle can only *narrow* what the body already declares — it can never
    self-grant a verb the manifest (or owner policy) does not give.
    """
    return bundle.verbs & manifest.verb_names()


def load_role(name_or_path: str | Path) -> RoleBundle:
    """Resolve a `RoleBundle` by builtin name or external YAML path.

    YAML shape: ``{role, verbs: [...], skill_cards?: [...], knowledge?: {...},
    provenance?}``; external bundles default to ``provenance: owner``.
    """
    if isinstance(name_or_path, str) and name_or_path in _BUILTIN_ROLES:
        data = _BUILTIN_ROLES[name_or_path]
        return RoleBundle(
            role=name_or_path,
            verbs=frozenset(str(v) for v in data["verbs"]),  # type: ignore[union-attr]
            skill_cards=tuple(str(c) for c in data.get("skill_cards", ())),  # type: ignore[union-attr]
            knowledge={str(k): str(v) for k, v in data.get("knowledge", {}).items()},  # type: ignore[union-attr]
            provenance="builtin",
        )
    path = Path(name_or_path)
    try:
        import yaml  # lazy: PyYAML only needed for external bundles
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("loading a YAML role bundle requires PyYAML") from e
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return RoleBundle(
        role=str(data["role"]),
        verbs=frozenset(str(v) for v in data.get("verbs", ())),
        skill_cards=tuple(str(c) for c in data.get("skill_cards", ())),
        knowledge={str(k): str(v) for k, v in data.get("knowledge", {}).items()},
        provenance=str(data.get("provenance", "owner")),
    )
