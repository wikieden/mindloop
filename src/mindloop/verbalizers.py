"""NVIDIA Cosmos integration — Cosmos Reason as a Chronotope `Verbalizer`.

Cosmos Reason is NVIDIA's Physical-AI reasoning vision-language model family:
Cosmos-Reason1 (7B), Cosmos Reason 2 (2B/8B/32B), and the "Cosmos 3 Reasoner"
inside the unified Cosmos 3 world-foundation-model family. It is a chain-of-
thought reasoner, not a detector — it does **not** emit world-frame 3D
detections, so it is not a `PerceptionAdapter`. It *is* a strong `answer()`
backend: it reads the serialized scene graph and reasons about it with physical
common sense.

This wraps any OpenAI-compatible NVIDIA NIM endpoint (the hosted
build.nvidia.com gateway, or a self-hosted NIM microservice). Uses only the
standard library (`urllib`). The model id is configurable, so the same wrapper
targets Cosmos Reason 1/2 or the Cosmos 3 Reasoner NIM.

    from tempomem import TempoMem
    from mindloop import CosmosReasonVerbalizer

    vb = CosmosReasonVerbalizer(model="nvidia/cosmos-reason2-8b")  # NVIDIA_API_KEY env
    mem = TempoMem.open("room.smem", embedding_dim=512, verbalizer=vb)
    print(mem.answer("what is on the kitchen table?"))
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from tempomem import QueryError

if TYPE_CHECKING:
    from tempomem import Verbalizer

_log = logging.getLogger("mindloop.verbalizers")

# NVIDIA-hosted, OpenAI-compatible NIM gateway (build.nvidia.com).
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
# A confirmed published NIM. For the unified Cosmos 3 family the reasoning piece
# ships as the "Cosmos 3 Reasoner" NIM — set ``model=`` to its id once GA.
DEFAULT_MODEL = "nvidia/cosmos-reason2-8b"

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
# An unterminated <think> (response truncated by max_tokens) — drop to the end.
_OPEN_THINK_RE = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)
_ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"</?(?:think|answer)>", re.IGNORECASE)

Transport = Callable[[dict[str, Any]], dict[str, Any]]


def strip_reasoning(text: str) -> str:
    """Extract the final answer from a Cosmos chain-of-thought response.

    Cosmos Reason emits ``<think>...</think>`` reasoning and (Reason1) wraps the
    final answer in ``<answer>...</answer>``. Strip the reasoning *first* (so an
    ``<answer>`` quoted inside a think block can't win), tolerate an unterminated
    ``<think>`` from a truncated reply, then return the ``<answer>`` body if
    present. Falls back to the de-tagged text so the result is never empty when
    the model did produce content.
    """
    cleaned = _OPEN_THINK_RE.sub("", _THINK_RE.sub("", text))
    m = _ANSWER_RE.search(cleaned)
    if m and m.group(1).strip():
        return m.group(1).strip()
    out = _TAG_RE.sub("", cleaned).strip()
    return out or _TAG_RE.sub("", text).strip()


class CosmosReasonVerbalizer:
    """`Verbalizer` backed by an NVIDIA Cosmos Reason NIM (OpenAI-compatible).

    Targets a hosted (build.nvidia.com) or self-hosted NIM. Set ``model=`` to the
    desired Cosmos Reason / Cosmos 3 Reasoner id. Reads the API key from
    ``api_key=`` or the ``NVIDIA_API_KEY`` environment variable.

    ``transport`` is an injection seam for testing: a callable taking the request
    payload dict and returning the parsed JSON response dict. It defaults to a
    stdlib-``urllib`` POST, so this stays dependency-free.

    Security: ``base_url`` is caller-supplied trusted input (your own NIM
    endpoint). Do not point it at an untrusted/user-derived URL — the POST goes
    wherever it says (SSRF), and the ``NVIDIA_API_KEY`` bearer token rides along.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 60.0,
        max_tokens: int = 1024,
        temperature: float = 0.6,
        extra_body: dict[str, Any] | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Extra OpenAI-compatible request fields merged into every payload — e.g.
        # ``{"chat_template_kwargs": {"enable_thinking": False}}`` to turn off a
        # thinking model's chain-of-thought (Qwen3.x) for clean structured output.
        self._extra_body = dict(extra_body or {})
        self._api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        self._transport = transport or self._http_post

    def complete(self, prompt: str) -> str:
        """Send `prompt` to the Cosmos NIM and return the cleaned answer text."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            **self._extra_body,
        }
        data = self._transport(payload)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise QueryError(f"Cosmos NIM returned an unexpected response: {data!r}") from e
        return strip_reasoning(text)

    def _http_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise QueryError(
                "CosmosReasonVerbalizer needs an API key: pass api_key= or set NVIDIA_API_KEY"
            )
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            # URLError: transport failure. JSONDecodeError: 200-OK non-JSON body
            # (e.g. an HTML error page from a reverse proxy) — both must surface
            # as QueryError, never a raw ValueError, per the answer() contract.
            raise QueryError(f"Cosmos NIM request failed: {e}") from e


# A callback fired when the serving backend changes: (old_index, new_index, reason).
SwitchHook = Callable[[int, int, str], None]


class FailoverVerbalizer:
    """A `Verbalizer` that fails over from a primary backend to on-body fallbacks (P7).

    Wraps an ordered list of `Verbalizer`s: ``backends[0]`` is the primary (e.g. a
    remote `CosmosReasonVerbalizer`), the rest are fallbacks (e.g. an on-body LLM at
    ``http://localhost:.../v1``). `complete` tries them in order and returns the
    first success; a backend that raises `QueryError` (a transport failure — the
    network down, the server unreachable) is skipped to the next.

    **Hysteresis** (so a flapping link does not thrash): when the primary fails, it
    is put on a `cooldown` of N subsequent calls during which it is tried **last**
    (fallbacks served first) — not skipped entirely, so it is still the last-resort
    if every fallback is also down. A primary success clears the cooldown. The
    counter is call-based (deterministic, no wall-clock) so it is fully testable.

    Reuses the `Verbalizer` seam, so wrapping the reasoner/planner verbalizer makes
    the whole LLM path failover-capable with **no brain change**. `mode` /
    `active_index` expose which backend is serving (telemetry); `on_switch` fires on
    a change.
    """

    def __init__(
        self,
        backends: Sequence[Verbalizer],
        *,
        cooldown: int = 8,
        on_switch: SwitchHook | None = None,
    ) -> None:
        if not backends:
            raise ValueError("FailoverVerbalizer needs at least one backend")
        self._backends = list(backends)
        self._cooldown = max(0, cooldown)
        self._on_switch = on_switch
        self._skip_primary_for = 0  # calls remaining to demote the primary
        self._active = 0  # index currently serving (telemetry)

    @property
    def active_index(self) -> int:
        """Index of the backend that served the last `complete` (0 = primary)."""
        return self._active

    @property
    def mode(self) -> str:
        """``"primary"`` when the primary is serving, else ``"fallback"``."""
        return "primary" if self._active == 0 else "fallback"

    def _order(self) -> list[int]:
        """The backend indices to try this call (primary demoted while cooling)."""
        n = len(self._backends)
        if self._skip_primary_for > 0:
            self._skip_primary_for -= 1
            return [*range(1, n), 0]  # fallbacks first, primary last-resort
        return list(range(n))

    def _note_active(self, idx: int, reason: str) -> None:
        if idx != self._active and self._on_switch is not None:
            self._on_switch(self._active, idx, reason)
        self._active = idx

    def complete(self, prompt: str) -> str:
        """Return the first backend's completion; fail over on `QueryError`."""
        last_err: QueryError | None = None
        for idx in self._order():
            try:
                out = self._backends[idx].complete(prompt)
            except QueryError as e:
                last_err = e
                _log.warning("verbalizer backend %d failed, failing over: %s", idx, e)
                if idx == 0:
                    self._skip_primary_for = self._cooldown  # demote the primary
                continue
            if idx == 0:
                self._skip_primary_for = 0  # primary healthy again
            self._note_active(idx, "recovered" if idx == 0 else "failover")
            return out
        raise QueryError(
            f"all {len(self._backends)} verbalizer backends failed; last error: {last_err}"
        )
