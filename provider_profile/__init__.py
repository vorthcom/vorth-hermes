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
