"""Explicit local inputs, new output directories, and no network activity."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

from . import __version__
from .compare import compare_runs
from .demo import demo_log
from .parser import ParseError, parse_run
from .render import render_html, render_svg, delta_text


def _write_report(destination, data):
    # Render before creating anything; never replace a user's existing directory.
    files = {'report.html': render_html(data), 'summary.json': json.dumps(data, indent=2, ensure_ascii=True) + '\n', 'share.svg': render_svg(data)}
    try:
        destination.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ParseError('Output directory already exists. Choose a new --out directory.') from None
    except OSError:
        raise ParseError('Cannot create the output directory.') from None
    try:
        for name, content in files.items():
            with (destination / name).open('x', encoding='utf-8', newline='\n') as handle:
                handle.write(content)
    except OSError:
        raise ParseError('Could not finish writing the report. The new directory may contain partial output; choose another directory after checking it.') from None


def _parse_compare_run(path, start, end, label, window):
    try:
        return parse_run(path, start=start, end=end)
    except OSError:
        text = 'unreadable input'
    except ParseError as error:
        text = str(error)
    if text == 'unreadable input':
        raise ParseError(f'Cannot read {label}. Choose an existing readable Codex JSONL file, not a folder. Quote paths that contain spaces.') from None
    if text == 'invalid time window':
        raise ParseError(f'Invalid time window for {label}. {window} must be ISO 8601 with a timezone, and end must be later than start.') from None
    raise ParseError(f'Cannot parse {label}.') from None


def main(argv=None):
    parser = argparse.ArgumentParser(prog='tracepair', description='See what changed between two Codex JSONL runs. Locally.')
    parser.add_argument('--version', action='version', version=f'TracePair {__version__}')
    commands = parser.add_subparsers(dest='command', required=True)
    diff = commands.add_parser('compare', help='Compare two explicit Codex JSONL files')
    diff.add_argument('run_a', type=Path)
    diff.add_argument('run_b', type=Path)
    diff.add_argument('--a-start', help='Run A inclusive start, ISO 8601 with timezone')
    diff.add_argument('--a-end', help='Run A exclusive end, ISO 8601 with timezone')
    diff.add_argument('--b-start', help='Run B inclusive start, ISO 8601 with timezone')
    diff.add_argument('--b-end', help='Run B exclusive end, ISO 8601 with timezone')
    demo = commands.add_parser('demo', help='Generate a report from clearly labeled synthetic runs')
    for command in (diff, demo):
        command.add_argument('--out', type=Path, default=Path('tracepair-report'), help='New directory for report.html, summary.json and share.svg')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            with tempfile.TemporaryDirectory(prefix='tracepair-demo-') as temporary:
                paths = [Path(temporary) / f'{name}.jsonl' for name in ('A', 'B')]
                for path, name in zip(paths, ('A', 'B')):
                    path.write_text(demo_log(name), encoding='utf-8')
                a, b = (parse_run(path) for path in paths)
        else:
            a = _parse_compare_run(args.run_a, args.a_start, args.a_end, 'Run A', '--a-start/--a-end')
            b = _parse_compare_run(args.run_b, args.b_start, args.b_end, 'Run B', '--b-start/--b-end')
        data = compare_runs(a, b, synthetic=args.command == 'demo')
        _write_report(args.out, data)
    except (ParseError, OSError):
        error = sys.exc_info()[1]
        # Parser errors are fixed messages; native OS paths are deliberately omitted.
        message = str(error) if isinstance(error, ParseError) else 'Cannot read an input or write an output.'
        print(f'TracePair: {message}', file=sys.stderr)
        return 2
    print(f"Run B input: {delta_text(data['changes']['input_tokens'])}.")
    print('Reports written: report.html | summary.json | share.svg')
    print('Open report.html in your chosen output directory. Review aggregates before sharing.')
    if args.command == 'demo':
        print('SYNTHETIC DEMO: these made-up numbers are not a performance result.')
    if any(run['quality'] != 'observed' for run in data['runs'].values()):
        print('Accounting gaps detected. See the report notes.')
    return 0
