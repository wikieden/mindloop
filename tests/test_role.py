"""4b — RoleBundle (D-O): reference-based YAML bundle, double-key grant
(effective = owner grant ∩ bundle need), provenance-vetted activation."""

from __future__ import annotations

from bodylink import MockBody

from mindloop import Phylax, Policy, RoleBundle, effective_verbs, load_role


def test_builtin_roles_load() -> None:
    for name in ("cleaner", "host", "guide"):
        b = load_role(name)
        assert b.role == name
        assert b.verbs  # every builtin declares a verb need
        assert b.provenance == "builtin"


def test_effective_verbs_is_grant_intersect_need() -> None:
    b = load_role("cleaner")
    manifest = MockBody().capabilities()
    eff = effective_verbs(b, manifest)
    assert eff <= manifest.verb_names()  # never wider than the body grants
    assert eff <= b.verbs  # never wider than the role needs
    assert "sweep" in eff  # cleaner needs sweep and g1d grants it


def test_bundle_cannot_self_grant_unknown_verbs() -> None:
    b = RoleBundle(
        role="evil",
        verbs=frozenset({"navigate", "self_destruct"}),
        provenance="builtin",
    )
    eff = effective_verbs(b, MockBody().capabilities())
    assert "self_destruct" not in eff  # not granted by the body -> inert


def test_unvetted_bundle_is_refused() -> None:
    gate = Phylax(Policy())  # trusts only "builtin"
    evil = RoleBundle(role="cleaner", verbs=frozenset({"navigate"}), provenance="random-url")
    assert not gate.vet_role(evil)
    assert gate.vet_role(load_role("cleaner"))


def test_host_role_references_menu_knowledge() -> None:
    b = load_role("host")
    assert b.knowledge.get("menu") == "builtin"  # D-K KB referenced, not embedded
