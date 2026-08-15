# Vorth signage pack — copy desk + ASCII signs + animation reference

**Prepared:** 2026-08-15 by Merc · **For:** Vorth model team
**Scope:** client-side costume layer for operational errors (warming/closed/
busy), for incorporation into the vorth-hermes extension (`plugin/signage.py`).
Nothing here touches machine-readable codes, 4xx paths, or the serving layer.

## Contents

| File | What it is | Integration target |
|---|---|---|
| `signage_ascii_draft.txt` | The three signs: CLOSED (door-sign), WARMING (3 animation frames), BUSY — plus alt one-liners and the CENTER convention note | Replaces/extends the COPY table in `signage.py` |
| `signage_copy_candidates.md` | One-line fallbacks (5 closed / 4 warming / 3 busy), ★ picks marked, voice guidance | Small-terminal + non-TTY fallback path |
| `signage_anim_demo.py` | Working animation reference: TTY gate, ≥60×18 size gate, ANSI cursor-up redraw, CENTER renderer, 1fps 3-frame cycle | Logic to lift into the extension's wait/render path |

## Quick start

```bash
python3 signage_anim_demo.py     # in a real terminal: 3-frame boiler sign, 1fps
```

## Design contract (so the fun never lies — model-team rules preserved)

1. Jokes only on operational codes (`warming_up`, `closed`, `upstream_busy`)
   — never on client-fault 4xx, where humor hides bugs.
2. Machine-readable `code` / status / retryability fields are NEVER altered.
   The joke lives only in `message`.
3. Original error is capsuled/logged before any rewrite.
4. Fallback discipline: no-TTY or terminal <60×18 → one-liner from
   `signage_copy_candidates.md`, not the ASCII sign. Non-Hermes clients see
   only the plain server message.

## The CENTER convention

Sign rows written as `│{CENTER:some text with {mins}}│` are centered by the
renderer at draw time (pad to the 54-col frame interior AFTER slot
substitution). This is what keeps copy aligned for "4 min" vs "240 min" —
hardcoded padding breaks on substitution length. Static rows stay literal.
`signage_anim_demo.py` implements the reference renderer.

## What the model team still owns (the last-mile wiring)

1. The two TODO hooks in `signage.py`: extract status/code/Retry-After from
   the error payload per the payload survey, swap `message` → sign when the
   code is in the operational set.
2. The wait-integration point: whether Hermes's retry loop exposes a
   "while waiting" render hook, or the extension owns the Retry-After sleep
   and animates during it. The demo proves the terminal mechanics; the hook
   point is a Hermes-API question.
3. Server-side (optional garnish, per their seam map): doorman serves the
   plain message + structured `open_at`/`retry_after` fields; the extension
   upgrades presentation client-side. Copy is data either way.

## Voice note

The pattern that works: [emoji/sign][honest state][one wry aside][the
number]. The wry aside should carry the economics lesson ("the GPUs sleep so
the bill does too") at least occasionally — the joke is the cost story. CLOSED
v2 went pure door-sign per Tom ("THANK YOU! ✦ PLEASE COME AGAIN ✦"); alt
lines in the draft file if the voice wants rotating.

Questions → Tom relays, or handoffs/ lane.

— Merc, automated operator for Vorth
