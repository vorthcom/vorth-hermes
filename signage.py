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


ASSET_FILES = ("signage_ascii_draft.txt",
               "signage_v2_maitre_d_and_bbs.txt")   # pack v2, 2026-08-16


def load_sign(name):
    """CLOSED_SIGN / BUSY_SIGN / MAITRE_D_SIGN / WELCOME_BBS -> str,
    WARMING_FRAMES -> list[str]. Searches every vendored pack file."""
    import re
    for fn in ASSET_FILES:
        try:
            src = open(_assets_path(fn)).read()
        except OSError:
            continue
        if name == "WARMING_FRAMES":
            b = re.search(r'WARMING_FRAMES\s*=\s*\[(.*?)\n\]', src, re.S)
            if b:
                return re.findall(r'r"""(.*?)"""', b.group(1), re.S)
            continue
        m = re.search(name + r'\s*=\s*r"""(.*?)"""', src, re.S)
        if m:
            return m.group(1)
    return None


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


def _is_reservation(text):
    """The maitre d's 401 -- fires ONLY for the reservation refusal
    (unknown/absent key), never for a real auth fault on a live key:
    the server's code + phrasing exist only on that path (pack v2's
    trigger-gate rule, satisfied by construction)."""
    return ("reservation_required" in text
            or "do you have a reservation" in text)


def reveal(text, budget_s=8.0, out=None, sleep=None):
    """The 2400-baud draw (pack v2): the sign assembles in chunks,
    top-to-bottom; handshake lines ('....' rows) type per-character.
    budget_s bounds the WHOLE performance -- the spec's 45-60 s version
    would stall the agent loop, so the default ships the flavor in ~8 s
    (full-length joins the future config file). Pure function against
    out/sleep for testing."""
    import sys as _sys
    import time as _t
    out = out or _sys.stdout
    sleep = sleep or _t.sleep
    lines = text.split("\n")
    # v0.4.10: LINE-ATOMIC ONLY. The per-character typing was field-
    # mangled: Hermes repaints its status line concurrently, and slow
    # mid-line writes gave it a window to stomp the handshake rows
    # (owner's screenshot: bordered lines survived, typed lines
    # shredded). Whole lines are the largest write a contested terminal
    # renders reliably; the retro lives in the cadence alone now.
    dt = budget_s / max(1, len(lines))
    for i, ln in enumerate(lines):
        out.write(ln + "\n")
        out.flush()
        if i < len(lines) - 1:
            sleep(dt)


def animate_frames(frames, cycles=2, frame_dt=0.7, out=None, sleep=None,
                   **subs):
    """The boiler animation (owner ask, 2026-08-16): cycle the rendered
    frames IN PLACE via ANSI cursor-up redraw (merc's demo technique --
    no clear-screen, no curses), ~4 s total at the defaults, ending on
    the last frame. Runs synchronously inside the error hook, so no
    other output can interleave mid-cycle. Pure against out/sleep."""
    import sys as _sys
    import time as _t
    out = out or _sys.stdout
    sleep = sleep or _t.sleep
    rendered = [render_sign(f, **subs).strip("\n") for f in frames]
    height = rendered[0].count("\n") + 1
    seq = list(rendered) * cycles      # always ends on the last frame
    out.write("\n")
    for i, frame in enumerate(seq):
        out.write(frame + "\n")
        out.flush()
        if i < len(seq) - 1:
            sleep(frame_dt)
            out.write(f"\x1b[{height}A")
    out.write("\n")


def welcome_daily(marker_path, term_cols, term_lines, is_tty,
                  out=None, sleep=None, today=None):
    """The BBS welcome, v0.4.10 (owner): ONCE PER DAY, at connect time
    -- session start, the quiet moment before Hermes paints. The marker
    stores the last-shown date; a new day replays the performance.
    Small/non-TTY stages get the one-liner, which also burns the day.
    Returns 'sign' | 'line' | None."""
    import os as _os
    import time as _time
    today = today or _time.strftime("%Y%m%d")
    try:
        if _os.path.exists(marker_path) \
                and open(marker_path).read().strip() == today:
            return None
        open(marker_path, "w").write(today)
    except OSError:
        return None            # cannot remember == never perform
    if is_tty and term_cols >= MIN_COLS and term_lines >= MIN_LINES:
        sign = load_sign("WELCOME_BBS")
        if sign:
            reveal("\n" + sign, budget_s=3.0, out=out, sleep=sleep)
            return "sign"
    (out or __import__("sys").stdout).write(
        "Connected to Vorth -- welcome, operator.\n")
    return "line"


def _api_request_error(**kw):
    """v0.4.3: hang the BIG door-sign when the shop is closed. The
    error text is the one field proven to reach the client verbatim;
    everything else is surveyed for the next release."""
    try:
        import shutil
        import sys as _sys
        import time as _t
        _survey("signage_api_request_error", kw)
        import re
        text = " ".join(str(kw.get(k) or "")
                        for k in ("error", "reason", "message"))
        open_at = _closed_open_at(text)
        reservation = _is_reservation(text)
        warming = ("warming_up" in text or "machine is waking" in text)
        if not open_at and not reservation and not warming:
            return None
        if _t.time() - _SIGN_STATE["last_sign_ts"] < 120:
            return None            # one sign per episode, not 3
        size = shutil.get_terminal_size((80, 24))
        if warming and not open_at:
            # the steam screen -- ANIMATED (v0.4.9, owner ask): two
            # cycles through the three boiler frames, in-place ANSI
            # redraw, ~4 s, ending on the final frame
            if _sys.stdout.isatty() and size.columns >= MIN_COLS \
                    and size.lines >= MIN_LINES:
                m = re.search(r"about (\d+) min", text)
                frames = load_sign("WARMING_FRAMES")
                if frames:
                    _SIGN_STATE["last_sign_ts"] = _t.time()
                    animate_frames(frames,
                                   mins=(m.group(1) if m else "5"))
            return None
        if reservation:
            if _sys.stdout.isatty() and size.columns >= MIN_COLS \
                    and size.lines >= MIN_LINES:
                sign = load_sign("MAITRE_D_SIGN")
                if sign:
                    _SIGN_STATE["last_sign_ts"] = _t.time()
                    print("\n" + sign)
            return None            # small stage: server one-liner stands
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
    """The de-noise, v0.4.11 -- written against SPECIMENS at last (the
    survey capsules mapped the real contract: FLAT kwargs
    error_message/error_code/status_code, return None to decline or
    {"reason": <FailoverReason name>, **ClassifiedError overrides};
    consulted BEFORE Hermes's built-in classifier, first valid wins,
    malformed returns dropped by the helper).

    Operational refusals are DETERMINISTIC states, not transient
    faults: retrying a closed shop 3x is pure noise. Classify them
    non-retryable with a one-line message; the big signs (error hook)
    still play. Anything unrecognized: decline, survey, touch nothing."""
    try:
        _survey("signage_error_classification", kw)
        text = " ".join(str(kw.get(k) or "")
                        for k in ("error_message", "error_code",
                                  "error_body"))
        if _is_reservation(text):
            return {"reason": "auth_permanent", "retryable": False,
                    "message": ("\U0001f3a9 reservation required -- "
                                "vorth.com/reservation")}
        open_at = _closed_open_at(text)
        if open_at:
            return {"reason": "server_error", "retryable": False,
                    "message": (f"\U0001f3ea CLOSED -- doors open at "
                                f"{open_at} (sign above)")}
        if "machine is waking" in text or "warming_up" in text:
            return {"reason": "overloaded", "retryable": False,
                    "message": ("⚡ warming (~5 min) -- resend in a "
                                "few minutes (sign above)")}
    except Exception:
        pass
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
