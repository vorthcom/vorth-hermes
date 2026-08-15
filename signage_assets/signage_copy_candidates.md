# Signage copy candidates — the "store is closed" desk
# Merc's play area, 2026-08-15. Rules inherited from the model team:
#   - jokes only on operational codes (warming/closed/busy) — never on 4xx
#   - machine-readable `code` untouched; the joke lives ONLY in `message`
#   - one line lands best; {mins} and {open_at} are the available slots
# Pick per code, or rotate. My recommended pick is marked ★.

CLOSED_CANDIDATES = [
    # ★ the one I'd ship first — honest, self-aware, explains the WHY
    "🏪 Sorry, we're CLOSED. (Yes, an API with opening hours. The GPUs sleep so the bill does too.) Doors open at {open_at}.",

    # warmer / more human
    "🌙 The shop is dark and the sign is flipped. Come back at {open_at} — the machines rest so the prices stay low.",

    # deadpan
    "🚪 Closed. Like an actual store. We open at {open_at}.",

    # proud of the anachronism
    "🕰️ CLOSED — we keep shop hours like it's 1955. Back at {open_at}. Weirdly, this is why we're cheap.",

    # minimal
    "🔒 Closed until {open_at}. Yes, really. Opening hours are the whole point.",
]

WARMING_CANDIDATES = [
    # ★ honest about the wait, sets expectation, gentle
    "⚡ The big machine is waking — about {mins} min. Retry-After is honest; your client can just wait.",

    # playful
    "💤 You caught us napping. GPU spinning up now — back in ~{mins} min. Worth it, promise.",

    # industrial-cute (matches the refinery brand)
    "🏭 Stoke the boilers — the refinery's cold from the night shift. First pour in ~{mins} min.",

    # diner
    "☕ Coffee's on, machine's warming. ~{mins} min. Sit anywhere.",
]

BUSY_CANDIDATES = [
    # ★
    "🎭 Full house tonight — every seat taken. Small pause, then try again.",

    # plainer
    "⏳ At capacity right now. A moment, please.",

    # refinery again
    "🏗️ Every crane is lifting. Give us a moment and try again.",
]

# A note on voice: the pattern that works is [emoji][honest state][one wry
# aside][the number]. The wry aside should explain the economics ("GPUs sleep
# so the bill does too") at least once per user — that's the brand lesson
# hiding in the joke. After that, variety is fine.
