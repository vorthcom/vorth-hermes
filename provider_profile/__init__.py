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

# WALK-INS WELCOME (v0.4.5, owner): a missing or empty key defaults to
# the walk-in identity, HERE -- this module executes during Hermes's
# provider discovery, which is exactly the scan that otherwise concludes
# "no API keys or providers found" and shunts a keyless install into
# setup. With the default, keyless launches work end-to-end: the door
# answers 401 reservation_required and the maitre d' explains
# (vorth.com/reservation). A real key in the env always wins.
if not os.environ.get("VORTH_API_KEY"):
    os.environ["VORTH_API_KEY"] = "vorth-walkin"

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
