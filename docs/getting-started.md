# Your first TracePair comparison

[中文](getting-started.zh-CN.md) · [README](../README.md) · [View the synthetic demo](https://mnb-zxc-920.github.io/TracePair/)

Start with the built-in demo. It needs no Codex account, API key or personal logs. Python 3.10+ must already be installed; use `python3` if that is your Python command.

## Get the tool and run the demo

Choose one way to get the source:

- With Git: run `git clone https://github.com/mnb-zxc-920/TracePair.git`, then `cd TracePair`.
- Without Git: download `tracepair-v0.1.1-source.zip` from the [release page](https://github.com/mnb-zxc-920/TracePair/releases/tag/v0.1.1), extract it, and open a terminal in the extracted `TracePair-0.1.1` folder. This folder contains `tracepair.py`. Do not run the command inside an unopened ZIP or from the parent Downloads folder.

Run:

```sh
python tracepair.py demo --out my-demo
```

Open `my-demo/report.html` in a browser. The same folder also contains `summary.json` and `share.svg`. This is a synthetic example, not evidence of improved performance.

## Choose your two logs

Codex stores session transcripts under `CODEX_HOME/sessions` and archived sessions under `CODEX_HOME/archived_sessions`. The default Codex home is `~/.codex`. [Official log locations](https://learn.chatgpt.com/docs/reference/troubleshooting#feedback-and-logs) · [Codex home setting](https://learn.chatgpt.com/docs/config-file/config-advanced#config-and-state-locations).

- On Windows with the default location, paste `%USERPROFILE%\.codex\sessions` into File Explorer's address bar. For archived sessions use `%USERPROFILE%\.codex\archived_sessions`.
- On macOS or Linux with the default location, open `~/.codex/sessions` or `~/.codex/archived_sessions` in your file manager.
- If `CODEX_HOME` is customized, use its existing value instead. If Codex ran in WSL or on another machine, check that environment's Codex home.

Inside that location, select the two session `.jsonl` files for the work you want to inspect. Browse any subfolders your installation uses. Do not pass the parent folder, `history.jsonl`, a text chat export, or an app diagnostic log. If no local rollout exists, this version of TracePair cannot retrieve one from a cloud service.

Use sessions that have stopped writing. A file can include many turns; comparing the whole file compares its observed session usage. To focus on two periods, use the [explicit time-window options](../README.md#compare-windows-in-longer-sessions). Matching model sets alone does not make two tasks comparable.

## Compare the selected files

Replace the two example paths with the files you selected. Quotes handle spaces:

```sh
python tracepair.py compare "/path/to/run-a.jsonl" "/path/to/run-b.jsonl" --out my-comparison
```

Windows example:

```powershell
python tracepair.py compare "C:\my logs\run-a.jsonl" "C:\my logs\run-b.jsonl" --out my-comparison
```

Open `my-comparison/report.html`. The logs stay on your machine. Review aggregates before sharing; they can still reveal sensitive information.

## If something looks wrong

| Message or symptom | Next step |
| --- | --- |
| Python cannot find `tracepair.py` | Open the terminal in the source folder that contains that file. |
| An input error labeled `Run A` or `Run B` | Check the indicated input: A is the first file and B is the second. Choose an existing readable Codex JSONL file, not a folder; quote paths containing spaces. |
| `Output directory already exists` | Choose another name, for example `--out my-comparison-2`. Existing reports are preserved. |
| `Invalid time window` labeled `Run A` or `Run B` | Check the named `--a-start` / `--a-end` or `--b-start` / `--b-end` options. Give ISO 8601 bounds with a timezone, for example `2026-01-01T09:00:00Z` or `2026-01-01T17:00:00+08:00`. When both are set, the end must be later than the start. Values and paths are omitted from these errors. |
| `Accounting gaps detected` or `Unknown` | Open the report's **Accounting notes**. A missing field is not a measured zero. |
| `NO_TOKEN_DATA` | Check that the chosen file is a Codex session rollout. It may contain no usable token snapshots, or the format may be unsupported. |
| `COUNTER_RESET` or `INVALID_COUNTER` | Totals are withheld because the counters cannot support a reliable total; see the [accounting rules](accounting.md). |

For a bug report, collect `python tracepair.py --version`, `python --version`, your operating system, the fixed warning code and a small **invented** example. Use the [bug report template](https://github.com/mnb-zxc-920/TracePair/issues/new?template=bug_report.md). Do not attach original logs, credentials or private screenshots. If you cannot create a reproducer, report the version and warning code first.
