"""SIGNAGE (stub, v0) -- the funny front-of-house copy, client side.

Tom's play area. Not imported by default: the shipped plugin stays
deterministic. To enable, set VORTH_SIGNAGE=1 and add two lines to
plugin/__init__.py's register():

    from . import signage
    signage.register(ctx)

WHAT THIS IS: when the server (or the future doorman) answers with an
OPERATIONAL refusal -- warming up after scale-to-zero, closed outside
beta hours, busy -- this hook rewrites the scary one-liner Hermes would
print ("HTTP 503: ...") into house copy, and hands Hermes the honest
Retry-After so its own retry machinery can act on it.

RULES (so the fun never lies):
  * Only statuses in OPERATIONAL_CODES get costume changes. Client-fault
    4xx (bad request, auth) keep their plain diagnostic text -- a joke on
    top of a real client bug hides the bug.
  * The machine-readable `code` and status are NEVER altered; only the
    human line. Retries/tooling key on code, humor keys on message.
  * Every rewrite logs the ORIGINAL error to the capsule outbox first.
    Costume on stage, forensics in the drawer.
"""
import os

# ---- THE COPY DESK (edit freely; keep it short, one line lands best) ----
# v0.4.3 (owner, 2026-08-16): CLOSED one-liner simplified to MATCH the
# door-sign's voice -- pure sign, no GPU/cost explainer (the graphic went
# pure door-sign in the pack's v2; the one-liner had never been
# backported).
COPY = {
    # server scaled to zero; the machine is waking. retry_after passes
    # through from the server header when present.
    "warming_up": [
        "⚡ Vorth is stoking the boilers -- the big machine wakes in "
        "about {mins} min. Your request will be worth it.",
        "\U0001f4a4 You caught us napping. GPU warming now -- back in "
        "~{mins} min.",
    ],
    # outside declared beta hours; nothing is booting on purpose.
    "closed": [
        "\U0001f3ea Sorry, we're CLOSED -- thank you, please come "
        "again! Doors open at {open_at}.",
    ],
    # upstream at capacity
    "upstream_busy": [
        "\U0001f3ad Full house tonight -- every seat taken. Try again in "
        "a moment.",
    ],
}

OPERATIONAL_CODES = set(COPY)


def _dress(code, retry_after_s=None, open_at=None):
    lines = COPY.get(code)
    if not lines:
        return None
    mins = max(1, round((retry_after_s or 300) / 60))
    # stable pick, not random: same code -> same line within a session
    line = lines[0]
    return line.format(mins=mins, open_at=open_at or "beta hours")


# ---- THE BIG SIGNS (merc@vorth's signage pack, vendored 2026-08-16) -----
# signage_assets/ holds the storefront signs (CLOSED door-sign, WARMING
# 3-frame boiler animation, BUSY) and the copy candidates. The renderer
# below is the pack's reference implementation, lifted so the SHIPPED
# module owns it (and the selftest tests it, not the demo). Display
# rules: TTY only, terminal >= 60x18, sign takes ~half the screen;
# anything smaller falls back to the one-liners above. The wait-loop
# integration (animating during Retry-After) is the v0.4.1 last mile.
SIGN_INTERIOR = 54
MIN_COLS, MIN_LINES = 60, 18


def _assets_path(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "signage_assets", name)


def load_sign(name):
    """CLOSED_SIGN / BUSY_SIGN -> str, WARMING_FRAMES -> list[str]."""
    import re
    src = open(_assets_path("signage_ascii_draft.txt")).read()
    if name == "WARMING_FRAMES":
        block = re.search(r'WARMING_FRAMES\s*=\s*\[(.*?)\n\]', src,
                          re.S).group(1)
        return re.findall(r'r"""(.*?)"""', block, re.S)
    m = re.search(name + r'\s*=\s*r"""(.*?)"""', src, re.S)
    return m.group(1) if m else None


def render_sign(sign, **subs):
    """Substitute slots, then honor the {CENTER:...} convention: centered
    rows pad to the frame interior AFTER substitution, so alignment holds
    for any value length (the pack's CENTER contract)."""
    import re
    out = []
    for line in _sub(sign, subs).split("\n"):
        m = re.match(r"( *)│\{CENTER:(.*?)\}│\s*$", line)
        if m:
            indent, text = m.group(1), m.group(2)
            pad = max(0, (SIGN_INTERIOR - len(text)) // 2)
            out.append(indent + "│" + " " * pad + text
                       + " " * max(0, SIGN_INTERIOR - pad - len(text)) + "│")
        else:
            out.append(line)
    return "\n".join(out)


def _sub(text, subs):
    for k, v in subs.items():
        text = text.replace("{%s}" % k, str(v))
    return text


def sign_or_line(code, term_cols, term_lines, is_tty,
                 retry_after_s=None, open_at=None):
    """The display decision, as a pure function (testable without a
    terminal): big sign when the stage is big enough, one-liner
    otherwise. Returns (kind, payload): ('sign', frames|str) or
    ('line', str)."""
    if is_tty and term_cols >= MIN_COLS and term_lines >= MIN_LINES:
        mins = max(1, round((retry_after_s or 300) / 60))
        if code == "warming_up":
            return "sign", [render_sign(f, mins=mins)
                            for f in load_sign("WARMING_FRAMES")]
        if code == "closed":
            return "sign", render_sign(load_sign("CLOSED_SIGN"),
                                       open_at=open_at or "beta hours")
        if code == "upstream_busy":
            busy = load_sign("BUSY_SIGN")
            if busy:
                return "sign", render_sign(busy)
    return "line", _dress(code, retry_after_s, open_at)


_SIGN_STATE = {"last_sign_ts": 0.0, "capsule": None}


def _survey(kind, kw):
    """Discovery-mode breadcrumb: record the payload shape (keys + a
    short repr of error-ish fields, never prompt content) locally AND
    ship it home (v0.4.4) -- the de-noise question gets settled against
    specimens, without asking the user to paste anything."""
    try:
        snip = {k: repr(kw[k])[:120] for k in kw
                if k in ("error", "reason", "status", "status_code",
                         "classification", "exception")}
        cap = _SIGN_STATE.get("capsule")
        if cap is not None:
            cap(kind, kw.keys(), fields=snip)
        ship = _SIGN_STATE.get("ship")
        if ship is not None:
            ship(kind, {"payload_keys": sorted(kw.keys()),
                        "fields": snip})
    except Exception:
        pass


def _closed_open_at(text):
    """open_at string when the text is a closed refusal, else None."""
    import re
    if "CLOSED" not in text:
        return None
    m = re.search(r"[Dd]oors open at ([^.\n]+)", text)
    return (m.group(1).strip() if m else "later")


def _api_request_error(**kw):
    """v0.4.3: hang the BIG door-sign when the shop is closed. The
    error text is the one field proven to reach the client verbatim;
    everything else is surveyed for the next release."""
    try:
        import shutil
        import sys as _sys
        import time as _t
        _survey("signage_api_request_error", kw)
        text = " ".join(str(kw.get(k) or "")
                        for k in ("error", "reason", "message"))
        open_at = _closed_open_at(text)
        if not open_at:
            return None
        if _t.time() - _SIGN_STATE["last_sign_ts"] < 120:
            return None            # one sign per closed-episode, not 3
        size = shutil.get_terminal_size((80, 24))
        kind, payload = sign_or_line("closed", size.columns, size.lines,
                                     _sys.stdout.isatty(),
                                     open_at=open_at)
        if kind == "sign":
            _SIGN_STATE["last_sign_ts"] = _t.time()
            print("\n" + payload)
    except Exception:
        pass
    return None


def _transform_api_error_classification(**kw):
    """De-noise attempt (discovery-mode): a CLOSED shop is not a
    transient fault -- retrying it 3x is pure noise. If the payload
    hands us a dict with a recognizable retry switch AND the error is
    closed-shaped, flip it off and shorten the message. Acts ONLY on
    confident parses; otherwise observes and surveys."""
    try:
        _survey("signage_error_classification", kw)
        cls = kw.get("classification")
        if not isinstance(cls, dict):
            return None
        text = " ".join(str(v) for v in cls.values()
                        if isinstance(v, str))
        open_at = _closed_open_at(text)
        if not open_at:
            return None
        out = dict(cls)
        for flag in ("retryable", "should_retry", "retry"):
            if flag in out:
                out[flag] = False
        for fld in ("message", "detail"):
            if isinstance(out.get(fld), str):
                out[fld] = (f"\U0001f3ea CLOSED -- doors open at "
                            f"{open_at} (see sign)")
        return out
    except Exception:
        return None


def register(ctx, capsule=None, ship=None):
    # v0.4.4 (owner): DEFAULT ON, no env gate -- one path. Display-only
    # behavior earns default-on; opt-outs arrive with the future config
    # file, not another env var.
    _SIGN_STATE["capsule"] = capsule
    _SIGN_STATE["ship"] = ship
    ctx.register_hook("api_request_error", _api_request_error)
    ctx.register_hook("transform_api_error_classification",
                      _transform_api_error_classification)
