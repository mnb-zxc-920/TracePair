# What the numbers mean

TracePair reads `event_msg` / `token_count` events containing `info.total_token_usage`. It never sums every `last_token_usage` event: a quota update can repeat a previous nonzero last usage while the cumulative counters stay unchanged. This behavior was reported in [OpenAI Codex issue 14489](https://github.com/openai/codex/issues/14489). The [native protocol](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs) is the format reference; the moving main branch is not a guarantee of compatibility with every Codex version.

## Opening snapshot

If the first cumulative snapshot matches its valid last-usage fields, it can describe the first observed usage. Otherwise TracePair treats it as a baseline and measures only the increments after it. The report explicitly says that opening usage was excluded. A lone excluded baseline does not establish zero usage.

Subsequent identical totals add nothing. A decrease in any known tracked cumulative field withholds the aggregate instead of guessing how to add reset segments. Missing, invalid, out-of-order or mixed-session evidence can also prevent a reliable total. The tool does not attempt to reconstruct invisible history.

Required input, output and total counters must be nonnegative integers with `total = input + output`. Present cached-input and reasoning-output counters must also be valid and fit within input and output respectively. A missing optional counter stays unknown. Context-fill estimates that do not reconcile are not relabeled as measured token usage.

The current native protocol also has a cache-write field. This version does not expose cache-write counts. It does not confuse them with cached reads.

## Time windows

Selection uses event timestamps: `start <= timestamp < end`. The last valid snapshot before the start supplies the baseline, without adding its historical usage. If there is no preceding snapshot, the first selected snapshot is excluded and a warning is recorded. An increment can describe a response that started before the boundary; that boundary is approximate, not a request-level duration measurement. Events at or after the end are excluded.

The recorded span runs between selected timestamped token, tool and turn-context records. It includes waiting and does not establish completion, time spent typing, or model-active time. Ordering failures entirely after the selected end do not invalidate an earlier window. Invalid timestamps cannot be reliably assigned to a window; mixed-session file identities also remain an integrity warning. A live file can change while being read; use a stable copy or wait until the producer has finished.

## Tool and model information

Recorded `function_call` and `custom_tool_call` response items are deduplicated by call identifier and grouped into fixed categories. Missing identifiers are flagged. A call to an orchestration wrapper counts as one recorded call; hidden nested commands are not discovered by reading the arguments. The categories describe observed activity, not which capabilities were available to the agent.

Model identifiers are hashed internally only to compare recorded sets. The reports expose matching/different/unknown and counts, without the identifiers or hashes. A matching model set does not prove matching model versions, settings, task difficulty or execution order.

## Comparison, not causation

Percent difference is `(B - A) / A`; when A is zero it is undefined. Missing totals do not produce a percentage. These are observational comparisons. They do not estimate subscription usage, money, waste, productivity or output quality. Any controlled experiment needs an independently defined task, quality criterion, conditions and repeated samples.
