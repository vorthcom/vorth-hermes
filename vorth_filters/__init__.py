"""vorth_filters -- the standalone, versioned detection library.

THE REBOOT CONSEQUENCE THIS PACKAGE EXISTS FOR (REFACTOR_DSH_APPLICABILITY
§4e): the filter engine must be importable by the gateway AND vendorable by
client plugins, because trust-by-replay requires the client detector to BE
the server filter's code, versioned -- a claim is admitted only if
re-running the named detector version reproduces the flag.

Dependency policy: STDLIB ONLY. Nothing here may import beyond the standard
library, ever; that is what makes the package vendorable into a client
plugin unchanged.

LINEAGE. LoopFinder, PINNED_THRESHOLDS, scan_words, request_text_material,
echoes_request, visible_content_empty are VERBATIM ports from the v1.4.1
release tree ab397c52... (live in production 2026-08-14):
sane_loop_filter.py and slick/deploy/sane_gateway.py. Behaviour-identical;
only module homes moved. The operating point is the certified one and may
not be edited here without a release note.

THE SHADOW DETECTORS (D1-D5) are NEW, observe-only, and DETERMINISTIC --
same (request, response) always yields the same events, which is what
replay verification requires. They never modify a response; whether
anything downstream ever acts on them is a different component's business
(sensor, not censor).

ONE DELIBERATE, DOCUMENTED DIVERGENCE from the serving filter: the shadow
loop detector (D2) DOES scan responses carrying tool_calls -- the serving
filter's scan_response skips them so truncation can never bisect a call
(a truncation-safety rationale). Shadow truncates nothing, and the entire
point of L0 is to MEASURE the loop-detector FP rate on agent traffic,
where the serving filter is deliberately off. Every D2 event records
`tool_calls_present` so that population is separable in analysis.
"""
from collections import deque
import json

FILTERS_VERSION = "0.1.0"

# ---- the pinned operating point (VERBATIM, sane_loop_filter.py) ----------
PINNED_THRESHOLDS = {"n": 8, "fire_count": 4, "window": 512,
                     "min_ratio": 0.5, "min_run": 48}

REQUEST_ECHO_MIN_RUN = 24        # sane_gateway.py:951

# D5 provisional threshold: a finish_reason=length response whose visible
# content is at most this many characters is flagged as a truncation stub.
# DECLARED, NOT MEASURED -- the plan pins the real number from shadow data
# (every D5 event carries the measured length so the threshold can be
# re-derived from the corpus without re-running anything).
D5_PROVISIONAL_STUB_CHARS = 80


class LoopFinder:
    """VERBATIM port of sane_loop_filter.LoopFinder (v1.4.1)."""

    def __init__(self, n=8, fire_count=4, window=512, min_ratio=0.5,
                 min_run=48):
        self.n = n
        self.fire = fire_count
        self.window = window
        self.min_ratio = min_ratio
        self.min_run = min_run          # ignore loops shorter than this
        self.buf = deque(maxlen=n)
        self.pos = 0
        self.seen = {}                  # gram -> (first, last, stride, cnt)
        self.win = deque(maxlen=window)
        self.wcount = {}

    def push(self, tok):
        """Feed one token; returns None or dict(reason, loop_start)."""
        self.buf.append(tok)
        self.pos += 1
        if len(self.buf) < self.n:
            return None
        g = hash(tuple(self.buf))
        if len(self.win) == self.window:
            old = self.win[0]
            self.wcount[old] -= 1
            if not self.wcount[old]:
                del self.wcount[old]
        self.win.append(g)
        self.wcount[g] = self.wcount.get(g, 0) + 1
        e = self.seen.get(g)
        if e is None:
            self.seen[g] = (self.pos, self.pos, 0, 1)
        else:
            first, last, stride, cnt = e
            d = self.pos - last
            if stride == 0 or d == stride:
                cnt += 1
                self.seen[g] = (first, self.pos, d, cnt)
                if (cnt >= self.fire and (self.pos - first) >= self.min_run):
                    return {"reason": "tight", "loop_start": first - self.n}
            else:
                self.seen[g] = (self.pos, self.pos, 0, 1)   # stride broken
        if (len(self.win) == self.window
                and len(self.wcount) < self.min_ratio * self.window):
            return {"reason": "window",
                    "loop_start": max(0, self.pos - self.window)}
        return None


def scan_words(words):
    """LoopFinder over word-proxy tokens AT THE PINNED THRESHOLDS
    (constructed from the constant, never the class defaults -- the
    reported value and the applied value must be the same object)."""
    lf = LoopFinder(**PINNED_THRESHOLDS)
    for j, w in enumerate(words):
        r = lf.push(w)
        if r:
            return {"reason": r["reason"],
                    "loop_start": max(0, int(r["loop_start"])),
                    "detect_at": j}
    return None


# ---- response accessors (VERBATIM semantics) -----------------------------
def _msg(resp):
    try:
        return resp["choices"][0]["message"]
    except Exception:
        return None


def _texts(msg):
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    content = msg.get("content") or ""
    return reasoning, content


def visible_content_empty(resp):
    """True iff the response carries NO delivered output at all. TOOL CALLS
    COUNT AS DELIVERED OUTPUT (a tool-call response legitimately carries
    content: "" -- that is the whole answer). Independent of finish_reason
    on purpose: a clean stop with an empty answer is the same nothing from
    the customer's side."""
    m = _msg(resp)
    if m is None:
        return True
    if m.get("tool_calls"):
        return False
    return not (m.get("content") or "").strip()


def request_text_material(body):
    """Every piece of CUSTOMER-authored text in a request body.
    Deliberately over-collects: tool descriptions and tool-call arguments
    are customer content just as much as message content is."""
    out = []
    if not isinstance(body, dict):
        return out

    def walk(v, depth=0):
        if depth > 6:
            return
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for k, sub in v.items():
                walk(sub, depth + 1)   # keys are OUR vocabulary
        elif isinstance(v, (list, tuple)):
            for sub in v:
                walk(sub, depth + 1)

    for key in ("messages", "tools", "tool_choice", "prompt", "input"):
        if key in body:
            walk(body.get(key))
    return out


def echoes_request(msg, body, min_run=REQUEST_ECHO_MIN_RUN):
    """True when `msg` contains >= min_run characters of the request
    verbatim."""
    if not isinstance(msg, str) or len(msg) < min_run:
        return False
    material = request_text_material(body)
    if not material:
        return False
    for i in range(0, len(msg) - min_run + 1):
        window = msg[i:i + min_run]
        for text in material:
            if window in text:
                return True
    return False


# ==========================================================================
# THE SHADOW DETECTORS -- observe-only, deterministic, replayable.
# Each returns None or an event-fragment dict; detect_all() stamps the
# common fields. NO detector may modify its inputs.
# ==========================================================================
def detect_d1_empty(request_body, resp):
    """D1 EMPTY: no delivered output, upstream said 200. The empty-2xx
    class -- the defect that cost a certification (v1.2)."""
    if not visible_content_empty(resp):
        return None
    m = _msg(resp) or {}
    return {"detector": "d1_empty",
            "finish_reason": (resp.get("choices") or [{}])[0].get(
                "finish_reason") if resp.get("choices") else None,
            "had_reasoning": bool(_texts(m)[0]) if m else False}


def detect_d2_loop(request_body, resp):
    """D2 LOOP: the certified detector at the certified operating point,
    run over reasoning+content words. SCANS TOOL-CALL RESPONSES TOO (the
    documented shadow divergence -- see module docstring); records the
    population so FP analysis can separate it."""
    m = _msg(resp)
    if m is None:
        return None
    reasoning, content = _texts(m)
    rwords, cwords = reasoning.split(), content.split()
    if not rwords and not cwords:
        return None
    hit = scan_words(rwords + cwords)
    if hit is None:
        return None
    return {"detector": "d2_loop",
            "reason": hit["reason"],
            "loop_start_word": hit["loop_start"],
            "detect_at_word": hit["detect_at"],
            "total_words": len(rwords) + len(cwords),
            "in_reasoning": hit["loop_start"] < len(rwords),
            "tool_calls_present": bool(m.get("tool_calls"))}


def detect_d3_malformed_tool_call(request_body, resp):
    """D3 MALFORMED TOOL CALL: arguments unparseable, tool not offered, or
    declared-required parameters absent. Deterministic and free -- tool
    calls are a verifiable domain. (Full JSON-Schema validation would need
    a dependency; required-parameter presence is the stdlib-honest subset,
    and the event says which check fired.)"""
    m = _msg(resp)
    if m is None or not m.get("tool_calls"):
        return None
    offered = {}
    for t in (request_body or {}).get("tools") or []:
        fn = (t or {}).get("function") or {}
        if fn.get("name"):
            offered[fn["name"]] = fn
    problems = []
    for i, tc in enumerate(m["tool_calls"]):
        fn = (tc or {}).get("function") or {}
        name = fn.get("name")
        if name not in offered:
            problems.append({"index": i, "problem": "tool_not_offered",
                             "name": name})
            continue
        try:
            args = json.loads(fn.get("arguments") or "")
        except Exception:
            problems.append({"index": i, "problem": "arguments_unparseable",
                             "name": name})
            continue
        if not isinstance(args, dict):
            problems.append({"index": i, "problem": "arguments_not_object",
                             "name": name})
            continue
        schema = (offered[name].get("parameters") or {})
        missing = [r for r in schema.get("required") or []
                   if r not in args]
        if missing:
            problems.append({"index": i,
                             "problem": "required_params_missing",
                             "name": name, "missing": missing})
    if not problems:
        return None
    return {"detector": "d3_malformed_tool_call",
            "problems": problems,
            "n_tool_calls": len(m["tool_calls"])}


def detect_d4_request_echo(request_body, resp):
    """D4 REQUEST ECHO: the visible answer contains >= min_run characters
    of the customer's own request verbatim."""
    m = _msg(resp)
    if m is None:
        return None
    _, content = _texts(m)
    if not echoes_request(content, request_body):
        return None
    return {"detector": "d4_request_echo",
            "min_run": REQUEST_ECHO_MIN_RUN,
            "content_chars": len(content)}


def detect_d5_truncation_stub(request_body, resp):
    """D5 TRUNCATION STUB: finish_reason=length with unusably short visible
    content. Threshold PROVISIONAL (declared above); the event carries the
    measured length so shadow data re-derives the real number."""
    try:
        ch = (resp.get("choices") or [{}])[0]
    except Exception:
        return None
    if ch.get("finish_reason") != "length":
        return None
    m = _msg(resp) or {}
    if m.get("tool_calls"):
        return None                     # a delivered call is not a stub
    content = (m.get("content") or "").strip()
    if len(content) > D5_PROVISIONAL_STUB_CHARS:
        return None
    return {"detector": "d5_truncation_stub",
            "content_chars": len(content),
            "threshold_chars": D5_PROVISIONAL_STUB_CHARS,
            "threshold_status": "provisional_declared"}


DETECTORS = (detect_d1_empty, detect_d2_loop, detect_d3_malformed_tool_call,
             detect_d4_request_echo, detect_d5_truncation_stub)


def detect_all(request_body, resp):
    """Run every detector; return the list of event fragments, each stamped
    with the detector version (trust-by-replay: the version names the exact
    code that must reproduce the flag)."""
    events = []
    for det in DETECTORS:
        try:
            ev = det(request_body, resp)
        except Exception as e:
            # A crashing detector is an instrument fault and must be VISIBLE,
            # never a silent absence of events.
            ev = {"detector": "detector_crash",
                  "crashed": det.__name__,
                  "error_type": type(e).__name__}
        if ev is not None:
            ev["detector_version"] = FILTERS_VERSION
            events.append(ev)
    return events
