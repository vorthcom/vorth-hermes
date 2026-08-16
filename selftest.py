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
    b1, b2 = io.StringIO(), io.StringIO()
    r1 = signage.welcome_once(mk, 100, 40, True, out=b1,
                              sleep=lambda s: None)
    r2 = signage.welcome_once(mk, 100, 40, True, out=b2,
                              sleep=lambda s: None)
    check("welcome plays ONCE (sign, then never again -- the joke dies "
          "if it plays twice)",
          r1 == "sign" and r2 is None and b2.getvalue() == "")
    mk2 = os.path.join(td2, ".welcomed2")
    b3 = io.StringIO()
    r3 = signage.welcome_once(mk2, 50, 12, True, out=b3,
                              sleep=lambda s: None)
    check("small terminal: one-liner welcome, once also burned",
          r3 == "line" and "operator" in b3.getvalue())

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
    r = _m47._plant_walkin(env_path=envf)
    # module import already set process env; clear to test the writer
    os.environ.pop("VORTH_API_KEY", None)
    r = _m47._plant_walkin(env_path=envf)
    check("keyless: walk-in written to .env (upstream of the gate)",
          r == "planted"
          and "VORTH_API_KEY=vorth-walkin" in open(envf).read(), r)
    os.environ.pop("VORTH_API_KEY", None)
    r2 = _m47._plant_walkin(env_path=envf)
    check("second plant is idempotent (dotenv_present, no duplicate line)",
          r2 == "dotenv_present"
          and open(envf).read().count("VORTH_API_KEY=") == 1, r2)
    if saved47 is not None:
        os.environ["VORTH_API_KEY"] = saved47
    else:
        os.environ.pop("VORTH_API_KEY", None)

# -- sentinel core intact ---------------------------------------------------
_spec2 = _il.spec_from_file_location(
    "vorth_plugin_pkg", os.path.join(HERE, "__init__.py"),
    submodule_search_locations=[HERE])
try:
    plug = _il.module_from_spec(_spec2)
    sys.modules["vorth_plugin_pkg"] = plug
    _spec2.loader.exec_module(plug)
    check("plugin package imports; version + detectors declared",
          plug.PLUGIN_VERSION == "0.4.7"
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

print(f"PLUGIN SELFTEST {P} PASS / {F} FAIL")
sys.exit(1 if F else 0)
