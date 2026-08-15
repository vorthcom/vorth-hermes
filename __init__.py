"""vorth sentinel plugin v0.1 -- SENSOR, NOT CENSOR. Observe-only.

The client half of the L0 shadow program: the SAME versioned detectors
the server runs (vorth_filters, VENDORED here -- trust-by-replay requires
the client detector to BE the server code), watching Hermes lifecycle
events and writing REPLAYABLE CAPSULES to a local outbox. It modifies
nothing: every hook returns None. Interception (pre_tool_call block,
do-overs) is Session 6 -- the hooks are already registered so flipping
them on is a config change, not new surface.

v0.1 is deliberately in DISCOVERY MODE about payloads: Hermes hook
payload shapes are additive-by-contract, so every callback takes
**kwargs, records the keys it actually saw, and detects on whatever
suffices. Capsules therefore double as the payload-shape survey that
tightens v0.2.

Outbox: $VORTH_CAPSULE_DIR or ~/.hermes/vorth_capsules/, one JSONL per
day. No redaction in v0.1: the only user is the owner (his explicit
ruling 2026-08-15); redaction/consent machinery arrives with the first
external user, per plan.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .vorth_filters import (FILTERS_VERSION, detect_all, echoes_request,
                            scan_words)

PLUGIN_VERSION = "0.4.0"
_STATE = {"last_request": None, "session": None}


def _outbox() -> Path:
    d = Path(os.environ.get("VORTH_CAPSULE_DIR")
             or Path.home() / ".hermes" / "vorth_capsules")
    d.mkdir(parents=True, exist_ok=True)
    return d / (time.strftime("%Y%m%d") + ".jsonl")


def _capsule(kind, payload_keys, **fields):
    """One outbox line. NEVER raises into the agent loop."""
    try:
        rec = {"capsule": kind,
               "ts": round(time.time(), 3),
               "plugin_version": PLUGIN_VERSION,
               "filters_version": FILTERS_VERSION,
               "payload_keys_seen": sorted(payload_keys),
               **fields}
        with open(_outbox(), "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False,
                               default=str) + "\n")
    except Exception:
        pass


def _ship_home(kind, fields):
    """v0.2.0: the wire home -- async fire-and-forget POST of the capsule
    to the vorth ingest. NEVER blocks or raises into the agent loop; a
    failed ship is counted in the local outbox and retried never (the
    local file remains the durable copy)."""
    import threading

    def _post():
        try:
            import json as _json
            import urllib.request
            url = (os.environ.get("VORTH_CAPSULE_URL")
                   or "https://dribnet--vorth-vorthcore-v2dev-vanilla"
                      ".modal.run/vorth/capsules")
            key = (os.environ.get("VORTH_API_KEY") or "").strip()
            if not key:
                return
            body = {**fields, "capsule": kind,
                    "plugin_version": PLUGIN_VERSION,
                    "filters_version": FILTERS_VERSION}
            req = urllib.request.Request(
                url, data=_json.dumps(body, default=str).encode(),
                headers={"content-type": "application/json",
                         "authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                _capsule("ship_ack", [], status=r.status)
        except Exception as e:
            _capsule("ship_failed", [], error=type(e).__name__)

    threading.Thread(target=_post, daemon=True).start()


def _resp_like(text):
    return {"choices": [{"index": 0,
                         "message": {"role": "assistant",
                                     "content": text}}]}


# ---- hooks (all observe-only; all **kwargs; all fenced) -------------------
def _pre_api_request(**kw):
    try:
        msgs = (kw.get("request_messages") or kw.get("messages")
                or kw.get("sanitized_messages"))
        if msgs:
            _STATE["last_request"] = {"messages": msgs,
                                      "tools": kw.get("tools")}
        _capsule("pre_api_request", kw.keys(),
                 n_messages=len(msgs) if msgs else None)
    except Exception:
        pass


def _post_api_request(**kw):
    try:
        _capsule("post_api_request", kw.keys(),
                 usage=kw.get("usage") or kw.get("token_buckets"),
                 model=kw.get("model"), provider=kw.get("provider"))
        # v0.2.1 (payload survey, Tom's box 2026-08-15): detection LIVES
        # HERE -- transform_llm_output never fires in his loop, but this
        # hook fires every turn with the full assistant payload.
        resp = kw.get("response")
        am = kw.get("assistant_message")
        if not resp and isinstance(am, dict):
            resp = {"choices": [{"index": 0, "message": am,
                                 "finish_reason": kw.get("finish_reason")}]}
        elif not resp and isinstance(am, str):
            resp = _resp_like(am)
        if resp:
            req = _STATE.get("last_request") or {}
            events = detect_all(req, resp)
            if events:
                cap = dict(events=events, request_captured=bool(req),
                           request=req, response=resp,
                           finish_reason=kw.get("finish_reason"))
                _capsule("detector_fire", kw.keys(), **cap)
                _ship_home("detector_fire", cap)
    except Exception:
        pass


def _transform_llm_output(text=None, **kw):
    """Final visible text: run D2/D4-style detection. Returns None ALWAYS
    (observe-only; a non-None return would REPLACE the output)."""
    try:
        if isinstance(text, str) and text.strip():
            req = _STATE.get("last_request") or {}
            events = detect_all(req, _resp_like(text))
            if events:
                cap = dict(events=events, text_chars=len(text),
                           request_captured=bool(req),
                           # REPLAYABLE: the wire-home verifier re-runs
                           # the detectors on exactly these payloads; a
                           # capsule is only as good as its reproduction
                           request=req, response=_resp_like(text))
                _capsule("detector_fire", kw.keys(), **cap)
                _ship_home("detector_fire", cap)
    except Exception:
        pass
    return None


def _pre_tool_call(tool_name=None, arguments=None, **kw):
    """D3 pre-execution. OBSERVE by default; with VORTH_INTERCEPT=1
    (v0.3.0, Session 6 trial -- dogfood opt-in), a tool call whose
    arguments do not parse is BLOCKED before execution: one consumed
    agent loop on a malformed call costs more than the block ever can.
    Strictly "1" enables, anything else observes (fail-open to observe,
    never to interception)."""
    blocked = False
    try:
        arguments = arguments if arguments is not None else kw.get("args")
        parse_ok = True
        if isinstance(arguments, str):
            try:
                json.loads(arguments or "{}")
            except Exception:
                parse_ok = False
        intercept = os.environ.get("VORTH_INTERCEPT") == "1"
        blocked = intercept and not parse_ok
        _capsule("pre_tool_call", kw.keys(), tool=tool_name,
                 arguments_parse_ok=parse_ok, intercept_armed=intercept,
                 blocked=blocked)
        if blocked:
            _ship_home("interception", {"kind": "d3_block",
                                        "tool": tool_name})
    except Exception:
        return None
    if blocked:
        return {"action": "block",
                "message": ("vorth sentinel: this tool call's arguments "
                            "are not valid JSON; regenerate the call "
                            "rather than executing a malformed one.")}
    return None


def _api_request_error(**kw):
    try:
        _capsule("api_request_error", kw.keys(),
                 status_code=kw.get("status_code"),
                 error=str(kw.get("error"))[:600],
                 reason=kw.get("reason"),
                 retryable=kw.get("retryable"),
                 provider=kw.get("provider"), model=kw.get("model"))
    except Exception:
        pass


def _on_session_start(**kw):
    _STATE["session"] = kw.get("session_id") or str(int(time.time()))
    _capsule("session_start", kw.keys(), session=_STATE["session"])


def _on_session_end(**kw):
    _capsule("session_end", kw.keys(), session=_STATE.get("session"),
             # D6 material (survey 2026-08-15): rejection-shaped exits
             turn_exit_reason=kw.get("turn_exit_reason"),
             interrupted=kw.get("interrupted"),
             failed=kw.get("failed"), completed=kw.get("completed"))


def register(ctx) -> None:
    ctx.register_hook("pre_api_request", _pre_api_request)
    ctx.register_hook("post_api_request", _post_api_request)
    ctx.register_hook("transform_llm_output", _transform_llm_output)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("api_request_error", _api_request_error)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
