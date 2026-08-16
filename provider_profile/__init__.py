"""The VORTH provider profile -- the beta surface, carried BY the plugin.

Distribution IS the point (REBOOT_SEQUENCE / DSH §4d): a beta user
installs the vorth extension and gets the provider; no public catalog
needed.

AUTH (v0.1.1, owner review 2026-08-15): a vorth PRODUCT API KEY --
standard `Authorization: Bearer $VORTH_API_KEY`, which every
OpenAI-compatible client already sends. The gateway checks it. Clients
never see infrastructure credentials (v0.1.0 briefly asked for Modal
proxy secrets; that was the wrong trust shape and is gone).
"""
import os
from pathlib import Path

# WALK-INS WELCOME (v0.4.5, hardened v0.4.7): the process-env default
# alone proved DOWNSTREAM of Hermes's configured-check (field test,
# owner) -- the check reads ~/.hermes/.env at startup. So the walk-in
# is planted in BOTH places, idempotently; a real key anywhere wins.
if not os.environ.get("VORTH_API_KEY"):
    os.environ["VORTH_API_KEY"] = "vorth-walkin"
    try:
        _p = (Path(os.environ.get("HERMES_HOME")
                   or Path.home() / ".hermes") / ".env")
        _t = _p.read_text() if _p.exists() else ""
        if not any(ln.strip().startswith("VORTH_API_KEY=")
                   for ln in _t.splitlines()):
            with open(_p, "a") as _f:
                if _t and not _t.endswith("\n"):
                    _f.write("\n")
                _f.write("VORTH_API_KEY=vorth-walkin\n")
    except Exception:
        pass

from providers import register_provider
from providers.base import ProviderProfile

BETA_MODEL = "beta-deepseek-v4-flash-0731"
BETA_BASE = "https://dribnet--vorth-vorthcore-v2dev-vanilla.modal.run/v1"

register_provider(ProviderProfile(
    name="vorth",
    aliases=("vorth-beta",),
    display_name="Vorth (beta)",
    description="Vorth Terse beta test surface -- model-team owned, free, "
                "filter off + shadow observers on",
    signup_url="https://vorth.com",
    env_vars=("VORTH_API_KEY",),
    base_url=BETA_BASE,
    default_aux_model=BETA_MODEL,
))
