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
        "\U0001f3ea Sorry, we're CLOSED. (Yes, a website with opening "
        "hours. It's a whole thing.) Doors open at {open_at}.",
        "\U0001f319 The shop is dark and the sign is flipped. Come back "
        "at {open_at} -- the machines sleep so the bill does too.",
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


def _api_request_error(**kw):
    """Observe an API error; if it's operational, remember the costume
    for the classification hook. Discovery-mode: field names verified
    against the payload survey before any rewrite ships."""
    # TODO(tom): pull status/code/Retry-After out of kw per the outbox
    # payload survey (error/reason fields), stash on module state.
    return None


def _transform_api_error_classification(**kw):
    """Where the rewrite happens: return the classification dict with
    the human message swapped for _dress(code), everything else
    untouched. Until wired, observe-only."""
    # TODO(tom): swap message text when code in OPERATIONAL_CODES;
    # never touch code/status/retryability fields.
    return None


def register(ctx):
    if os.environ.get("VORTH_SIGNAGE") != "1":
        return
    ctx.register_hook("api_request_error", _api_request_error)
    ctx.register_hook("transform_api_error_classification",
                      _transform_api_error_classification)
