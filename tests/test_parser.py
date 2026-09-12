"""Public parser contract tests using only invented, local JSONL records."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tracepair.parser import ParseError, parse_run


TOKEN_KEYS = (
    "input_tokens", "cached_input_tokens", "uncached_input_tokens",
    "output_tokens", "reasoning_output_tokens", "total_tokens",
)
CATEGORIES = ("shell", "files", "web", "agents", "code", "other")
WARNING_CODES = {
    "OPTIONAL_COUNTER_MISSING", "INVALID_COUNTER", "OPENING_USAGE_EXCLUDED",
    "INSUFFICIENT_SNAPSHOTS", "COUNTER_RESET", "WINDOW_BASELINE_MISSING",
    "WINDOW_BOUNDARY_APPROXIMATE", "INVALID_TIMESTAMP", "OUT_OF_ORDER",
    "MIXED_SESSIONS", "TOOL_ID_MISSING", "NO_TOKEN_DATA", "MALFORMED_LINES",
}
RESULT_KEYS = {
    "tokens", "quality", "warnings", "tool_calls", "tool_categories",
    "duplicate_snapshots", "duplicate_tool_calls", "token_snapshots",
    "malformed_lines", "model_fingerprints", "elapsed_seconds", "coverage",
}
_OMITTED = object()


def usage(input_tokens, cached, output_tokens, reasoning):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning,
        "total_tokens": input_tokens + output_tokens,
    }


ZERO = usage(0, 0, 0, 0)
FIRST = usage(100, 40, 20, 10)
SECOND = usage(150, 60, 35, 14)
THIRD = usage(190, 70, 50, 20)


def stamp(second):
    return f"2026-01-01T00:00:{second:02d}Z"


def snapshot(second, total, last=_OMITTED):
    info = {"total_token_usage": dict(total)}
    if last is not _OMITTED:
        info["last_token_usage"] = dict(last) if isinstance(last, dict) else last
    return {
        "timestamp": stamp(second), "type": "event_msg",
        "payload": {"type": "token_count", "info": info},
    }


def tool(second, name, call_id=_OMITTED, kind="function_call"):
    payload = {"type": kind, "name": name, "arguments": "{}"}
    if call_id is not _OMITTED:
        payload["call_id"] = call_id
    return {"timestamp": stamp(second), "type": "response_item", "payload": payload}


def context(second, model=_OMITTED):
    payload = {} if model is _OMITTED else {"model": model}
    return {"timestamp": stamp(second), "type": "turn_context", "payload": payload}


def session(second, identifier):
    return {
        "timestamp": stamp(second), "type": "session_meta",
        "payload": {"id": identifier},
    }


def line(event):
    return json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"


class ParseRunContractTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="tracepair_synthetic_")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "invented-run.jsonl"

    def read(self, events, **window):
        self.path.write_bytes(b"".join(line(event) for event in events))
        result = parse_run(self.path, **window)
        self.assert_schema(result)
        return result

    def read_bytes(self, data, **window):
        self.path.write_bytes(data)
        result = parse_run(str(self.path), **window)
        self.assert_schema(result)
        return result

    def assert_schema(self, result):
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(set(result["tokens"]), set(TOKEN_KEYS))
        for value in result["tokens"].values():
            self.assertTrue(value is None or (type(value) is int and value >= 0))
        self.assertIn(result["quality"], {"observed", "partial", "unavailable"})
        self.assertIn(result["coverage"], {
            "from_first_usage", "between_snapshots", "unavailable",
        })
        self.assertIsInstance(result["warnings"], list)
        self.assertEqual(result["warnings"], sorted(result["warnings"]))
        self.assertLessEqual(set(result["warnings"]), WARNING_CODES)
        self.assertEqual(set(result["tool_categories"]), set(CATEGORIES))
        for key in (
            "tool_calls", "duplicate_snapshots", "duplicate_tool_calls",
            "token_snapshots", "malformed_lines",
        ):
            self.assertIs(type(result[key]), int)
            self.assertGreaterEqual(result[key], 0)
        for value in result["tool_categories"].values():
            self.assertIs(type(value), int)
            self.assertGreaterEqual(value, 0)
        self.assertEqual(sum(result["tool_categories"].values()), result["tool_calls"])
        fingerprints = result["model_fingerprints"]
        self.assertIsInstance(fingerprints, list)
        self.assertEqual(fingerprints, sorted(set(fingerprints)))
        for fingerprint in fingerprints:
            self.assertRegex(fingerprint, r"\A[0-9a-f]{64}\Z")
        elapsed = result["elapsed_seconds"]
        if elapsed is not None:
            self.assertIn(type(elapsed), (int, float))
            self.assertGreaterEqual(elapsed, 0)
        json.dumps(result, allow_nan=False)

    def assert_tokens(self, result, input_tokens, cached, uncached, output, reasoning, total):
        self.assertEqual(result["tokens"], dict(zip(
            TOKEN_KEYS, (input_tokens, cached, uncached, output, reasoning, total),
        )))

    def assert_unknown(self, result, warning):
        self.assertEqual(result["tokens"], dict.fromkeys(TOKEN_KEYS))
        self.assertEqual(result["quality"], "unavailable")
        self.assertIn(warning, result["warnings"])

    def test_fresh_first_snapshot_is_observed_usage(self):
        result = self.read([snapshot(0, FIRST, FIRST)])
        self.assert_tokens(result, 100, 40, 60, 20, 10, 120)
        self.assertEqual(result["quality"], "observed")
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["coverage"], "from_first_usage")
        self.assertEqual(result["token_snapshots"], 1)
        self.assertEqual(result["elapsed_seconds"], 0)

    def test_duplicate_cumulative_totals_ignore_nonzero_last_usage(self):
        result = self.read([
            snapshot(0, FIRST, FIRST), snapshot(1, FIRST, FIRST),
            snapshot(2, SECOND, FIRST), snapshot(3, SECOND, FIRST),
            snapshot(4, THIRD, FIRST),
        ])
        self.assert_tokens(result, 190, 70, 120, 50, 20, 240)
        self.assertEqual(result["duplicate_snapshots"], 2)
        self.assertEqual(result["token_snapshots"], 5)
        self.assertEqual(result["quality"], "observed")
        self.assertEqual(result["elapsed_seconds"], 4)

    def test_resumed_first_snapshot_is_an_excluded_baseline(self):
        result = self.read([
            snapshot(0, FIRST, usage(8, 3, 2, 1)), snapshot(10, SECOND),
        ])
        self.assert_tokens(result, 50, 20, 30, 15, 4, 65)
        self.assertEqual(result["coverage"], "between_snapshots")
        self.assertEqual(result["quality"], "partial")
        self.assertIn("OPENING_USAGE_EXCLUDED", result["warnings"])

    def test_single_resumed_baseline_has_unknown_usage(self):
        result = self.read([snapshot(0, FIRST)])
        self.assert_unknown(result, "INSUFFICIENT_SNAPSHOTS")
        self.assertIn("OPENING_USAGE_EXCLUDED", result["warnings"])
        self.assertEqual(result["coverage"], "between_snapshots")
        self.assertEqual(result["token_snapshots"], 1)

    def test_exact_initial_zero_is_known_zero(self):
        result = self.read([snapshot(0, ZERO, ZERO)])
        self.assert_tokens(result, 0, 0, 0, 0, 0, 0)
        self.assertEqual(result["quality"], "observed")
        self.assertEqual(result["coverage"], "from_first_usage")
        self.assertEqual(result["warnings"], [])

    def test_reset_of_any_tracked_counter_invalidates_all_tokens(self):
        resets = {
            "input": usage(90, 40, 30, 10),
            "output": usage(120, 40, 15, 10),
            "cached": usage(110, 39, 30, 10),
            "reasoning": usage(110, 40, 30, 9),
            "total": usage(90, 40, 19, 10),
        }
        for counter, decreased in resets.items():
            with self.subTest(counter=counter):
                result = self.read([
                    snapshot(0, FIRST, FIRST), snapshot(1, decreased),
                    snapshot(2, THIRD), tool(3, "exec_command", "reset-tool"),
                ])
                self.assert_unknown(result, "COUNTER_RESET")
                self.assertEqual(result["tool_calls"], 1)

    def test_invalid_required_counters_fail_closed_and_maximum_is_valid(self):
        for field in ("input_tokens", "output_tokens", "total_tokens"):
            for bad in (True, 1.0, -1, "150", None, 2**63, _OMITTED):
                with self.subTest(field=field, bad=repr(bad)):
                    invalid = dict(SECOND)
                    if bad is _OMITTED:
                        invalid.pop(field)
                    else:
                        invalid[field] = bad
                    result = self.read([
                        snapshot(0, FIRST, FIRST), snapshot(1, invalid),
                        snapshot(2, THIRD), tool(3, "read_file", "invalid-tool"),
                    ])
                    self.assert_unknown(result, "INVALID_COUNTER")
                    self.assertEqual(result["tool_calls"], 1)
        inconsistent = dict(FIRST, total_tokens=121)
        self.assert_unknown(self.read([snapshot(0, inconsistent, inconsistent)]), "INVALID_COUNTER")
        maximum = usage(2**63 - 2, 0, 1, 0)
        result = self.read([snapshot(0, maximum, maximum)])
        self.assert_tokens(result, 2**63 - 2, 0, 2**63 - 2, 1, 0, 2**63 - 1)

    def test_present_but_invalid_optional_counters_are_hard_failures(self):
        for field, above_parent in (
            ("cached_input_tokens", 151), ("reasoning_output_tokens", 36),
        ):
            for bad in (False, 0.0, -1, "0", None, 2**63, above_parent):
                with self.subTest(field=field, bad=bad):
                    invalid = dict(SECOND)
                    invalid[field] = bad
                    result = self.read([
                        snapshot(0, FIRST, FIRST), snapshot(1, invalid), snapshot(2, THIRD),
                    ])
                    self.assert_unknown(result, "INVALID_COUNTER")

    def test_missing_optional_counters_remain_independently_unknown(self):
        cases = [
            (("cached_input_tokens",), (100, None, None, 20, 10, 120)),
            (("reasoning_output_tokens",), (100, 40, 60, 20, None, 120)),
            (("cached_input_tokens", "reasoning_output_tokens"),
             (100, None, None, 20, None, 120)),
        ]
        for missing, expected in cases:
            with self.subTest(missing=missing):
                counters = {key: value for key, value in FIRST.items() if key not in missing}
                result = self.read([snapshot(0, counters, counters)])
                self.assert_tokens(result, *expected)
                self.assertEqual(result["quality"], "partial")
                self.assertIn("OPTIONAL_COUNTER_MISSING", result["warnings"])
                self.assertEqual(result["coverage"], "from_first_usage")

    def test_first_last_requires_valid_matching_required_and_optional_fields(self):
        missing_cache = dict(FIRST)
        missing_cache.pop("cached_input_tokens")
        alternatives = {
            "absent": _OMITTED, "null": None, "not_object": [],
            "required_mismatch": usage(99, 40, 20, 10),
            "optional_mismatch": dict(FIRST, cached_input_tokens=39),
            "optional_absent": missing_cache,
            "invalid_type": dict(FIRST, input_tokens=True),
        }
        for label, last in alternatives.items():
            with self.subTest(last=label):
                result = self.read([snapshot(0, FIRST, last), snapshot(10, SECOND)])
                self.assert_tokens(result, 50, 20, 30, 15, 4, 65)
                self.assertEqual(result["coverage"], "between_snapshots")
                self.assertIn("OPENING_USAGE_EXCLUDED", result["warnings"])

    def test_optional_counters_appearing_or_disappearing_do_not_recover_known_totals(self):
        for field in ("cached_input_tokens", "reasoning_output_tokens"):
            for missing_positions in ((0,), (1,), (0, 1)):
                with self.subTest(field=field, missing_positions=missing_positions):
                    totals = [dict(FIRST), dict(SECOND), dict(THIRD)]
                    for position in missing_positions:
                        totals[position].pop(field)
                    result = self.read([
                        snapshot(0, totals[0], totals[0]),
                        snapshot(1, totals[1]), snapshot(2, totals[2]),
                    ])
                    if field == "cached_input_tokens":
                        self.assert_tokens(result, 190, None, None, 50, 20, 240)
                    else:
                        self.assert_tokens(result, 190, 70, 120, 50, None, 240)
                    self.assertIn("OPTIONAL_COUNTER_MISSING", result["warnings"])
                    self.assertEqual(result["quality"], "partial")

    def test_window_uses_last_prestart_snapshot_without_adding_its_usage(self):
        result = self.read([
            snapshot(0, ZERO, ZERO), snapshot(10, FIRST), snapshot(20, SECOND),
        ], start=stamp(15), end=stamp(25))
        self.assert_tokens(result, 50, 20, 30, 15, 4, 65)
        self.assertIn("WINDOW_BOUNDARY_APPROXIMATE", result["warnings"])
        self.assertEqual(result["coverage"], "between_snapshots")
        self.assertEqual(result["token_snapshots"], 1)
        self.assertEqual(result["elapsed_seconds"], 0)

    def test_window_start_is_inclusive_end_is_exclusive(self):
        result = self.read([
            snapshot(10, FIRST), snapshot(20, SECOND),
            tool(21, "exec_command", "inside-window"),
            snapshot(30, THIRD), tool(30, "read_file", "at-end"),
            snapshot(40, ZERO, ZERO),
        ], start=stamp(20), end=stamp(30))
        self.assert_tokens(result, 50, 20, 30, 15, 4, 65)
        self.assertEqual(result["token_snapshots"], 1)
        self.assertEqual(result["tool_calls"], 1)
        self.assertNotIn("COUNTER_RESET", result["warnings"])
        self.assertEqual(result["elapsed_seconds"], 1)

    def test_window_without_baseline_excludes_even_a_fresh_first_total(self):
        result = self.read([
            snapshot(10, FIRST, FIRST), snapshot(20, SECOND),
        ], start=stamp(5), end=stamp(25))
        self.assert_tokens(result, 50, 20, 30, 15, 4, 65)
        self.assertIn("WINDOW_BASELINE_MISSING", result["warnings"])
        self.assertEqual(result["coverage"], "between_snapshots")
        self.assertEqual(result["quality"], "partial")

    def test_single_window_snapshot_without_baseline_is_unknown(self):
        result = self.read([snapshot(10, FIRST, FIRST)], start=stamp(5), end=stamp(15))
        self.assert_unknown(result, "INSUFFICIENT_SNAPSHOTS")
        self.assertIn("WINDOW_BASELINE_MISSING", result["warnings"])
        self.assertEqual(result["token_snapshots"], 1)

    def test_prestart_baseline_without_selected_tokens_is_not_usage(self):
        result = self.read([
            snapshot(0, FIRST, FIRST), snapshot(30, SECOND),
        ], start=stamp(10), end=stamp(20))
        self.assert_unknown(result, "NO_TOKEN_DATA")
        self.assertEqual(result["coverage"], "unavailable")
        self.assertEqual(result["token_snapshots"], 0)
        self.assertIsNone(result["elapsed_seconds"])

    def test_end_only_window_does_not_include_future_usage_or_models(self):
        result = self.read([
            snapshot(10, FIRST, FIRST), context(19, "synthetic-model-before-end"),
            snapshot(20, SECOND), tool(20, "read_file", "future-call"),
            context(20, "synthetic-model-after-end"),
        ], end=stamp(20))
        self.assert_tokens(result, 100, 40, 60, 20, 10, 120)
        self.assertEqual(result["tool_calls"], 0)
        self.assertEqual(result["elapsed_seconds"], 9)
        self.assertEqual(result["model_fingerprints"], [
            hashlib.sha256(b"synthetic-model-before-end").hexdigest(),
        ])

    def test_invalid_windows_raise_generic_parse_errors(self):
        self.path.write_bytes(line(snapshot(0, FIRST, FIRST)))
        invalid_windows = [
            {"start": "2026-01-01T00:00:00"},
            {"end": "2026-01-01T00:00:10"},
            {"start": "SYNTHETIC_PRIVATE_WINDOW_MARKER"},
            {"end": "SYNTHETIC_DIFFERENT_WINDOW_MARKER"},
            {"start": stamp(10), "end": stamp(10)},
            {"start": stamp(20), "end": stamp(10)},
        ]
        self.assertTrue(issubclass(ParseError, ValueError))
        for window in invalid_windows:
            with self.subTest(window=window):
                with self.assertRaises(ParseError) as raised:
                    parse_run(self.path, **window)
                message = str(raised.exception)
                self.assertTrue(message)
                self.assertNotIn(str(self.path), message)
                for supplied in window.values():
                    self.assertNotIn(supplied, message)
                self.assertNotIn("SYNTHETIC_", message)

    def test_unselectable_relevant_timestamps_make_window_usage_unavailable(self):
        for kind in ("token", "tool", "context"):
            for bad in (_OMITTED, "invented-invalid-time", "2026-01-01T00:00:10"):
                with self.subTest(kind=kind, timestamp=repr(bad)):
                    event = {
                        "token": snapshot(10, SECOND),
                        "tool": tool(10, "exec_command", "bad-timestamp-call"),
                        "context": context(10, "invented-model"),
                    }[kind]
                    if bad is _OMITTED:
                        event.pop("timestamp")
                    else:
                        event["timestamp"] = bad
                    result = self.read([
                        snapshot(0, FIRST, FIRST), event, snapshot(20, THIRD),
                    ], start=stamp(5), end=stamp(30))
                    self.assert_unknown(result, "INVALID_TIMESTAMP")

    def test_out_of_order_token_tool_and_context_events_invalidate_whole_run(self):
        for earlier in (
            snapshot(10, SECOND), tool(10, "python", "out-of-order-call"),
            context(10, "invented-earlier-model"),
        ):
            with self.subTest(event_type=earlier["type"]):
                result = self.read([
                    snapshot(20, FIRST, FIRST), earlier, snapshot(30, THIRD),
                ])
                self.assert_unknown(result, "OUT_OF_ORDER")

    def test_bom_blank_lines_and_malformed_records_preserve_valid_observations(self):
        result = self.read_bytes(
            b"\xef\xbb\xbf\n \t\r\n" + line(snapshot(0, FIRST, FIRST))
            + b"{invalid-json\n\xff\n[]\nnull\n\"not-an-object\"\n"
            + line(snapshot(10, SECOND))
        )
        self.assert_tokens(result, 150, 60, 90, 35, 14, 185)
        self.assertEqual(result["malformed_lines"], 5)
        self.assertEqual(result["token_snapshots"], 2)
        self.assertEqual(result["quality"], "partial")
        self.assertIn("MALFORMED_LINES", result["warnings"])

    def test_oversized_valid_json_line_is_skipped_and_fully_drained(self):
        oversized = b'{"invented_padding":"' + b"x" * (16 * 1024 * 1024) + b'"}\n'
        result = self.read_bytes(
            line(snapshot(0, FIRST, FIRST)) + oversized + line(snapshot(10, SECOND)),
        )
        self.assert_tokens(result, 150, 60, 90, 35, 14, 185)
        self.assertEqual(result["malformed_lines"], 1)
        self.assertEqual(result["token_snapshots"], 2)
        self.assertIn("MALFORMED_LINES", result["warnings"])

    def test_unknown_event_types_and_null_info_do_not_invent_usage_or_tools(self):
        ignored = [
            {"type": "event_msg", "payload": {"type": "token_count", "info": None}},
            {"type": "invented_event", "timestamp": "bad", "total_token_usage": THIRD},
            {"type": "event_msg", "payload": {"type": "invented", "info": {"total_token_usage": THIRD}}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "invented-output"}},
            {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "invented-output"}},
            {"type": "token_count", "info": {"total_token_usage": THIRD}},
        ]
        result = self.read([snapshot(10, FIRST, FIRST), *ignored])
        self.assert_tokens(result, 100, 40, 60, 20, 10, 120)
        self.assertEqual(result["token_snapshots"], 1)
        self.assertEqual(result["tool_calls"], 0)
        self.assertEqual(result["quality"], "observed")
        empty = self.read(ignored)
        self.assert_unknown(empty, "NO_TOKEN_DATA")
        self.assertEqual(empty["token_snapshots"], 0)
        self.assertEqual(empty["tool_calls"], 0)

    def test_only_native_tool_invocations_count_with_fixed_name_categories(self):
        names = {
            "shell": ("exec_command", "shell_command", "bash"),
            "files": ("apply_patch", "read_file", "write_file"),
            "web": ("web.run", "web__run", "browser"),
            "agents": ("spawn_agent", "send_message", "wait_agent", "followup_task"),
            "code": ("exec", "python"),
            "other": ("invented.private.tool", "shell", "python3"),
        }
        events = []
        for category_names in names.values():
            for name in category_names:
                for prefix, kind in (("", "function_call"), ("functions.", "custom_tool_call")):
                    event = tool(10, prefix + name, f"synthetic-call-{len(events)}", kind)
                    event["payload"]["arguments"] = json.dumps({
                        "tool_uses": [{"recipient_name": "functions.exec_command"}] * 3,
                    })
                    events.append(event)
        events.extend([
            {"timestamp": stamp(10), "type": "event_msg", "payload": {"type": "function_call", "name": "bash"}},
            tool(10, "bash", "wrong-payload-type", "tool_call"),
            tool(10, "bash", "output-only", "function_call_output"),
        ])
        result = self.read(events)
        self.assertEqual(result["tool_categories"], {
            "shell": 6, "files": 6, "web": 6, "agents": 8, "code": 4, "other": 6,
        })
        self.assertEqual(result["tool_calls"], 36)
        self.assertEqual(result["duplicate_tool_calls"], 0)
        self.assert_unknown(result, "NO_TOKEN_DATA")

    def test_tool_ids_dedupe_across_whole_file_and_missing_ids_count(self):
        result = self.read([
            tool(0, "exec_command", "seen-before-window"),
            tool(10, "exec_command", "seen-before-window", "custom_tool_call"),
            tool(11, "exec_command", "new-in-window"),
            tool(12, "exec_command", "new-in-window"),
            tool(13, "read_file"), tool(14, "invented-tool"),
        ], start=stamp(5), end=stamp(20))
        self.assertEqual(result["tool_calls"], 3)
        self.assertEqual(result["duplicate_tool_calls"], 2)
        self.assertEqual(result["tool_categories"], {
            "shell": 1, "files": 1, "web": 0, "agents": 0, "code": 0, "other": 1,
        })
        self.assertIn("TOOL_ID_MISSING", result["warnings"])

    def test_model_fingerprints_include_start_model_and_selected_changes_only(self):
        selected_settings = {
            "timestamp": stamp(20), "type": "event_msg",
            "payload": {
                "type": "thread_settings_applied",
                "thread_settings": {"model": "synthetic-model-B"},
            },
        }
        result = self.read([
            context(0, "synthetic-obsolete-model"), context(10, "synthetic-model-A"),
            selected_settings, context(25, "synthetic-model-B"),
            context(30, "synthetic-future-model"),
        ], start=stamp(15), end=stamp(30))
        self.assertEqual(result["model_fingerprints"], sorted([
            hashlib.sha256(b"synthetic-model-A").hexdigest(),
            hashlib.sha256(b"synthetic-model-B").hexdigest(),
        ]))
        unknown = self.read([context(0), snapshot(1, ZERO, ZERO)])
        self.assertEqual(unknown["model_fingerprints"], [])

    def test_session_id_change_invalidates_usage_but_repeated_id_does_not(self):
        for later_id, mixed in (("synthetic-session-A", False), ("synthetic-session-B", True)):
            with self.subTest(mixed=mixed):
                result = self.read([
                    session(0, "synthetic-session-A"), snapshot(1, FIRST, FIRST),
                    session(2, later_id), snapshot(3, SECOND), tool(4, "bash", "mixed-session-tool"),
                ])
                self.assertEqual(result["tool_calls"], 1)
                if mixed:
                    self.assert_unknown(result, "MIXED_SESSIONS")
                else:
                    self.assert_tokens(result, 150, 60, 90, 35, 14, 185)
                    self.assertNotIn("MIXED_SESSIONS", result["warnings"])

    def test_elapsed_span_uses_relevant_events_and_normalizes_timezone_offsets(self):
        first_context = context(0)
        first_context["timestamp"] = "2026-01-01T08:00:00+08:00"
        last_tool = tool(5, "python", "elapsed-tool")
        last_tool["timestamp"] = "2026-01-01T01:00:05+01:00"
        result = self.read([
            first_context, snapshot(2, FIRST, FIRST), last_tool,
            {"timestamp": stamp(20), "type": "response_item", "payload": {"type": "message", "text": "invented"}},
        ])
        self.assertEqual(result["elapsed_seconds"], 5)
        self.assertEqual(result["quality"], "observed")
        self.assert_tokens(result, 100, 40, 60, 20, 10, 120)
        self.assertEqual(self.read([tool(5, "python", "only-tool")])["elapsed_seconds"], 0)
        self.assertIsNone(self.read([])["elapsed_seconds"])

    def test_unreadable_input_raises_fixed_generic_error_without_path(self):
        messages = []
        for basename in ("SYNTHETIC_PRIVATE_PATH_A.jsonl", "SYNTHETIC_PRIVATE_PATH_B.jsonl"):
            path = self.root / basename
            with self.subTest(basename=basename):
                with self.assertRaises(ParseError) as raised:
                    parse_run(path)
                message = str(raised.exception)
                self.assertTrue(message)
                self.assertNotIn(basename, message)
                self.assertNotIn(str(self.root), message)
                messages.append(message)
        self.assertEqual(messages[0], messages[1])

    def test_result_contains_no_raw_secret_path_text_ids_names_or_timestamps(self):
        markers = {
            "filename": "SYNTHETIC_PRIVATE_FILENAME.jsonl",
            "session": "SYNTHETIC_PRIVATE_SESSION_ID",
            "call": "SYNTHETIC_PRIVATE_CALL_ID",
            "tool": "SYNTHETIC_PRIVATE_TOOL_NAME",
            "model": "SYNTHETIC_PRIVATE_MODEL_NAME",
            "arguments": "SYNTHETIC_PRIVATE_ARGUMENT_SECRET",
            "output": "SYNTHETIC_PRIVATE_OUTPUT_TEXT",
            "text": "SYNTHETIC_PRIVATE_MESSAGE_TEXT",
            "malformed": "SYNTHETIC_PRIVATE_MALFORMED_SECRET",
        }
        invocation = tool(3, markers["tool"], markers["call"])
        invocation["payload"]["arguments"] = markers["arguments"]
        events = [
            session(0, markers["session"]), context(1, markers["model"]),
            snapshot(2, FIRST, FIRST), invocation,
            {"timestamp": stamp(4), "type": "response_item", "payload": {
                "type": "function_call_output", "call_id": markers["call"], "output": markers["output"],
            }},
            {"timestamp": stamp(5), "type": "response_item", "payload": {
                "type": "message", "text": markers["text"],
            }},
        ]
        path = self.root / markers["filename"]
        path.write_bytes(b"".join(line(event) for event in events) + markers["malformed"].encode() + b"\n")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = parse_run(path)
        self.assert_schema(result)
        exported = json.dumps(result, ensure_ascii=False) + stdout.getvalue() + stderr.getvalue()
        for marker in (*markers.values(), str(path), str(self.root), *(stamp(i) for i in range(6))):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, exported)
        self.assertEqual(result["model_fingerprints"], [
            hashlib.sha256(markers["model"].encode()).hexdigest(),
        ])
        self.assertEqual(result["tool_categories"]["other"], 1)
        self.assert_tokens(result, 100, 40, 60, 20, 10, 120)


if __name__ == "__main__":
    unittest.main()
