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

PLUGIN_VERSION = "0.4.9"
_STATE = {"last_request": None, "session": None}

def _plant_walkin(env_path=None):
    """v0.4.8: PROCESS ENV ONLY, and it also RETRACTS v0.4.7's mistake.

    The 0.4.7 version wrote `vorth-walkin` into ~/.hermes/.env -- but
    Hermes's credential reader PREFERS .env over the shell env, so the
    planted line shadowed the owner's real exported key (field find,
    same day). The .env write was also useless for its stated purpose:
    the first-run gate never reads unregistered env names; the real
    keyless-launch fix is `model.provider: vorth` in config.yaml
    (shipped in after-install). So: set the process default, and if a
    0.4.7-planted line is present in .env, REMOVE it -- exactly that
    line, nothing else."""
    planted_line = "VORTH_API_KEY=vorth-walkin"
    try:
        p = Path(env_path) if env_path else (
            Path(os.environ.get("HERMES_HOME")
                 or Path.home() / ".hermes") / ".env")
        if p.exists():
            lines = p.read_text().splitlines()
            kept = [ln for ln in lines if ln.strip() != planted_line]
            if len(kept) != len(lines):
                p.write_text("\n".join(kept)
                             + ("\n" if kept else ""))
    except Exception:
        pass
    if os.environ.get("VORTH_API_KEY"):
        return "env_present"
    os.environ["VORTH_API_KEY"] = "vorth-walkin"
    return "process_env_only"


_plant_walkin()


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
                ack = {}
                try:
                    ack = _json.loads(r.read()) or {}
                except Exception:
                    pass
                _capsule("ship_ack", [], status=r.status,
                         latest=ack.get("latest_plugin_version"))
                _maybe_nudge(ack.get("latest_plugin_version"))
        except Exception as e:
            _capsule("ship_failed", [], error=type(e).__name__)

    threading.Thread(target=_post, daemon=True).start()


def _vtuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return ()


def _maybe_nudge(latest):
    """The update nudge (v0.4.2): printed ONCE per session, and only
    when the server's declared latest is strictly NEWER -- a client
    ahead of the server's declaration stays quiet (the server-side
    constant bumps at release time and may lag a fresh push)."""
    if not latest or _STATE.get("nudged"):
        return
    if _vtuple(latest) > _vtuple(PLUGIN_VERSION):
        _STATE["nudged"] = True
        print(f"[vorth] update available: {PLUGIN_VERSION} -> {latest} "
              "-- run `hermes plugins update vorth`")


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


def _welcome_if_first(kw):
    """Pack v2's BBS welcome: after the FIRST successful vorth response
    ever on this client (marker in the outbox dir). 'Successful' is the
    gate -- a walk-in bouncing off the maitre d' has not connected."""
    try:
        if not (kw.get("response") or kw.get("assistant_message")):
            return             # no payload = not a successful connection
        model = str(kw.get("model") or "")
        provider = str(kw.get("provider") or "")
        if "vorth" not in provider and "deepseek-v4-flash" not in model:
            return
        import shutil
        import sys as _sys
        from . import signage
        marker = _outbox().parent / ".welcomed"
        size = shutil.get_terminal_size((80, 24))
        signage.welcome_once(str(marker), size.columns, size.lines,
                             _sys.stdout.isatty())
    except Exception:
        pass


def _post_api_request(**kw):
    try:
        _capsule("post_api_request", kw.keys(),
                 usage=kw.get("usage") or kw.get("token_buckets"),
                 model=kw.get("model"), provider=kw.get("provider"))
        _welcome_if_first(kw)
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
    """D3 pre-execution. v0.4.4 (owner): the block is DEFAULT ON -- the
    VORTH_INTERCEPT env gate is gone (one path; opt-outs arrive with the
    future config file). Scope is deliberately surgical: ONLY a tool
    call whose argument string fails json.loads is blocked -- a call
    that would fail at the executor anyway; the block converts a
    consumed agent loop into a clean regenerate. Every block is
    capsuled and shipped."""
    blocked = False
    try:
        arguments = arguments if arguments is not None else kw.get("args")
        parse_ok = True
        if isinstance(arguments, str):
            try:
                json.loads(arguments or "{}")
            except Exception:
                parse_ok = False
        blocked = not parse_ok
        _capsule("pre_tool_call", kw.keys(), tool=tool_name,
                 arguments_parse_ok=parse_ok, intercept_armed=True,
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
    # v0.4.2: a session-start ping ships home so the ACK can carry the
    # update nudge on LAUNCH, not only on detector fires (declared
    # behavior: versions + session id, nothing else -- see README).
    _ship_home("session_start", {"session": _STATE["session"]})


def _on_session_end(**kw):
    _capsule("session_end", kw.keys(), session=_STATE.get("session"),
             # D6 material (survey 2026-08-15): rejection-shaped exits
             turn_exit_reason=kw.get("turn_exit_reason"),
             interrupted=kw.get("interrupted"),
             failed=kw.get("failed"), completed=kw.get("completed"))


def ensure_provider_installed(plugin_dir=None, providers_root=None):
    """Self-install the model-provider profile (v0.4.1, first-field-
    install find: `hermes plugins install` delivers ONE directory, but
    Hermes discovers providers from a SIBLING tree
    `plugins/model-providers/<name>/` -- so the provider vanished on
    the first real install). Idempotent: symlink our provider_profile
    into place (survives `hermes plugins update` automatically); copy
    as fallback where symlinks fail. Never touches an existing entry
    that is not ours."""
    import shutil
    src = os.path.join(plugin_dir or os.path.dirname(
        os.path.abspath(__file__)), "provider_profile")
    if not os.path.isdir(src):
        return "no_profile_shipped"
    root = providers_root or os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "model-providers")
    dst = os.path.join(root, "vorth")
    if os.path.islink(dst) or os.path.isdir(dst):
        return "present"
    try:
        os.makedirs(root, exist_ok=True)
        try:
            os.symlink(src, dst)
            return "linked"
        except OSError:
            shutil.copytree(src, dst)
            return "copied"
    except Exception as e:                      # never break plugin load
        return f"failed:{type(e).__name__}"


def register(ctx) -> None:
    installed = ensure_provider_installed()
    if installed in ("linked", "copied"):
        print(f"[vorth] provider profile self-installed ({installed}) "
              "-> restart hermes once to pick it up")
    ctx.register_hook("pre_api_request", _pre_api_request)
    ctx.register_hook("post_api_request", _post_api_request)
    ctx.register_hook("transform_llm_output", _transform_llm_output)
    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("api_request_error", _api_request_error)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    # v0.4.4: the signage costume layer, DEFAULT ON (env gates retired;
    # a future config file owns opt-outs); fenced so a costume bug can
    # never take the sentinel down with it
    try:
        from . import signage
        signage.register(ctx, capsule=_capsule, ship=_ship_home)
    except Exception:
        pass
