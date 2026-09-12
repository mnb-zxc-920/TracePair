# TracePair contribution rules

TracePair is a small, offline comparison tool for explicit Codex JSONL files.
Keep its runtime in the Python standard library. Do not add telemetry, network
calls, log auto-discovery, hooks, background monitoring, or transcript exports.

Use synthetic fixtures. Never commit personal logs, paths, account IDs, secrets,
or customer data. Unknown counters must remain unknown. Token differences are
observations, not proof of cost savings, productivity, or task quality.

Keep changes small and independently reviewed. Run `python -m unittest discover
-s tests -v` and the demo before claiming support. Preserve input files and
refuse to replace an existing output directory. Public documentation must match
the currently delivered behavior.
