# Vorth signage pack v2 — maître d' (401) + BBS welcome

**Prepared:** 2026-08-16 by Merc · **For:** Vorth model team
**Adds to the v1 pack** (warming/closed/busy signs + animation reference).
Two new signs, one new mechanic (slow-reveal), one rule-clarification.

## Contents

| File | What |
|---|---|
| `signage_v2_maitre_d_and_bbs.txt` | MAITRE_D_SIGN (401 reservation-only) + WELCOME_BBS (first-connect retro BBS) + the slow-reveal animation spec |
| (v1 files still apply: signs, one-line fallbacks, anim demo) | |

## 1. Maître d' — 401 unknown/missing key

- **Trigger gate (important):** show the sign ONLY for absent/unknown keys.
  A malformed key on a live account is a real client fault and must keep the
  plain diagnostic text — house rule 1 stands. The sign works because
  "not in beta yet" isn't a bug, it's routing: the joke carries the fix
  (https://vorth.com/reservation).
- Copy is in the sign; one-liner fallback:
  `HTTP 401: 🎩 Sorry — do you have a reservation? Seating on the beta floor
  is by reservation only: https://vorth.com/reservation`

## 2. BBS welcome — first successful connection

- **Frequency: ONCE per client.** Extension stores a sentinel after first
  show (~/.vorth_welcomed or config state). Never on retries, never per boot
  — the joke dies if it plays twice.
- **Skip conditions:** non-TTY, terminal <60×18, or VORTH_QUIET=1 → print
  `Connected to Vorth — welcome, operator.` instead.

## 3. The slow-reveal mechanic (the retro part)

Spec is in the file. Short version:
- Split the frame into ~40-60 char chunks; reveal one chunk per ~1s,
  top-to-bottom — the whole sign assembles over ~45-60s like a 2400-baud
  terminal.
- Optional extra period flavor: the CONNECT/PROTOCOL/REFINERY handshake
  lines type character-by-character (30-50ms/char) while the border fills.
- Same ANSI cursor-redraw mechanics as the v1 warming animation — the v1
  demo (signage_anim_demo.py) already proves the TTY gate + redraw approach.
- "caller #____" stays blank unless the server ever exposes a counter —
  honest absence, per house rules.

## What the model team owns (unchanged from v1)

- Hook wiring in signage.py (payload survey → field extraction → message
  swap only on operational/eligible codes).
- The once-per-client sentinel for the welcome sign.
- Decision on where wait-render lives (Hermes retry hook vs extension-owned
  sleep) — same open question as v1.

Questions → Tom relays or handoffs/ lane.

— Merc, automated operator for Vorth
