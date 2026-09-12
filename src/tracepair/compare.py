"""Project parser output into a small, explicitly shareable comparison."""
from . import __version__

TOKEN_KEYS = (
    "input_tokens", "cached_input_tokens", "uncached_input_tokens",
    "output_tokens", "reasoning_output_tokens", "total_tokens",
)
CATEGORIES = ("shell", "files", "web", "agents", "code", "other")
WARNINGS = {
    "MALFORMED_LINES": "Some lines could not be read; this log may be incomplete.",
    "OPTIONAL_COUNTER_MISSING": "Cached or reasoning counters are missing. Missing is not zero.",
    "INVALID_COUNTER": "A native counter is invalid or internally inconsistent. Token totals are withheld.",
    "OPENING_USAGE_EXCLUDED": "The first cumulative snapshot is a baseline. Earlier usage is excluded.",
    "COUNTER_RESET": "Cumulative counters decreased. A reliable combined token total is unavailable.",
    "INSUFFICIENT_SNAPSHOTS": "There is a baseline but not enough data to measure usage after it.",
    "WINDOW_BASELINE_MISSING": "No snapshot precedes the window. The first selected snapshot is excluded.",
    "WINDOW_BOUNDARY_APPROXIMATE": "Usage is assigned by snapshot time; the start boundary is approximate.",
    "INVALID_TIMESTAMP": "A relevant timestamp is missing or invalid. The selected usage is uncertain.",
    "OUT_OF_ORDER": "Relevant timestamps are out of order. Token totals are withheld.",
    "MIXED_SESSIONS": "The file contains different session identifiers. Token totals are withheld.",
    "TOOL_ID_MISSING": "Some tool calls lack an identifier and cannot be deduplicated reliably.",
    "NO_TOKEN_DATA": "No usable native token snapshots were found.",
}


def change(a, b):
    """Percent change is undefined for a zero baseline, including zero to zero."""
    if a is None or b is None:
        return {"absolute": None, "percent": None}
    return {"absolute": b - a, "percent": round((b - a) / a * 100, 1) if a else None}


def _export(run):
    # Deliberate projection: adding a parser field never silently publishes it.
    return {
        "tokens": {key: run["tokens"].get(key) for key in TOKEN_KEYS},
        "quality": run["quality"], "coverage": run["coverage"],
        "warnings": [code for code in run["warnings"] if code in WARNINGS],
        "tool_calls": run["tool_calls"],
        "tool_categories": {key: run["tool_categories"].get(key, 0) for key in CATEGORIES},
        "duplicate_snapshots": run["duplicate_snapshots"],
        "duplicate_tool_calls": run["duplicate_tool_calls"],
        "token_snapshots": run["token_snapshots"],
        "malformed_lines": run["malformed_lines"],
        "elapsed_seconds": run["elapsed_seconds"],
        "model_count": len(run["model_fingerprints"]),
    }


def compare_runs(a, b, *, synthetic=False):
    """Keep private fingerprints internal, and never infer equal task quality."""
    notes = []
    models_a, models_b = set(a["model_fingerprints"]), set(b["model_fingerprints"])
    if not models_a or not models_b:
        model_relation = "unknown"
        notes.append("Model metadata is missing in at least one run.")
    elif models_a != models_b:
        model_relation = "different"
        notes.append("The recorded model sets differ. This is not a controlled model comparison.")
    else:
        model_relation = "matching"
    if len(models_a) > 1 or len(models_b) > 1:
        notes.append("At least one run records multiple models.")
    if a["coverage"] != b["coverage"]:
        notes.append("The logs have different accounting coverage.")
    if a["quality"] != "observed" or b["quality"] != "observed":
        notes.append("At least one log has data gaps. Read the accounting notes below.")
    ta, tb = a["elapsed_seconds"], b["elapsed_seconds"]
    if ta is not None and tb is not None and ta != tb:
        notes.append("The recorded spans differ; idle time and task complexity are not measured.")
    ca = {key for key in CATEGORIES if a["tool_categories"].get(key, 0)}
    cb = {key for key in CATEGORIES if b["tool_categories"].get(key, 0)}
    if ca != cb:
        notes.append("The observed tool categories differ; tool availability is not known.")
    return {
        "schema": "tracepair.comparison.v1", "version": __version__,
        "synthetic": bool(synthetic), "runs": {"A": _export(a), "B": _export(b)},
        "changes": {key: change(a["tokens"].get(key), b["tokens"].get(key)) for key in TOKEN_KEYS},
        "model_relation": model_relation, "comparison_notes": notes,
        "interpretation": "Differences describe these logs. They do not prove savings, productivity, task completion, or equal output quality.",
        "privacy": "Exports contain aggregate counts and fixed notes, not raw conversations, paths, session IDs, model names, or custom tool names. Aggregates can still be sensitive; review before sharing.",
    }
