# Copyright 2026 TracePair contributors.
# SPDX-License-Identifier: MIT
"""Observed-usage parser for native Codex JSONL transcripts.

Codex emits cumulative token_count snapshots that can duplicate opening
usage (https://github.com/openai/codex/issues/14489). Native counters are
described in
https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs .
cache_write_input_tokens is omitted from this v0 contract and must not be
treated as cached-read usage.

Results never include raw log strings, paths, timestamps, IDs, tool names,
model names, arguments, outputs, or transcript text.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

MAX_LINE = 16 * 1024 * 1024
MAX_INT = 2 ** 63 - 1
REQUIRED = ("input_tokens", "output_tokens", "total_tokens")
OPTIONAL = ("cached_input_tokens", "reasoning_output_tokens")
USAGE_KEYS = REQUIRED + OPTIONAL
CATEGORIES = ("shell", "files", "web", "agents", "code", "other")
TOOL_MAP = {
    "exec_command": "shell", "shell_command": "shell", "bash": "shell",
    "apply_patch": "files", "read_file": "files", "write_file": "files",
    "web.run": "web", "web__run": "web", "browser": "web",
    "spawn_agent": "agents", "send_message": "agents",
    "wait_agent": "agents", "followup_task": "agents",
    "exec": "code", "python": "code",
}
TOOL_TYPES = frozenset(("function_call", "custom_tool_call"))
HARD = frozenset({
    "COUNTER_RESET", "INSUFFICIENT_SNAPSHOTS", "INVALID_COUNTER",
    "INVALID_TIMESTAMP", "MIXED_SESSIONS", "NO_TOKEN_DATA", "OUT_OF_ORDER",
})
NONE_TOKENS = {
    "input_tokens": None, "cached_input_tokens": None,
    "uncached_input_tokens": None, "output_tokens": None,
    "reasoning_output_tokens": None, "total_tokens": None,
}

class ParseError(ValueError):
    """Invalid time window or unreadable input, without source details."""

class _State:
    def __init__(self):
        self.warnings = set()
        self.dead = False
        self.acc = None
        self.prev = None
        self.opened = False
        self.coverage = "unavailable"
        self.pre = None
        self.pre_ts = None
        self.snapshots = 0
        self.dup_snap = 0
        self.tools = 0
        self.dup_tools = 0
        self.cats = {name: 0 for name in CATEGORIES}
        self.seen_ids = set()
        self.models = set()
        self.pre_model = None
        self.pre_model_ts = None
        self.session = None
        self.prev_ts = None
        self.tmin = None
        self.tmax = None
        self.malformed = 0
        self.known = {}
        self.selected_seen = False

def _kill(st):
    st.dead = True
    st.acc = None

def _sha(text):
    # JSON may carry escaped unpaired surrogates. Opaque IDs must not crash us.
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()

def _parse_ts(value):
    if type(value) is not str:
        return None
    text = value.strip()
    if not text:
        return None
    if text[-1] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp

def _parse_bound(value):
    if value is None:
        return None
    stamp = _parse_ts(value) if type(value) is str else None
    if stamp is None:
        raise ParseError("invalid time window")
    return stamp

def _nonneg_int(value):
    if type(value) is int and 0 <= value <= MAX_INT:
        return value
    return None

def _parse_usage(blob):
    """Parse total_token_usage; never assume missing optional counters are 0."""
    if not isinstance(blob, dict):
        return None
    usage = {}
    for key in REQUIRED:
        number = _nonneg_int(blob.get(key))
        if number is None:
            return "invalid"
        usage[key] = number
    if usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]:
        return "invalid"
    missing = False
    for key in OPTIONAL:
        if key not in blob:
            usage[key] = None
            missing = True
            continue
        number = _nonneg_int(blob[key])
        if number is None:
            return "invalid"
        usage[key] = number
    cached = usage["cached_input_tokens"]
    reasoning = usage["reasoning_output_tokens"]
    if cached is not None and cached > usage["input_tokens"]:
        return "invalid"
    if reasoning is not None and reasoning > usage["output_tokens"]:
        return "invalid"
    return usage, missing

def _last_matches(total, last):
    return last is not None and all(total[k] == last[k] for k in USAGE_KEYS)

def _advanced(prev, curr):
    return any(
        prev[k] is not None and curr[k] is not None and curr[k] > prev[k]
        for k in USAGE_KEYS
    )

def _classify(name):
    if type(name) is not str:
        return "other"
    label = name.strip()
    if label.startswith("functions."):
        label = label[10:]
    return TOOL_MAP.get(label, "other")

def _payload_of(rec):
    payload = rec.get("payload")
    if not isinstance(payload, dict):
        return {}
    if rec.get("type") == "event_msg" and payload.get("type") == "event_msg":
        inner = payload.get("payload")
        if isinstance(inner, dict):
            return inner
    return payload

def _tool_body(payload):
    kind = payload.get("type")
    if type(kind) is str and kind in TOOL_TYPES:
        return payload
    inner = payload.get("payload")
    if isinstance(inner, dict) and type(inner.get("type")) is str and inner.get("type") in TOOL_TYPES:
        return inner
    return None

def _model_value(kind, payload):
    if kind == "turn":
        model = payload.get("model")
        if type(model) is str:
            return model
        inner = payload.get("payload")
        if isinstance(inner, dict) and type(inner.get("model")) is str:
            return inner.get("model")
        return None
    settings = payload.get("thread_settings")
    if not isinstance(settings, dict):
        inner = payload.get("payload")
        if isinstance(inner, dict):
            settings = inner.get("thread_settings")
    if isinstance(settings, dict) and type(settings.get("model")) is str:
        return settings.get("model")
    return None

def _iter_raw_lines(fh):
    """Binary JSONL lines with a 16 MiB cap; oversized lines are drained."""
    first = True
    while True:
        line = fh.readline(MAX_LINE + 1)
        if not line:
            return
        complete = line.endswith(b"\n")
        core = line[:-1] if complete else line
        if core.endswith(b"\r"):
            core = core[:-1]
        if len(core) > MAX_LINE:
            if not complete:
                while True:
                    extra = fh.readline(MAX_LINE + 1)
                    if not extra or extra.endswith(b"\n"):
                        break
            first = False
            yield None
            continue
        if first and core.startswith(b"\xef\xbb\xbf"):
            core = core[3:]
        first = False
        yield core

def _in_sel(ts, start_dt, end_dt):
    if start_dt is None and end_dt is None:
        return True
    return ts is not None and (start_dt is None or ts >= start_dt) and (
        end_dt is None or ts < end_dt
    )

def _note_time(st, ts):
    if ts is None:
        return
    if st.tmin is None or ts < st.tmin:
        st.tmin = ts
    if st.tmax is None or ts > st.tmax:
        st.tmax = ts

def _order(st, ts):
    if ts is None:
        return
    if st.prev_ts is not None and ts < st.prev_ts:
        st.warnings.add("OUT_OF_ORDER")
        _kill(st)
    st.prev_ts = ts

def _apply_delta(st, prev, curr):
    """Add a later cumulative snapshot relative to prev; never sum last_token_usage."""
    same_total = curr == prev
    if st.dead:
        if same_total:
            st.dup_snap += 1
        return
    for key in USAGE_KEYS:
        before = prev[key]
        after = curr[key]
        if before is not None and after is not None and after < before:
            st.warnings.add("COUNTER_RESET")
            _kill(st)
            return
    for key, parent in (("cached_input_tokens", "input_tokens"),
                        ("reasoning_output_tokens", "output_tokens")):
        if prev[key] is None or curr[key] is None:
            st.warnings.add("OPTIONAL_COUNTER_MISSING")
        elif curr[key] - prev[key] > curr[parent] - prev[parent]:
            st.warnings.add("INVALID_COUNTER")
            _kill(st)
            return
    if same_total:
        st.dup_snap += 1
        if st.acc is None:
            st.acc = {
                key: (0 if prev[key] is not None and curr[key] is not None else None)
                for key in USAGE_KEYS
            }
        else:
            for key in OPTIONAL:
                if prev[key] is None or curr[key] is None:
                    st.acc[key] = None
        return
    if st.acc is None:
        st.acc = {}
        for key in USAGE_KEYS:
            before = prev[key]
            after = curr[key]
            st.acc[key] = (
                after - before if before is not None and after is not None else None
            )
        return
    for key in USAGE_KEYS:
        before = prev[key]
        after = curr[key]
        if before is None or after is None or st.acc[key] is None:
            st.acc[key] = None
        else:
            st.acc[key] += after - before

def _take_snapshot(st, usage, missing, last, start_dt):
    st.snapshots += 1
    if missing:
        st.warnings.add("OPTIONAL_COUNTER_MISSING")
    if not st.opened and start_dt is not None and st.pre is not None:
        st.known = {key: value for key, value in st.pre.items() if value is not None}
    # A missing optional field must not hide a decrease when it reappears.
    for key, value in usage.items():
        if value is not None:
            if key in st.known and value < st.known[key]:
                st.warnings.add("COUNTER_RESET")
                _kill(st)
            st.known[key] = value
    if not st.opened:
        if start_dt is not None:
            st.opened = True
            st.coverage = "between_snapshots"
            if st.pre is not None:
                if (
                    st.pre_ts is not None
                    and st.pre_ts < start_dt
                    and _advanced(st.pre, usage)
                ):
                    st.warnings.add("WINDOW_BOUNDARY_APPROXIMATE")
                _apply_delta(st, st.pre, usage)
                st.prev = usage
            else:
                st.warnings.add("WINDOW_BASELINE_MISSING")
                st.prev = usage
            return
        st.opened = True
        if _last_matches(usage, last):
            st.acc = {key: usage[key] for key in USAGE_KEYS}
            st.coverage = "from_first_usage"
            st.prev = usage
        else:
            st.warnings.add("OPENING_USAGE_EXCLUDED")
            st.coverage = "between_snapshots"
            st.prev = usage
        return
    _apply_delta(st, st.prev, usage)
    st.prev = usage

def _session_id(rec, payload):
    for blob in (payload, rec):
        if not isinstance(blob, dict):
            continue
        for key in ("id", "session_id"):
            value = blob.get(key)
            if type(value) is str and value:
                return value
        inner = blob.get("payload")
        if isinstance(inner, dict):
            for key in ("id", "session_id"):
                value = inner.get(key)
                if type(value) is str and value:
                    return value
    return None

def _offer_model(st, model, sel, ts, start_dt):
    if type(model) is not str or not model:
        return
    digest = _sha(model)
    if sel:
        st.models.add(digest)
    elif start_dt is not None and ts is not None and ts < start_dt:
        if st.pre_model_ts is None or ts >= st.pre_model_ts:
            st.pre_model = digest
            st.pre_model_ts = ts

def _handle_tool(st, body, sel):
    call_id = body.get("call_id")
    fresh = True
    if type(call_id) is str and call_id:
        call_digest = _sha(call_id)
        if call_digest in st.seen_ids:
            if sel:
                st.dup_tools += 1
            fresh = False
        else:
            st.seen_ids.add(call_digest)
    elif sel:
        st.warnings.add("TOOL_ID_MISSING")
    if sel and fresh:
        st.tools += 1
        st.cats[_classify(body.get("name"))] += 1

def _handle_token(st, payload, sel, start_dt, ts):
    info = payload.get("info")
    if info is None:
        return
    if not isinstance(info, dict):
        if sel:
            st.warnings.add("INVALID_COUNTER")
            _kill(st)
        return
    total_blob = info.get("total_token_usage")
    if not isinstance(total_blob, dict):
        if sel:
            st.warnings.add("INVALID_COUNTER")
            _kill(st)
        return
    parsed = _parse_usage(total_blob)
    if parsed == "invalid":
        if sel:
            st.warnings.add("INVALID_COUNTER")
            _kill(st)
        return
    usage, missing = parsed
    last = None
    last_blob = info.get("last_token_usage")
    if isinstance(last_blob, dict):
        last_parsed = _parse_usage(last_blob)
        if isinstance(last_parsed, tuple):
            last = last_parsed[0]
    if not sel:
        if start_dt is not None and ts is not None and ts < start_dt:
            if st.pre_ts is None or ts >= st.pre_ts:
                st.pre = usage
                st.pre_ts = ts
        return
    _take_snapshot(st, usage, missing, last, start_dt)

def _kind_of(rec_type, payload):
    if rec_type == "event_msg" and payload.get("type") == "token_count":
        return "token"
    if rec_type == "response_item" and _tool_body(payload) is not None:
        return "tool"
    if rec_type == "turn_context" or payload.get("type") == "turn_context":
        return "turn"
    if rec_type == "event_msg" and payload.get("type") == "thread_settings_applied":
        return "settings"
    return None

def _consume(st, rec, start_dt, end_dt):
    rec_type = rec.get("type")
    payload = _payload_of(rec)
    if rec_type == "session_meta" or payload.get("type") == "session_meta":
        sid = _session_id(rec, payload)
        if sid is not None:
            sid = _sha(sid)
            if st.session is None:
                st.session = sid
            elif sid != st.session:
                st.warnings.add("MIXED_SESSIONS")
                _kill(st)
    kind = _kind_of(rec_type, payload)
    if kind is None:
        return
    raw_ts = rec.get("timestamp")
    ts = _parse_ts(raw_ts) if raw_ts is not None else None
    windowed = start_dt is not None or end_dt is not None
    if raw_ts is not None and ts is None:
        st.warnings.add("INVALID_TIMESTAMP")
        _kill(st)
    elif windowed and raw_ts is None:
        st.warnings.add("INVALID_TIMESTAMP")
        _kill(st)
    sel = _in_sel(ts, start_dt, end_dt)
    if sel:
        _order(st, ts)
        st.selected_seen = True
    elif start_dt is not None and ts is not None and ts < start_dt and st.selected_seen:
        # A newly encountered earlier baseline would change already measured usage.
        st.warnings.add("OUT_OF_ORDER")
        _kill(st)
    if sel and kind in ("token", "tool", "turn"):
        _note_time(st, ts)
    if kind == "token":
        _handle_token(st, payload, sel, start_dt, ts)
        return
    if kind == "tool":
        _handle_tool(st, _tool_body(payload), sel)
        return
    _offer_model(st, _model_value(kind, payload), sel, ts, start_dt)

def _finalize(st):
    warnings = st.warnings
    if st.snapshots == 0:
        warnings.add("NO_TOKEN_DATA")
    if st.acc is None and (st.snapshots > 0 or st.pre is not None):
        warnings.add("INSUFFICIENT_SNAPSHOTS")
    if st.pre_model is not None:
        st.models.add(st.pre_model)
    unavailable = st.dead or st.acc is None or bool(warnings & HARD)
    if unavailable:
        tokens = dict(NONE_TOKENS)
        coverage = st.coverage if not st.dead and st.snapshots else "unavailable"
        quality = "unavailable"
    else:
        acc = st.acc
        inp = acc["input_tokens"]
        cached = acc["cached_input_tokens"]
        tokens = {
            "input_tokens": inp,
            "cached_input_tokens": cached,
            "uncached_input_tokens": (
                None if inp is None or cached is None else inp - cached
            ),
            "output_tokens": acc["output_tokens"],
            "reasoning_output_tokens": acc["reasoning_output_tokens"],
            "total_tokens": acc["total_tokens"],
        }
        coverage = st.coverage
        quality = "partial" if warnings else "observed"
    if st.tmin is None:
        elapsed = None
    else:
        elapsed = (st.tmax - st.tmin).total_seconds()
        if elapsed == int(elapsed):
            elapsed = int(elapsed)
    return {
        "tokens": tokens,
        "quality": quality,
        "warnings": sorted(warnings),
        "tool_calls": st.tools,
        "tool_categories": {key: st.cats[key] for key in CATEGORIES},
        "duplicate_snapshots": st.dup_snap,
        "duplicate_tool_calls": st.dup_tools,
        "token_snapshots": st.snapshots,
        "malformed_lines": st.malformed,
        "model_fingerprints": sorted(st.models),
        "elapsed_seconds": elapsed,
        "coverage": coverage,
    }

def parse_run(path, *, start=None, end=None):
    """Parse one native JSONL run into JSON-serializable observed usage.

    start/end are timezone-aware ISO-8601 strings for a half-open window
    [start, end). Naive bounds raise ParseError. Native totals are observed
    evidence, not proof of complete billing.
    """
    start_dt = _parse_bound(start)
    end_dt = _parse_bound(end)
    if start_dt is not None and end_dt is not None and start_dt >= end_dt:
        raise ParseError("invalid time window")
    if not isinstance(path, (str, Path)):
        raise ParseError("unreadable input")
    st = _State()
    try:
        with Path(path).open("rb") as fh:
            for raw in _iter_raw_lines(fh):
                if raw is None:
                    st.malformed += 1
                    continue
                if not raw.strip():
                    continue
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    st.malformed += 1
                    continue
                try:
                    rec = json.loads(text)
                except (json.JSONDecodeError, RecursionError, ValueError):
                    st.malformed += 1
                    continue
                if not isinstance(rec, dict):
                    st.malformed += 1
                    continue
                _consume(st, rec, start_dt, end_dt)
    except (OSError, ValueError):
        raise ParseError("unreadable input") from None
    if st.malformed:
        st.warnings.add("MALFORMED_LINES")
    return _finalize(st)
