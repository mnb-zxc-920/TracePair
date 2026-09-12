"""Self-contained HTML and SVG. No scripts, fonts, or assets fetched remotely."""
from html import escape

from .compare import CATEGORIES, WARNINGS

LABELS = {
    "input_tokens": "Input tokens", "cached_input_tokens": "Cached input",
    "uncached_input_tokens": "Uncached input", "output_tokens": "Output tokens",
    "reasoning_output_tokens": "Reasoning output", "total_tokens": "Total tokens",
}


def number(value):
    return "Unknown" if value is None else f"{value:,}"


def compact(value):
    if value is None:
        return "Unknown"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}m"
    if abs(value) >= 1000:
        return f"{value / 1000:.1f}k"
    return str(value)


def duration(value):
    if value is None:
        return "Unknown"
    minutes, seconds = divmod(round(value), 60)
    return f"{minutes}m {seconds:02}s" if minutes else f"{seconds}s"


def delta_text(change):
    absolute, percent = change["absolute"], change["percent"]
    if absolute is None:
        return "Not comparable"
    if absolute == 0:
        return "No change"
    direction = "more" if absolute > 0 else "fewer"
    if percent is None:
        return f"{abs(absolute):,} {direction} · zero baseline"
    return f"{abs(percent):g}% {direction}"


def _bars(run, maximum):
    tokens = run["tokens"]
    keys = ("uncached_input_tokens", "cached_input_tokens", "output_tokens")
    if any(tokens.get(key) is None for key in keys):
        return '<div class="bar unavailable">Breakdown unavailable</div>'
    if not maximum:
        return '<div class="bar unavailable">Observed zero tokens</div>'
    parts = []
    for key, cls in zip(keys, ("uncached", "cached", "output")):
        width = max(0, min(100, tokens[key] / maximum * 100))
        parts.append(f'<span class="{cls}" style="width:{width:.5f}%" title="{LABELS[key]}: {number(tokens[key])}"></span>')
    return '<div class="bar">' + ''.join(parts) + '</div>'


def render_html(data):
    a, b = data["runs"]["A"], data["runs"]["B"]
    badge = "SYNTHETIC DEMO" if data["synthetic"] else "LOCAL COMPARISON"
    cards = []
    for key in ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens"):
        change = data["changes"][key]
        cls = "down" if change["absolute"] is not None and change["absolute"] < 0 else "neutral"
        cards.append(f'''<article class="metric"><h3>{LABELS[key]}</h3>
<div class="pair"><span><i>A</i>{compact(a['tokens'][key])}</span><span><i>B</i>{compact(b['tokens'][key])}</span></div>
<p class="delta {cls}">{delta_text(change)}</p><small>{number(a['tokens'][key])} → {number(b['tokens'][key])}</small></article>''')
    maximum = max(a["tokens"]["total_tokens"] or 0, b["tokens"]["total_tokens"] or 0)
    chart = ''.join(f'''<div class="runrow"><div class="runhead"><b>Run {name}</b><span>{number(run['tokens']['total_tokens'])} tokens</span></div>{_bars(run, maximum)}</div>'''
                    for name, run in (("A", a), ("B", b)))
    tools = ''.join(f'<tr><th scope="row">{key.title()}</th><td>{a["tool_categories"][key]}</td><td>{b["tool_categories"][key]}</td></tr>' for key in CATEGORIES)
    accounting = []
    for name, run in (("A", a), ("B", b)):
        notes = ''.join(f'<li>{escape(WARNINGS[code])}</li>' for code in run['warnings'])
        if not notes:
            notes = '<li>No accounting warnings were detected in the supplied log.</li>'
        coverage = {"from_first_usage": "First usage matches the opening cumulative snapshot.",
                    "between_snapshots": "Usage after an excluded opening snapshot.",
                    "unavailable": "Accounting coverage is unavailable."}.get(run['coverage'], "Unknown coverage.")
        accounting.append(f'''<article><div class="runhead"><h3>Run {name}</h3><span class="status {escape(run['quality'])}">{escape(run['quality'])}</span></div>
<p>{coverage}</p><ul>{notes}</ul><div class="smallfacts"><span>{run['token_snapshots']} native snapshots</span><span>{run['duplicate_snapshots']} repeated snapshots ignored</span><span>{run['duplicate_tool_calls']} duplicate call IDs ignored</span></div></article>''')
    comparison_notes = ''.join(f'<li>{escape(note)}</li>' for note in data['comparison_notes'])
    if not comparison_notes:
        comparison_notes = '<li>The recorded metadata raises no additional comparison warnings.</li>'
    demo_note = '<p class="demo-note">Made-up runs demonstrate the interface. These numbers are not a performance result.</p>' if data['synthetic'] else ''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>TracePair — Run comparison</title><style>
:root{{--paper:#f5f3ec;--ink:#192d31;--muted:#657173;--line:#d9ded7;--teal:#197869;--mint:#a2d7c4;--amber:#efb668;--mono:Consolas,'Liberation Mono',monospace}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 'Segoe UI',Arial,sans-serif}}main{{max-width:1180px;margin:auto;padding:32px 36px 60px}}
header{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:23px}}.brand{{font-weight:800;font-size:25px;letter-spacing:-1px;display:flex;align-items:center;gap:10px}}.mark{{display:flex;gap:4px;align-items:center}}.mark b{{display:block;background:var(--teal);width:9px;height:24px;border-radius:2px}}.mark b:nth-child(2){{height:15px;background:var(--ink)}}.tag{{font:11px var(--mono);letter-spacing:1.8px;border:1px solid #c8d4cc;border-radius:30px;padding:8px 13px}}
.hero{{display:grid;grid-template-columns:1.3fr 1fr;gap:50px;align-items:end;padding:48px 0 32px}}.eyebrow{{font:11px var(--mono);letter-spacing:2px;color:var(--teal);margin:0 0 14px}}h1{{font-size:clamp(36px,4.5vw,59px);line-height:1.05;font-weight:750;letter-spacing:-2.8px;margin:0}}h1 em{{font-style:normal;color:var(--teal)}}.intro{{color:var(--muted);margin:0;max-width:365px;font-size:16px}}.demo-note{{background:#fff0d8;border-left:3px solid var(--amber);font-size:13px;padding:10px 14px;margin:0 0 24px}}
.metrics{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}}.metric{{background:#fffefa;border:1px solid var(--line);border-radius:12px;padding:20px}}h3{{margin:0;font-size:14px;font-weight:650}}.metric h3{{color:var(--muted)}}.pair{{display:flex;gap:20px;margin:18px 0 13px;flex-wrap:wrap}}.pair span{{font:27px var(--mono);letter-spacing:-1px}}.pair i{{display:block;font:10px var(--mono);font-style:normal;color:var(--muted);margin-bottom:5px;letter-spacing:0}}.delta{{font-weight:700;font-size:13px;margin:0 0 6px}}.down{{color:var(--teal)}}.neutral{{color:#825416}}small{{font:10px var(--mono);color:var(--muted)}}
.panels{{display:grid;grid-template-columns:1.3fr 1fr;gap:20px;margin-top:22px}}.panel{{border:1px solid var(--line);border-radius:12px;padding:26px;background:#ffffff66}}h2{{font-size:19px;letter-spacing:-.4px;margin:0 0 5px}}.sub{{font-size:12px;color:var(--muted);margin:0 0 24px}}.runrow{{margin:24px 0}}.runhead{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;font-size:12px}}.runhead span{{font-family:var(--mono)}}.bar{{height:28px;display:flex;background:#e7ebe4;border-radius:4px;overflow:hidden}}.bar span{{height:100%;min-width:0}}.uncached{{background:var(--teal)}}.cached{{background:var(--mint)}}.output{{background:var(--amber)}}.unavailable{{font-size:11px;color:var(--muted);align-items:center;padding:0 10px}}.legend{{display:flex;flex-wrap:wrap;gap:14px;font-size:11px;margin:26px 0 16px}}.legend i{{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}}.footnote{{font-size:11px;color:var(--muted);margin:0}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:9px 4px;border-bottom:1px solid #e2e6df;text-align:right}}th:first-child{{text-align:left;font-weight:500}}thead{{color:var(--muted);font:10px var(--mono)}}tfoot{{font-weight:700}}.inlinefacts{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding:27px 0;border-bottom:1px solid var(--line)}}.inlinefacts b{{display:block;font:16px var(--mono);margin-top:6px}}.inlinefacts span{{font-size:11px;color:var(--muted)}}
.interpretation{{background:var(--ink);color:#f3f5ed;border-radius:12px;padding:27px 30px;margin-top:26px;display:grid;grid-template-columns:1fr 1.3fr;gap:35px}}.interpretation h2{{font-size:21px;line-height:1.3}}.interpretation p,.interpretation li{{font-size:12px;color:#d2dfda}}.interpretation ul{{margin:0;padding-left:17px}}.interpretation p{{margin:8px 0 0}}details{{margin-top:25px}}summary{{font-size:15px;font-weight:700;cursor:pointer;padding:8px 0}}summary:focus-visible{{outline:2px solid var(--teal);outline-offset:3px}}.accounting{{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:15px}}.accounting article{{border-top:1px solid var(--line);padding-top:18px}}.accounting p,.accounting li{{font-size:12px;color:var(--muted)}}.accounting ul{{padding-left:17px}}.status{{padding:4px 8px;border:1px solid #bdcfc4;border-radius:4px;font-size:10px}}.status.unavailable,.status.partial{{color:#875714;border-color:#dbc395;background:#fff1d8}}.smallfacts{{display:flex;gap:8px;flex-direction:column;font:10px var(--mono);color:var(--muted)}}footer{{display:flex;justify-content:space-between;gap:24px;border-top:1px solid var(--line);margin-top:35px;padding-top:20px;font-size:10px;color:var(--muted)}}footer p{{max-width:780px;margin:0}}footer a{{color:var(--teal);white-space:nowrap}}
@media(max-width:800px){{main{{padding:22px 20px 40px}}.hero{{grid-template-columns:1fr;gap:22px;padding-top:32px}}.intro{{max-width:100%}}.metrics{{grid-template-columns:repeat(2,1fr)}}.panels,.interpretation{{grid-template-columns:1fr;gap:16px}}.accounting{{grid-template-columns:1fr}}h1{{letter-spacing:-1.6px}}.inlinefacts{{gap:10px}}.inlinefacts b{{font-size:13px}}footer{{flex-direction:column}}}}
@media(max-width:420px){{.metric{{padding:15px}}.pair{{gap:12px}}.pair span{{font-size:22px}}.tag{{font-size:8px;padding:6px 9px}}}}
@media print{{body{{background:white}}main{{padding:0}}details{{display:block}}.metric,.panel,.interpretation{{break-inside:avoid}}.interpretation{{background:#e7eeea;color:var(--ink)}}.interpretation p,.interpretation li{{color:var(--ink)}}}}
</style></head><body><main>
<header><div class="brand"><span class="mark" aria-hidden="true"><b></b><b></b></span>TracePair</div><span class="tag">{badge}</span></header>
<section class="hero"><div><p class="eyebrow">A / B · CODEX RUN COMPARISON</p><h1>Two runs.<br><em>See what changed.</em></h1></div><p class="intro">Native counters. Tool activity. Accounting gaps.<br>A local view of the differences, with the context you need to read them.</p></section>
{demo_note}<section class="metrics" aria-label="Token comparison">{''.join(cards)}</section>
<div class="panels"><section class="panel"><h2>Where the tokens went</h2><p class="sub">Same scale · observed cumulative usage</p>{chart}<div class="legend"><span><i class="uncached"></i>Uncached input</span><span><i class="cached"></i>Cached input</span><span><i class="output"></i>Output</span></div><p class="footnote">Cached input is part of input. Reasoning is part of output.<br>Neither is added twice. Token counts are not a bill.</p></section>
<section class="panel"><h2>Tool activity</h2><p class="sub">Recorded calls · grouped into fixed categories</p><table><thead><tr><th>Category</th><th>Run A</th><th>Run B</th></tr></thead><tbody>{tools}</tbody><tfoot><tr><th>Total observed</th><td>{a['tool_calls']}</td><td>{b['tool_calls']}</td></tr></tfoot></table><p class="footnote" style="margin-top:14px">Calls inside an orchestration wrapper are not expanded. Tool names and arguments stay out of this report.</p></section></div>
<section class="inlinefacts" aria-label="Additional metadata"><div><span>Recorded span · A / B</span><b>{duration(a['elapsed_seconds'])} / {duration(b['elapsed_seconds'])}</b></div><div><span>Reasoning output · A / B</span><b>{compact(a['tokens']['reasoning_output_tokens'])} / {compact(b['tokens']['reasoning_output_tokens'])}</b></div><div><span>Recorded model sets</span><b>{escape(data['model_relation'].title())}</b></div></section>
<section class="interpretation"><div><h2>A difference is a starting point.</h2><p>{escape(data['interpretation'])}</p></div><ul>{comparison_notes}</ul></section>
<details open><summary>Accounting notes</summary><div class="accounting">{''.join(accounting)}</div></details>
<footer><p>{escape(data['privacy'])}<br>TracePair v{escape(data['version'])} · Recorded span includes idle time. Outcome quality requires your own review.</p><a href="https://github.com/mnb-zxc-920/TracePair" rel="noreferrer">View source ↗</a></footer>
</main></body></html>'''


def render_svg(data):
    """A compact share card with fixed labels; contains no transcript-derived strings."""
    a, b = data['runs']['A'], data['runs']['B']
    badge = 'SYNTHETIC DEMO · MADE-UP NUMBERS' if data['synthetic'] else 'OBSERVED LOG COUNTERS'
    boxes = []
    for index, key in enumerate(('input_tokens', 'uncached_input_tokens', 'output_tokens')):
        x = 54 + index * 367
        boxes.append(f'''<g transform="translate({x},270)"><rect width="347" height="193" rx="14" fill="#fffefa" stroke="#d9ded7"/>
<text x="22" y="36" font-size="16" fill="#657173">{LABELS[key]}</text><text x="22" y="66" font-size="12" fill="#657173">RUN A</text><text x="185" y="66" font-size="12" fill="#657173">RUN B</text>
<text x="22" y="110" font-size="34" font-family="Consolas,monospace">{compact(a['tokens'][key])}</text><text x="185" y="110" font-size="34" font-family="Consolas,monospace">{compact(b['tokens'][key])}</text>
<text x="22" y="157" font-size="16" fill="#197869">{escape(delta_text(data['changes'][key]))}</text></g>''')
    notes = 'Read the full report for accounting gaps and comparison limits.'
    if a['quality'] != 'observed' or b['quality'] != 'observed':
        notes = 'DATA GAPS PRESENT · Read the full report before interpreting changes.'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-labelledby="title desc">
<title id="title">TracePair: two Codex runs compared</title><desc id="desc">{escape(badge)}. Token differences do not prove savings or equal output quality.</desc>
<rect width="1200" height="630" fill="#f5f3ec"/><g fill="#192d31" font-family="Segoe UI,Arial,sans-serif"><rect x="54" y="38" width="10" height="27" rx="2" fill="#197869"/><rect x="69" y="49" width="10" height="16" rx="2"/>
<text x="94" y="63" font-size="29" font-weight="700">TracePair</text><text x="1145" y="58" text-anchor="end" font-size="12" letter-spacing="1.8">{badge}</text><path d="M54 91H1145" stroke="#d9ded7"/>
<text x="54" y="168" font-size="49" font-weight="700" letter-spacing="-1.5">Two runs. See what changed.</text><text x="54" y="219" font-size="20" fill="#657173">A local comparison of native Codex logs. No API key. No hooks.</text>
{''.join(boxes)}<text x="54" y="507" font-size="15" fill="#657173">{notes}</text><text x="54" y="540" font-size="14">Differences do not prove savings, productivity, or equal output quality.</text><path d="M54 568H1145" stroke="#d9ded7"/>
<text x="54" y="601" font-size="13" fill="#197869">github.com/mnb-zxc-920/TracePair</text><text x="1145" y="601" text-anchor="end" font-size="13" fill="#657173">{a['tool_calls']} → {b['tool_calls']} observed tool calls · v{escape(data['version'])}</text></g></svg>'''
