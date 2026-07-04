"""Episteme — procedural knowledge as data (P2, the skill-card library).

A `SkillCard` is a piece of how-to knowledge (do the laundry, cook pasta) stored
as **flat steps + rules** (K2 — a DAG is reserved via `schema_version`, not built
yet). The card is the *declarative* knowledge; turning it into a dispatchable
verb sequence is `instantiate()`, which:

  1. resolves which `Rule`s fire from the situation **slots** (e.g. ``fabric=wool``),
  2. overlays each firing rule's params onto the matching steps,
  3. binds each step's object slot to a concrete mention, and
  4. drops any step whose verb the body's `CapabilityManifest` does not declare (D3).

The output is a `Command` tuple — the **same** intermediate representation the LLM
planner emits (`plan.Command`) — so it flows straight into `plan.compile_commands`
(node-id binding B9, SubTask metadata). Skill cards and the LLM planner are two
sources of the same verb sequence; `SkillCardPlanner` tries the library first and
falls back to an inner LLM `Planner` (flagged low-confidence) when no card fits.

Stdlib-only at the core: cards are built from plain dicts (`SkillCard.from_dict`),
so tests stay network- and dependency-free. The optional YAML loader
(`load_cards`) lazy-imports PyYAML (the ``skills`` extra) and is the only place a
third-party dep appears. Retrieval is BYO-encoder (like `tempomem.query`): pass an
`Encoder` for semantic search, otherwise keyword overlap.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .plan import Command

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    import numpy as np

    from .execute import CapabilityManifest

_log = logging.getLogger("mindloop.episteme")

_SCHEMA_VERSION = 1


# --------------------------------------------------------------------------- #
# value types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class SkillStep:
    """One flat step of a card: a verb + an object slot + literal params.

    ``target`` names *what the verb acts on*: a slot key (resolved from the
    situation slots at instantiate time, e.g. ``"appliance"``), or a literal
    object mention. Empty means the verb takes no object (e.g. ``detect``).
    ``params`` are step-level defaults; firing `Rule`s overlay on top.
    """

    verb: str
    target: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Rule:
    """A conditional param overlay: when the situation matches, set params.

    ``when`` is a set of ``slot == value`` conditions (all must hold). ``set_params``
    is overlaid onto steps whose verb equals ``target_verb`` (empty ⇒ every step).
    Example (laundry): ``when={"fabric": "wool"}``, ``target_verb="operate_appliance"``,
    ``set_params={"program": "delicate", "temperature_c": 30}``.
    """

    when: dict[str, str] = field(default_factory=dict)
    set_params: dict[str, Any] = field(default_factory=dict)
    target_verb: str = ""

    def fires(self, slots: Mapping[str, str]) -> bool:
        """True if every `when` condition is satisfied by `slots`."""
        return all(slots.get(k) == v for k, v in self.when.items())


@dataclass(frozen=True, slots=True)
class SkillCard:
    """Procedural knowledge for one task category, as flat steps + rules (K2).

    ``category`` is the object/domain the card is about (``"laundry"``,
    ``"pasta"``) and doubles as the default object mention for steps whose
    ``target`` is empty-but-object-bearing. ``safety`` holds policy annotations the
    Phylax tier (P3) gates on — a card carrying ``safety`` from an untrusted source
    must be signed/reviewed before it is honored (P3). ``provenance`` records where
    the card came from (``"builtin"``, a URL, a signature).
    """

    id: str
    category: str = ""
    preconditions: tuple[str, ...] = ()
    rules: tuple[Rule, ...] = ()
    steps: tuple[SkillStep, ...] = ()
    failure_hints: tuple[str, ...] = ()
    safety: dict[str, Any] = field(default_factory=dict)
    provenance: str = "builtin"
    schema_version: int = _SCHEMA_VERSION

    @property
    def slot_vocab(self) -> dict[str, str]:
        """Every ``value -> slot`` pair mentioned by this card's rule conditions.

        Used by the default slot extractor: a word in the instruction that equals
        one of these values is read as that slot (``"wool" -> fabric=wool``).
        """
        return {v: k for r in self.rules for k, v in r.when.items()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SkillCard:
        """Build a `SkillCard` from a plain dict (the YAML/JSON shape). Stdlib."""
        steps = tuple(
            SkillStep(
                verb=str(s["verb"]),
                target=str(s.get("target", "")),
                params=dict(s.get("params", {})),
            )
            for s in data.get("steps", ())
        )
        rules = tuple(
            Rule(
                when={str(k): str(v) for k, v in r.get("when", {}).items()},
                set_params=dict(r.get("set_params", {})),
                target_verb=str(r.get("target_verb", "")),
            )
            for r in data.get("rules", ())
        )
        return cls(
            id=str(data["id"]),
            category=str(data.get("category", "")),
            preconditions=tuple(data.get("preconditions", ())),
            rules=rules,
            steps=steps,
            failure_hints=tuple(data.get("failure_hints", ())),
            safety=dict(data.get("safety", {})),
            provenance=str(data.get("provenance", "builtin")),
            schema_version=int(data.get("schema_version", _SCHEMA_VERSION)),
        )


# --------------------------------------------------------------------------- #
# instantiation: card + situation -> Command sequence (feeds compile_commands)
# --------------------------------------------------------------------------- #
def extract_slots(instruction: str, card: SkillCard) -> dict[str, str]:
    """Read situation slots from the instruction using the card's rule vocab.

    Deterministic and case-insensitive: any whitespace token of `instruction`
    that equals a value named in some rule's ``when`` becomes that slot. So
    ``"wash the wool sweater"`` against a card with ``when={"fabric": "wool"}``
    yields ``{"fabric": "wool"}``. A bespoke extractor can be supplied to
    `SkillCardPlanner` for richer parsing; this is the zero-dependency default.
    """
    vocab = card.slot_vocab
    slots: dict[str, str] = {}
    for tok in instruction.lower().replace(",", " ").split():
        word = tok.strip(".!?;:\"'")
        if word in vocab:
            slots[vocab[word]] = word
    return slots


def instantiate(
    card: SkillCard,
    manifest: CapabilityManifest,
    *,
    slots: Mapping[str, str] | None = None,
    preferences: Mapping[str, Any] | None = None,
) -> tuple[Command, ...]:
    """Expand a `SkillCard` into a dispatchable `Command` sequence (B9 via compile).

    For each step: overlay every firing `Rule`'s params (rules win over the
    step's own params), then overlay matching L5 `preferences` (preferences win
    last — the user's stated choice tops a generic rule). Resolve the step's
    object slot to a mention (a slot value, else the literal `target`, else the
    card `category`). Drop a step whose verb the body does not declare (D3,
    logged). The returned `Command`s carry resolved `params`; node-id binding and
    SubTask metadata happen downstream in `plan.compile_commands`.
    """
    slots = dict(slots or {})
    supported = manifest.verb_names()
    firing = tuple(r for r in card.rules if r.fires(slots))
    commands: list[Command] = []

    for step in card.steps:
        if step.verb != "speak" and step.verb not in supported:
            _log.warning(
                "skill card %r step verb %r unsupported by body %r — dropped",
                card.id,
                step.verb,
                manifest.body_profile.profile_id,
            )
            continue
        params: dict[str, Any] = dict(step.params)
        for rule in firing:
            if rule.target_verb in ("", step.verb):
                params.update(rule.set_params)
        if preferences:
            known = manifest_param_keys(manifest, step.verb)
            params.update({k: v for k, v in preferences.items() if k in known})
        mention = _resolve_mention(step.target, slots, card.category)
        args = (mention,) if mention else ()
        commands.append(Command(verb=step.verb, args=args, params=params))
    return tuple(commands)


def manifest_param_keys(manifest: CapabilityManifest, verb: str) -> frozenset[str]:
    """The param keys a body declares for `verb` (so preferences only set known params)."""
    for spec in manifest.verbs:
        if spec.name == verb:
            return frozenset(spec.params)
    return frozenset()


def _resolve_mention(target: str, slots: Mapping[str, str], category: str) -> str:
    """Resolve a step's object slot to a concrete mention.

    A slot key resolves to its situation value; the literal ``"{category}"`` token
    resolves to the card category; any other non-empty `target` is a literal
    mention (object name, or a `speak` message); an empty target means the verb
    takes no object (``detect``) and yields no arg.
    """
    if target in slots:
        return slots[target]
    if target == "{category}":
        return category
    return target


# --------------------------------------------------------------------------- #
# library + retrieval (BYO encoder, like tempomem.query)
# --------------------------------------------------------------------------- #
class SkillLibrary:
    """An in-memory collection of `SkillCard`s with id lookup + retrieval.

    `retrieve` ranks cards against an instruction: semantic cosine if an
    `Encoder` is supplied (BYO, like `tempomem`), else keyword overlap over the
    card id/category/step verbs. No encoder and no keyword hit ⇒ empty, and the
    caller falls back to the LLM planner.
    """

    def __init__(self, cards: Sequence[SkillCard] = ()) -> None:
        self._cards: dict[str, SkillCard] = {c.id: c for c in cards}

    def __len__(self) -> int:
        return len(self._cards)

    def add(self, card: SkillCard) -> None:
        self._cards[card.id] = card

    def get(self, card_id: str) -> SkillCard | None:
        return self._cards.get(card_id)

    def cards(self) -> tuple[SkillCard, ...]:
        return tuple(self._cards.values())

    def retrieve(
        self, instruction: str, *, encoder: Any | None = None, k: int = 1
    ) -> list[SkillCard]:
        """Return the top-`k` cards most relevant to `instruction` (best first)."""
        if not self._cards:
            return []
        if encoder is not None:
            ranked = self._semantic_rank(instruction, encoder)
        else:
            ranked = self._keyword_rank(instruction)
        return [c for score, c in ranked if score > 0][:k]

    def _keyword_rank(self, instruction: str) -> list[tuple[float, SkillCard]]:
        words = set(instruction.lower().replace(",", " ").split())
        scored: list[tuple[float, SkillCard]] = []
        for card in self._cards.values():
            # verbs + rule values stay whole terms (an "open_door" step must not
            # leak an "open" token); only the *naming* fields are tokenized so a
            # hyphen/slash-joined id or category ("learned/put-mug-on-shelf")
            # still matches instruction words.
            tokens = {s.verb.lower() for s in card.steps if s.verb}
            tokens |= {v.lower() for r in card.rules for v in r.when.values() if v}
            for name in (card.id, card.category):
                tokens |= {tok for tok in re.split(r"[^a-z0-9]+", name.lower()) if tok}
            overlap = len(words & tokens)
            scored.append((float(overlap), card))
        scored.sort(key=lambda sc: sc[0], reverse=True)
        return scored

    def _semantic_rank(self, instruction: str, encoder: Any) -> list[tuple[float, SkillCard]]:
        import numpy as np

        def _norm(v: np.ndarray) -> np.ndarray:
            n = float(np.linalg.norm(v))
            return v / n if n else v

        q = _norm(np.asarray(encoder.encode_text(instruction), dtype="float32"))
        scored: list[tuple[float, SkillCard]] = []
        for card in self._cards.values():
            doc = f"{card.category} {card.id} " + " ".join(s.verb for s in card.steps)
            d = _norm(np.asarray(encoder.encode_text(doc), dtype="float32"))
            scored.append((float(q @ d), card))
        scored.sort(key=lambda sc: sc[0], reverse=True)
        return scored


def load_cards(path: str | Path) -> list[SkillCard]:
    """Load `SkillCard`s from a YAML file or a directory of ``*.yaml`` files.

    Lazy-imports PyYAML (the ``skills`` extra). A file may hold a single card
    mapping or a list of them. Stdlib callers that want zero deps build cards via
    `SkillCard.from_dict` instead.
    """
    try:
        import yaml
    except ModuleNotFoundError as e:  # pragma: no cover - exercised via extra
        raise RuntimeError(
            "load_cards needs PyYAML — install the 'skills' extra: pip install 'mindloop[skills]'"
        ) from e
    from pathlib import Path as _Path

    p = _Path(path)
    files = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    cards: list[SkillCard] = []
    for f in files:
        loaded = yaml.safe_load(f.read_text(encoding="utf-8"))
        items = loaded if isinstance(loaded, list) else [loaded]
        cards.extend(SkillCard.from_dict(item) for item in items if item)
    return cards


# --------------------------------------------------------------------------- #
# the planner: library-first, LLM fallback (flagged low-confidence)
# --------------------------------------------------------------------------- #
class SkillCardPlanner:
    """A `plan.Planner` that plans from the skill library, falling back to an LLM.

    `plan` retrieves the best-matching card for the instruction and instantiates
    it against the body manifest (slots extracted via `extract_slots` or a
    supplied `slot_extractor`, L5 `preferences` overlaid). If no card fits — or
    the card expands to nothing — it defers to the inner `fallback` planner
    (general LLM knowledge), logging that the result is **low-confidence** (P2
    contract: a no-card plan is flagged). With no fallback, returns ``()``.
    """

    def __init__(
        self,
        library: SkillLibrary,
        manifest: CapabilityManifest,
        *,
        fallback: Any | None = None,
        encoder: Any | None = None,
        preferences: Mapping[str, Any] | None = None,
        slot_extractor: Any | None = None,
        policy: Any | None = None,
    ) -> None:
        self._lib = library
        self._manifest = manifest
        self._fallback = fallback
        self._encoder = encoder
        self._prefs = dict(preferences or {})
        self._extract = slot_extractor or extract_slots
        # Optional Phylax: vets a card before it is honored — a card carrying
        # `safety:` annotations from an untrusted provenance is refused (P3).
        self._policy = policy

    def plan(self, instruction: str, context: str) -> tuple[Command, ...]:
        hits = self._lib.retrieve(instruction, encoder=self._encoder, k=1)
        if hits and (self._policy is None or self._policy.vet_card(hits[0])):
            card = hits[0]
            slots = self._extract(instruction, card)
            commands = instantiate(card, self._manifest, slots=slots, preferences=self._prefs)
            if commands:
                _log.info("planned from skill card %r (slots=%s)", card.id, slots)
                return commands
        if self._fallback is not None:
            _log.warning("no skill card for %r — LLM fallback (low-confidence)", instruction)
            return self._fallback.plan(instruction, context)
        _log.warning("no skill card for %r and no fallback — empty plan", instruction)
        return ()
