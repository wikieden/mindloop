> 🌐 **English** · [中文](../../../zh/devplan/specs/P7-edge-fallback.md)

# P7 spec — Edge fallback: on-body offline AI chain (LLM + ASR + TTS)

**Status:** planned (design, 2026-06-28). New cross-cutting capability; proposed
milestone **M-L3.6**. Owner decisions flagged in §7.

## 1. Goal

When the network is down, the robot must stay **cognitively functional** on its
own compute: an **on-body** small LLM + local **ASR** (speech→text) + local
**TTS** (text→speech) form a self-contained AI chain. Remote, larger models are
the *primary* path; the on-body chain is the **degraded fallback** — graceful, not
parity. Critically, the robot **never loses safety or memory** when offline.

## 2. What already survives offline (no change needed)

The architecture is already mostly local — only three things reach the network:

| Concern | Network? | Why it survives offline |
|---|---|---|
| **Memory** (tempomem) | local sqlite `.smem` | no network ever |
| **Planning rules** (compile, D3 gate) | deterministic, stdlib | no network |
| **Skill cards** (Episteme, P2) | local YAML/dict | no network |
| **Safety** (Phylax, P3) | stdlib policy gate | **no network — safety degrades closed** |
| **Body dispatch** (ExecutorAdapter) | on-body | no network |
| Reasoner / Planner LLM | **remote** | ← needs on-body fallback |
| Speech in (ASR) | — (new) | ← on-body engine |
| Speech out (TTS) | — (new) | ← on-body engine |

So P7 adds exactly three on-body capabilities and one arbitration policy; the rest
already works disconnected. **Safety surviving offline is the headline**: P3 is
pure-stdlib and runs on-body, so a disconnected robot is *more* conservative, not
less.

## 3. The on-body AI chain

```
            ONLINE  (network up)                         OFFLINE (network down)
  mic ─► [remote ASR? or on-body] ─► text          mic ─► on-body ASR ─► text
  text ─► Brain.handle ─► Reasoner/Planner          text ─► Brain.handle ─► on-body LLM
              (remote Cosmos / Qwen)                            (small quantized, local)
  Answer/speak ─► [remote/on-body TTS] ─► audio     Answer/speak ─► on-body TTS ─► audio
                                  └──────────── Phylax safety gate (local, always) ──────────┘
```

The brain code does **not** change. The three swaps ride existing/new seams:

### 3a. Reasoner/Planner failover — reuse the `Verbalizer` seam

The on-body LLM is just **another `Verbalizer`** pointed at a local
OpenAI-compatible server (vLLM / llama.cpp / MLC / Ollama on the robot's edge
compute). `CosmosReasonVerbalizer(base_url="http://localhost:<port>/v1",
model=<small>)` already works unchanged.

New: **`FailoverVerbalizer([primary, *fallbacks])`** — tries the primary (remote);
on a transport error (`QueryError` — timeout / connection refused) it falls to the
next backend (on-body). Connectivity-aware with hysteresis so it does not flap.
Reports which backend served (telemetry). Brain unchanged — it gets a `Verbalizer`.
Both the `Reasoner` and the `Planner`/`IntentRouter` are Verbalizer-backed, so one
wrapper covers the whole LLM path.

### 3b. ASR — a new `Listener` seam (the ears)

A new protocol `mindloop` ships (same pattern as `ExecutorAdapter`):
`Listener.transcribe(audio) -> str` (and a streaming variant). Concrete on-body
engine is BYO (whisper.cpp / sherpa-onnx / Moonshine). Output feeds
`Brain.handle(instruction)`. `MockListener` (scripted) keeps tests network-free.

### 3c. TTS — a new `Speaker` seam (the mouth)

New protocol `Speaker.say(text) -> Audio` (or streams to the audio device). On-body
engine BYO (piper / kokoro / sherpa-onnx). Speaks `Answer.text`, `plan.speak`, and
Phylax `refusal_speak`. `MockSpeaker` records utterances for tests.

### 3d. The voice loop

A thin orchestrator ties them: `Listener → Brain.handle(..., safety_context) →
Speaker`. Ships as a small `voice.py` loop (or an app on top); mindloop owns the
`Listener`/`Speaker` *protocols*, not the engines.

## 4. Mode arbitration

A `ConnectivityMonitor` (or the failover wrapper itself) selects the path:

- **Online** → remote big reasoner (Cosmos-Reason2 / Qwen3.6 on the workstation).
- **Offline** → on-body small LLM + local ASR/TTS.
- **Hysteresis** — require N consecutive failures to drop to offline and N
  successes to return, so a flaky link does not thrash.
- **Telemetry** — every turn records which mode served it.

## 5. Degradation contract (offline ≠ online)

The on-body model is weaker; offline mode tightens accordingly:

- **Skill-card-first** — prefer P2 deterministic skill cards (no LLM) over the
  small LLM for known tasks; the small LLM is the fallback *within* offline.
- **Conservative safety** — `SafetyContext` defaults to conservative offline
  (unknown identity → stranger); Phylax already enforces this.
- **Simpler answers** — `ask` may shorten the token budget; open-ended chat may be
  disabled offline.
- **Honest UX** — TTS announces degraded mode ("I'm offline, working locally").

## 6. Edge hardware & model candidates (recommendations)

- **Compute** — NVIDIA Jetson AGX Thor / Orin on the robot, or the body's onboard
  GPU. Runs the local OpenAI-compatible server.
- **LLM** — a small quantized instruct/VLM: Qwen3-4B/8B or Cosmos-Reason2-2B in
  4-bit, served by llama.cpp / MLC / Ollama / vLLM.
- **ASR** — sherpa-onnx (streaming, low-latency) or whisper.cpp (small/base) or
  Moonshine (tiny). All run offline on edge.
- **TTS** — piper (fast, local) or kokoro / sherpa-onnx TTS.

## 7. Owner decisions (to ratify)

1. **D-edge-1** — on-body fallback is **degraded, not parity** (skill-card-first +
   conservative). Confirm.
2. **D-edge-2** — ASR/TTS enter as **new BYO seam protocols** (`Listener` /
   `Speaker`), engines out-of-tree — same pattern as `Verbalizer`/`ExecutorAdapter`.
   Confirm.
3. **Edge stack** — pick the on-body LLM, ASR, TTS engines + the edge compute target.
4. **ASR/TTS home** — new package (e.g. an "ears+mouth" member) vs. folding into
   `worldsense` (perception) / `bodylink`. Recommendation: protocols in `mindloop`,
   engines in a small new member or the device package.

## 8. Phasing

| Step | Deliverable |
|---|---|
| P7.1 ✅ | `FailoverVerbalizer` (LLM failover with call-based hysteresis; network-free tests) — done 2026-06-28. `ConnectivityMonitor` folded into the wrapper's cooldown for now |
| P7.2 | `Listener` / `Speaker` protocols + `Mock*` + the voice loop |
| P7.3 | reference on-body engines wired (edge server + ASR + TTS), validated on hardware |
| P7.4 | degradation contract + mode telemetry + "offline" UX |

**Exit (M-L3.6):** pull the network — the robot still hears a command, plans
(skill-card or on-body LLM), passes the safety gate, acts, and speaks, entirely on
its own compute.
