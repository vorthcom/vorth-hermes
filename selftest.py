#!/usr/bin/env python3
"""Plugin selftest -- $0, no TTY, no network, no Hermes.

Covers the signage renderer (merc's pack, as SHIPPED in signage.py --
the demo is reference, this tests the real module), the display
decision, and that the sentinel core still imports with its detectors
intact. Run: python3 selftest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import importlib.util as _il                                # noqa: E402

_spec = _il.spec_from_file_location(
    "vorth_signage", os.path.join(HERE, "signage.py"))
signage = _il.module_from_spec(_spec)
_spec.loader.exec_module(signage)

P, F = 0, 0


def check(name, ok, detail=""):
    global P, F
    ok = bool(ok)
    P, F = P + ok, F + (not ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]"
                                                     if detail else ""))


def box_widths(rendered):
    """Visual widths of the box rows -- alignment invariant."""
    return {len(ln.rstrip()) for ln in rendered.split("\n")
            if ln.strip().startswith(("│", "┌", "└"))}


# -- assets load ------------------------------------------------------------
frames = signage.load_sign("WARMING_FRAMES")
closed = signage.load_sign("CLOSED_SIGN")
check("warming animation has 3 frames", len(frames) == 3, str(len(frames)))
check("closed sign loads", bool(closed))

# -- CENTER convention: alignment survives substitution lengths ------------
for mins in (4, 240, 99999):
    r = signage.render_sign(frames[0], mins=mins)
    check(f"frame rows stay aligned with mins={mins}",
          len(box_widths(r)) == 1, str(box_widths(r)))
    check(f"no unrendered CENTER slot at mins={mins}", "{CENTER:" not in r)
r = signage.render_sign(closed, open_at="9am NZT")
check("closed sign aligned with open_at substituted",
      len(box_widths(r)) == 1 and "9am NZT" in r)

# -- display decision: pure function, no terminal needed -------------------
kind, payload = signage.sign_or_line("warming_up", 100, 40, True,
                                     retry_after_s=300)
check("big terminal + tty -> the animated sign",
      kind == "sign" and isinstance(payload, list) and len(payload) == 3)
kind, payload = signage.sign_or_line("warming_up", 50, 12, True,
                                     retry_after_s=300)
check("small terminal -> one-liner fallback",
      kind == "line" and "min" in (payload or ""))
kind, payload = signage.sign_or_line("closed", 100, 40, False,
                                     open_at="9am")
check("no TTY -> one-liner fallback (pipes get plain text)",
      kind == "line" and "9am" in (payload or ""))
kind, payload = signage.sign_or_line("some_client_fault", 100, 40, True)
check("non-operational code gets NO costume (the fun never lies)",
      payload is None, str((kind, payload)))

# -- pack v2: the maitre d' and the BBS welcome ----------------------------
md = signage.load_sign("MAITRE_D_SIGN")
bbs = signage.load_sign("WELCOME_BBS")
check("maitre d' + BBS welcome load from pack v2",
      bool(md) and bool(bbs))
check("both v2 signs hold alignment",
      len(box_widths(md)) == 1 and len(box_widths(bbs)) == 1,
      f"md={box_widths(md)} bbs={box_widths(bbs)}")
check("reservation refusal detected, closed copy NOT confused for it",
      signage._is_reservation("... do you have a reservation? ...")
      and not signage._is_reservation("Sorry, we're CLOSED -- thank you"))

import io                                                   # noqa: E402
buf = io.StringIO()
signage.reveal(bbs, budget_s=0.01, out=buf, sleep=lambda s: None)
check("reveal() delivers the complete sign (chunked, typed, lossless)",
      "V O R T H   O N L I N E" in buf.getvalue()
      and "CARRIER DETECT" in buf.getvalue()
      and buf.getvalue().count("\n") >= bbs.count("\n"))

import tempfile as _tf                                      # noqa: E402
with _tf.TemporaryDirectory() as td2:
    mk = os.path.join(td2, ".welcomed")
    b1, b2, b3 = io.StringIO(), io.StringIO(), io.StringIO()
    r1 = signage.welcome_daily(mk, 100, 40, True, out=b1,
                               sleep=lambda s: None, today="20260816")
    r2 = signage.welcome_daily(mk, 100, 40, True, out=b2,
                               sleep=lambda s: None, today="20260816")
    r3 = signage.welcome_daily(mk, 100, 40, True, out=b3,
                               sleep=lambda s: None, today="20260817")
    check("welcome plays ONCE PER DAY (again same day: silent; new day: "
          "encore)", r1 == "sign" and r2 is None and b2.getvalue() == ""
          and r3 == "sign")
    mk2 = os.path.join(td2, ".welcomed2")
    b4 = io.StringIO()
    r4 = signage.welcome_daily(mk2, 50, 12, True, out=b4,
                               sleep=lambda s: None)
    check("small terminal: one-liner welcome, day also burned",
          r4 == "line" and "operator" in b4.getvalue())
    # LINE-ATOMIC invariant (the mangling fix): every write ends in \n
    class _W:
        def __init__(self):
            self.calls = []

        def write(self, s):
            self.calls.append(s)

        def flush(self):
            pass
    w = _W()
    signage.reveal("A\nB\nC", budget_s=0.01, out=w, sleep=lambda s: None)
    check("reveal writes are LINE-ATOMIC (no mid-line stomping window)",
          all(c.endswith("\n") for c in w.calls), str(w.calls))

# -- the boiler animation (v0.4.9): in-place cycle, lossless, aligned -----
bufA = io.StringIO()
signage.animate_frames(frames, cycles=2, frame_dt=0.1, out=bufA,
                       sleep=lambda s: None, mins=7)
outA = bufA.getvalue()
heights = {f.strip("\n").count("\n") + 1 for f in
           (signage.render_sign(f, mins=7) for f in frames)}
check("all warming frames share one height (in-place redraw invariant)",
      len(heights) == 1, str(heights))
check("animation cycles all frames and ends on the LAST one",
      outA.count("\x1b[") == 2 * len(frames) - 1
      and outA.rstrip().endswith(frames[-1].strip("\n").splitlines()[-1])
      and "wakes in about 7 min" in outA,
      f"redraws={outA.count(chr(27))}")

# -- walk-in planted UPSTREAM (v0.4.7: the .env file, not just process
# env -- Hermes's configured-check reads .env before any plugin runs) ------
with _tf.TemporaryDirectory() as td3:
    envf = os.path.join(td3, ".env")
    saved47 = os.environ.pop("VORTH_API_KEY", None)
    import importlib.util as _il47
    _s47 = _il47.spec_from_file_location(
        "vorth_plugin_dotenv", os.path.join(HERE, "__init__.py"),
        submodule_search_locations=[HERE])
    _m47 = _il47.module_from_spec(_s47)
    sys.modules["vorth_plugin_dotenv"] = _m47
    _s47.loader.exec_module(_m47)
    os.environ.pop("VORTH_API_KEY", None)
    r = _m47._plant_walkin(env_path=envf)
    check("keyless: walk-in set in PROCESS ENV ONLY (v0.4.8 -- .env is "
          "never written; the 0.4.7 write shadowed real keys)",
          r == "process_env_only" and not os.path.exists(envf)
          and os.environ.get("VORTH_API_KEY") == "vorth-walkin", r)
    # RETRACTION: a 0.4.7-planted line is removed; other lines untouched
    open(envf, "w").write("OTHER_KEY=x\nVORTH_API_KEY=vorth-walkin\n")
    os.environ.pop("VORTH_API_KEY", None)
    r2 = _m47._plant_walkin(env_path=envf)
    body = open(envf).read()
    check("a 0.4.7-planted .env line is RETRACTED, neighbors untouched",
          "vorth-walkin" not in body and "OTHER_KEY=x" in body, body)
    # a REAL key line in .env is never touched
    open(envf, "w").write("VORTH_API_KEY=vorth-beta-REAL\n")
    r3 = _m47._plant_walkin(env_path=envf)
    check("a real .env key line survives the retraction pass",
          "vorth-beta-REAL" in open(envf).read(), r3)
    if saved47 is not None:
        os.environ["VORTH_API_KEY"] = saved47
    else:
        os.environ.pop("VORTH_API_KEY", None)

# -- de-noise hook (v0.4.11, specimen-proven contract) ---------------------
r = signage._transform_api_error_classification(
    error_message="🏪 Sorry, we're CLOSED -- thank you, please come "
                  "again! Doors open at 15:00 NZST.", status_code=503)
check("closed error -> non-retryable classification with short message",
      isinstance(r, dict) and r["retryable"] is False
      and r["reason"] == "server_error" and "15:00 NZST" in r["message"],
      str(r))
r = signage._transform_api_error_classification(
    error_message="do you have a reservation?", error_code="reservation_required")
check("reservation -> auth_permanent non-retryable",
      isinstance(r, dict) and r["reason"] == "auth_permanent"
      and r["retryable"] is False)
r = signage._transform_api_error_classification(
    error_message="some ordinary provider explosion", status_code=500)
check("unrecognized errors DECLINED (built-in classifier untouched)",
      r is None)

# -- sentinel core intact ---------------------------------------------------
_spec2 = _il.spec_from_file_location(
    "vorth_plugin_pkg", os.path.join(HERE, "__init__.py"),
    submodule_search_locations=[HERE])
try:
    plug = _il.module_from_spec(_spec2)
    sys.modules["vorth_plugin_pkg"] = plug
    _spec2.loader.exec_module(plug)
    check("plugin package imports; version + detectors declared",
          plug.PLUGIN_VERSION == "0.4.13"
          and bool(plug.FILTERS_VERSION), plug.PLUGIN_VERSION)
except Exception as e:
    check("plugin package imports", False, f"{type(e).__name__}: {e}")

# -- walk-in default (v0.4.5): keyless import plants the identity ----------
saved = os.environ.pop("VORTH_API_KEY", None)
import importlib as _importlib
_spec3 = _il.spec_from_file_location(
    "vorth_plugin_keyless", os.path.join(HERE, "__init__.py"),
    submodule_search_locations=[HERE])
_p3 = _il.module_from_spec(_spec3)
sys.modules["vorth_plugin_keyless"] = _p3
_spec3.loader.exec_module(_p3)
check("keyless import defaults VORTH_API_KEY to vorth-walkin",
      os.environ.get("VORTH_API_KEY") == "vorth-walkin")
os.environ.pop("VORTH_API_KEY", None)
os.environ["VORTH_API_KEY"] = "real-key-untouched"
_spec4 = _il.spec_from_file_location(
    "vorth_plugin_keyed", os.path.join(HERE, "__init__.py"),
    submodule_search_locations=[HERE])
_p4 = _il.module_from_spec(_spec4)
sys.modules["vorth_plugin_keyed"] = _p4
_spec4.loader.exec_module(_p4)
check("a REAL key is never overwritten by the walk-in default",
      os.environ.get("VORTH_API_KEY") == "real-key-untouched")
if saved is not None:
    os.environ["VORTH_API_KEY"] = saved
else:
    os.environ.pop("VORTH_API_KEY", None)

# -- provider self-install (v0.4.1, first-field-install find) --------------
import tempfile                                             # noqa: E402
with tempfile.TemporaryDirectory() as td:
    root = os.path.join(td, "model-providers")
    r1 = plug.ensure_provider_installed(plugin_dir=HERE, providers_root=root)
    r2 = plug.ensure_provider_installed(plugin_dir=HERE, providers_root=root)
    check("provider profile self-installs into model-providers/",
          r1 in ("linked", "copied")
          and os.path.exists(os.path.join(root, "vorth")), r1)
    check("second call is idempotent (present, nothing touched)",
          r2 == "present", r2)
    check("missing shipped profile is reported, never fatal",
          plug.ensure_provider_installed(
              plugin_dir=td, providers_root=root + "2")
          == "no_profile_shipped")

# -- v0.4.11: the tool-call assembly fix (the 525-FP class) ---------------
class _AM:                       # assistant_message is an OBJECT upstream
    content = None
    tool_calls = None


with tempfile.TemporaryDirectory() as td5:
    os.environ["VORTH_CAPSULE_DIR"] = td5

    def fires():
        import glob as _g
        n = 0
        for p in _g.glob(os.path.join(td5, "*.jsonl")):
            n += sum(1 for ln in open(p)
                     if '"capsule": "detector_fire"' in ln)
        return n

    plug._STATE["last_request"] = {"messages": [
        {"role": "user", "content": "do the thing"}]}
    plug._post_api_request(assistant_message=_AM(),
                           assistant_tool_call_count=2,
                           finish_reason="tool_calls",
                           model="deepseek-v4-flash", provider="vorth")
    check("TOOL-CALL turn (content None + 2 tool calls) -> NO d1 fire "
          "(the 525-FP class, dead)", fires() == 0)
    plug._post_api_request(assistant_message=_AM(),
                           assistant_tool_call_count=0,
                           finish_reason="stop",
                           model="deepseek-v4-flash", provider="vorth")
    check("GENUINE empty (no content, no tool calls, finish=stop) -> "
          "d1 fires", fires() == 1)
    os.environ.pop("VORTH_CAPSULE_DIR", None)

# -- v0.4.11: shipped-copy evidence minimization ---------------------------
big = {"messages": [{"role": "user", "content": "x" * 9000}] * 30}
m = plug._minimize_request(big)
import json as _json
check("shipped request evidence: last-2 tail, truncated, counted, marked",
      len(m["messages"]) == 2 and m["n_messages_total"] == 30
      and m["_evidence"] == "minimized_v1"
      and len(_json.dumps(m)) < 12000, f"{len(_json.dumps(m))}B")

# -- v0.4.12: THE PROVIDER GATE (owner audit: inert for foreign traffic) --
with tempfile.TemporaryDirectory() as td6:
    os.environ["VORTH_CAPSULE_DIR"] = td6

    def outbox_lines():
        import glob as _g
        return sum(sum(1 for _ in open(p))
                   for p in _g.glob(os.path.join(td6, "*.jsonl")))

    # foreign turn: pre must capture nothing, post must write nothing,
    # even for a GENUINE empty answer
    plug._pre_api_request(provider="anthropic", model="claude-x",
                          request_messages=[{"role": "user",
                                             "content": "secret"}])
    check("foreign pre: no state capture, no breadcrumb",
          plug._STATE.get("vorth_turn") is False
          and plug._STATE.get("last_request") is None
          and outbox_lines() == 0)
    plug._post_api_request(provider="anthropic", model="claude-x",
                           assistant_message=_AM(),
                           assistant_tool_call_count=0,
                           finish_reason="stop")
    check("foreign post: NOTHING written even for a genuine empty",
          outbox_lines() == 0)
    r = plug._pre_tool_call(tool_name="t", arguments="{not json",
                            provider="anthropic")
    check("foreign malformed tool call: NEVER blocked, nothing logged",
          r is None and outbox_lines() == 0)
    # vorth turn: everything works as before
    plug._pre_api_request(provider="vorth", model="x",
                          request_messages=[{"role": "user",
                                             "content": "hi"}])
    r = plug._pre_tool_call(tool_name="t", arguments="{not json",
                            provider="vorth")
    check("vorth malformed tool call: still blocked",
          isinstance(r, dict) and r.get("action") == "block")
    check("vorth pre: breadcrumb written",
          plug._STATE.get("vorth_turn") is True and outbox_lines() >= 1)
    os.environ.pop("VORTH_CAPSULE_DIR", None)

# -- v0.4.13: unfounded tool_not_offered dropped (Step session cycle) ------
ev = [{"detector": "d3_malformed_tool_call",
       "problems": [{"problem": "tool_not_offered", "name": "read_file"}]}]
check("d3 tool_not_offered with UNKNOWN offered-set -> dropped entirely",
      plug._filter_unfounded(ev, {"messages": []}) == [])
ev2 = [{"detector": "d3_malformed_tool_call",
        "problems": [{"problem": "args_unparseable", "index": 0},
                     {"problem": "tool_not_offered", "name": "x"}]}]
out = plug._filter_unfounded(ev2, {})
check("parse problems SURVIVE the filter (they judge the call itself)",
      len(out) == 1 and out[0]["problems"] == [{"problem":
                                               "args_unparseable",
                                               "index": 0}])
check("with a REAL offered-set, tool_not_offered is kept",
      plug._filter_unfounded(ev, {"tools": [{"function":
                                            {"name": "other"}}]}) == ev)

print(f"PLUGIN SELFTEST {P} PASS / {F} FAIL")
sys.exit(1 if F else 0)

