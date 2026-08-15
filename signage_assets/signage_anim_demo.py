#!/usr/bin/env python3
"""Warming-sign animation demo — standalone test of the concept.

Run: python3 signage_anim_demo.py
Quit: Ctrl-C

Simulates what the signage extension would do while Hermes's retry
machinery waits on Retry-After: draw the sign, cycle 3 frames at 1 fps.
Uses ANSI cursor-up redraw — same technique progress bars use, no curses,
works in any modern terminal. The real extension would gate on
shutil.get_terminal_size() >= 60x18 and TTY detection first.
"""
import re, sys, time, shutil, os

SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "signage_ascii_draft.txt")).read()

def extract(name):
    m = re.search(name + r'\s*=\s*(?:\[)?r?"""(.*?)"""(?:\])?', SRC, re.S)
    return m.group(1) if m else None

def frames():
    block = re.search(r'WARMING_FRAMES\s*=\s*\[(.*?)\n\]', SRC, re.S).group(1)
    return re.findall(r'r"""(.*?)"""', block, re.S)

def main():
    # gates — same ones the extension would check
    size = shutil.get_terminal_size((80, 24))
    if not sys.stdout.isatty():
        print("(not a tty — would fall back to one-liner here)")
        return
    if size.columns < 60 or size.lines < 18:
        print(f"(terminal {size.columns}x{size.lines} too small — one-liner fallback)")
        return

    fr = [f.replace("{mins}", "4") for f in frames()]
    # honor the {CENTER:text} render convention: center those rows to the
    # frame interior width so alignment holds for any substituted value
    def render(f):
        out = []
        for line in f.split("\n"):
            m = re.match(r"( *)│\{CENTER:(.*?)\}│\s*$", line)
            if m:
                indent, text = m.group(1), m.group(2)
                interior = 54
                pad = max(0, (interior - len(text)) // 2)
                out.append(indent + "│" + " " * pad + text + " " * (interior - pad - len(text)) + "│")
            else:
                out.append(line)
        return "\n".join(out)
    fr = [render(f) for f in fr]
    nlines = max(f.count("\n") for f in fr)
    sys.stdout.write("\n")
    try:
        for cycle in range(12):  # demo: ~12s then exit
            f = fr[cycle % len(fr)]
            sys.stdout.write(f)
            sys.stdout.flush()
            time.sleep(1)
            if cycle < 11:
                # cursor back to top of the sign for in-place redraw
                sys.stdout.write(f"\x1b[{f.count(chr(10))}A")
    except KeyboardInterrupt:
        pass
    sys.stdout.write("\n(demo over — in production this runs during the Retry-After wait)\n")

if __name__ == "__main__":
    main()
