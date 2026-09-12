# Local inputs, minimized outputs

The application reads only the two input files you specify. It makes no network requests, runs no model, installs no hooks, changes no Codex settings, and has no telemetry. Its generated HTML and SVG fetch no remote scripts, fonts or images. The source link is a normal link that you choose to follow.

JSON parsing necessarily reads input lines. Their prompt text, tool arguments, tool results, paths and arbitrary names are not copied to the aggregate report. Export fields are explicitly selected: counts, fixed warning messages, accounting coverage, model-set relationship and tool categories. Model fingerprints used internally do not enter the output files. There are no user-supplied report labels that could accidentally carry prompt text.

This is **data minimization**, not a promise of anonymity. Counts, durations and tool categories can reveal information about your work. Review all three files before sharing them. The application is not a confidential-data sanitizer for arbitrary input schemas.

Use synthetic examples when filing issues. Never attach personal or customer logs, API keys, cookies, credentials or private transcripts. If a problem can only be reproduced with a real log, reduce it locally to fabricated records that keep the same counter/timestamp structure.

Output directories must be new. Inputs are opened for reading only. A write failure may leave a partial new output directory; TracePair reports the failure and does not remove unrelated files.
