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

# -- sentinel core intact ---------------------------------------------------
_spec2 = _il.spec_from_file_location(
    "vorth_plugin_pkg", os.path.join(HERE, "__init__.py"),
    submodule_search_locations=[HERE])
try:
    plug = _il.module_from_spec(_spec2)
    sys.modules["vorth_plugin_pkg"] = plug
    _spec2.loader.exec_module(plug)
    check("plugin package imports; version + detectors declared",
          plug.PLUGIN_VERSION == "0.4.5"
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
