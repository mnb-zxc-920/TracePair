"""CLI recovery behavior using only the public synthetic demo generator."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tracepair.cli import main
from tracepair.demo import demo_log


class CliErrorsTest(unittest.TestCase):
    PATH_CANARY = 'SYNTHETIC_PRIVATE_PATH_83A2'
    CONTENT_CANARY = 'SYNTHETIC_PRIVATE_CONTENT_83A2'
    OS_CANARY = 'SYNTHETIC_NATIVE_ERROR_83A2'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tracepair-cli-errors-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / ('synthetic files ' + self.PATH_CANARY)
        self.root.mkdir()
        self.paths = [self.root / f'Run {name}.jsonl' for name in ('A', 'B')]
        for path, name in zip(self.paths, ('A', 'B')):
            self.write_demo(path, name)
        self.target = self.root / 'uncreated parent' / 'report with spaces'

    def write_demo(self, path, name):
        # The canary is invented; it replaces an ignored synthetic tool argument.
        path.write_text(demo_log(name).replace('synthetic only', self.CONTENT_CANARY),
                        encoding='utf-8')

    def snapshot(self):
        """Check bytes, file metadata, and directory membership after rejection."""
        state = {}
        for path in self.root.rglob('*'):
            if path.is_dir():
                state[path.relative_to(self.root).as_posix()] = ('directory',)
            else:
                stat = path.stat()
                state[path.relative_to(self.root).as_posix()] = (
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    stat.st_size, stat.st_mtime_ns, stat.st_mode)
        return state

    def invoke(self, paths=None, bounds=(), target=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ['compare', *map(str, self.paths if paths is None else paths),
                *bounds, '--out', str(self.target if target is None else target)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def assert_private(self, text, values=()):
        for value in (self.PATH_CANARY, self.CONTENT_CANARY, self.OS_CANARY,
                      str(self.root), *(str(path) for path in self.paths),
                      str(self.target), *values):
            self.assertNotIn(value, text)
            if '/' in value or '\\' in value:
                self.assertNotIn(Path(value).name, text)
        # Also catch a diagnostic that echoes only a bait suffix or basename.
        self.assertNotIn('CANARY', text)
        self.assertNotIn('Traceback (most recent call last)', text)
        self.assertNotRegex(text, r'\[(?:Errno|WinError)\s+\d+')

    def assert_rejected_without_effects(self, result, before, values=()):
        code, stdout, stderr = result
        self.assertEqual(code, 2)
        self.assertEqual(stdout, '')
        self.assertTrue(stderr.strip())
        self.assert_private(stdout + stderr, values)
        self.assertEqual(self.snapshot(), before)
        # This also detects creation of --out's missing parent directories.
        self.assertFalse(self.target.parent.exists())

    def assert_read_recovery(self, stderr, run):
        # Check the promised information, without fixing sentences or punctuation.
        self.assertRegex(stderr, rf'(?i)\brun\s+{run}\b')
        for meaning in (r'\b(?:check|verify|ensure|confirm|use|choose)\b',
                        r'\bexist(?:s|ing|ence)?\b|\bfound\b',
                        r'\breadable\b|\bread\s+permissions?\b|\bpermissions?\b',
                        r'\bfile\b', r'\bdirector(?:y|ies)\b|\bfolders?\b',
                        r'\bquot(?:e|es|ed|ing|ation)\b', r'\bspaces?\b|\bwhitespace\b'):
            self.assertRegex(stderr, '(?i)' + meaning)

    def assert_window_recovery(self, stderr, run):
        prefix = run.lower()
        self.assertIn(f'--{prefix}-start', stderr)
        self.assertIn(f'--{prefix}-end', stderr)
        self.assertRegex(stderr, r'(?i)\bISO[ -]?8601\b')
        self.assertRegex(stderr, r'(?i)\btime[ -]?zone\b|\bUTC\s+offset\b')
        self.assertRegex(stderr, r'(?is)(?:\bend\b.{0,90}\b(?:later|after|greater)\b'
                         r'.{0,90}\bstart\b|\bstart\b.{0,90}\b(?:before|earlier|less)\b'
                         r'.{0,90}\bend\b)')

    def test_missing_run_a_has_actionable_private_error(self):
        missing = self.root / 'MISSING_A_CANARY file.jsonl'
        before = self.snapshot()
        result = self.invoke(paths=[missing, self.paths[1]])
        self.assert_rejected_without_effects(result, before, [str(missing)])
        self.assert_read_recovery(result[2], 'A')

    def test_missing_run_b_has_actionable_private_error(self):
        missing = self.root / 'MISSING_B_CANARY file.jsonl'
        before = self.snapshot()
        result = self.invoke(paths=[self.paths[0], missing])
        self.assert_rejected_without_effects(result, before, [str(missing)])
        self.assert_read_recovery(result[2], 'B')

    def test_directory_inputs_are_rejected_for_both_runs(self):
        directory = self.root / 'DIRECTORY_CANARY with spaces'
        directory.mkdir()
        for index, run in enumerate(('A', 'B')):
            with self.subTest(run=run):
                paths = self.paths.copy()
                paths[index] = directory
                before = self.snapshot()
                result = self.invoke(paths=paths)
                self.assert_rejected_without_effects(result, before, [str(directory)])
                self.assert_read_recovery(result[2], run)

    def test_unreadable_inputs_hide_native_errors_for_both_runs(self):
        original_open = Path.open
        for index, run in enumerate(('A', 'B')):
            with self.subTest(run=run):
                denied_path = self.paths[index]

                def deny_one_file(path, *args, **kwargs):
                    if path == denied_path:
                        raise PermissionError(13, self.OS_CANARY, str(path))
                    return original_open(path, *args, **kwargs)

                before = self.snapshot()
                # Permission bits are unreliable under Windows/admin accounts.
                # Inject the OS failure at file open, leaving CLI/parser behavior real.
                with patch.object(Path, 'open', new=deny_one_file):
                    result = self.invoke()
                self.assert_rejected_without_effects(result, before)
                self.assert_read_recovery(result[2], run)

    def test_run_a_invalid_bounds_name_options(self):
        cases = [('--a-start', '2097-12-30T04:05:06'),
                 ('--a-end', '2097-12-30T04:05:06+PRIVATE_TZ_A_CANARY')]
        for option, value in cases:
            with self.subTest(option=option):
                before = self.snapshot()
                result = self.invoke(bounds=[option, value])
                self.assert_rejected_without_effects(result, before, [value])
                self.assert_window_recovery(result[2], 'A')

    def test_run_b_invalid_bounds_name_options(self):
        cases = [('--b-start', '2097-12-30T04:05:06+PRIVATE_TZ_B_CANARY'),
                 ('--b-end', '2097-12-30T04:05:06')]
        for option, value in cases:
            with self.subTest(option=option):
                before = self.snapshot()
                result = self.invoke(bounds=[option, value])
                self.assert_rejected_without_effects(result, before, [value])
                self.assert_window_recovery(result[2], 'B')

    def test_reversed_and_equal_windows_name_run_and_pair(self):
        start = '2097-12-30T04:05:06+03:00'
        for run in ('A', 'B'):
            for end in ('2097-12-30T03:05:06+03:00', start):
                with self.subTest(run=run, equal=(start == end)):
                    before = self.snapshot()
                    prefix = run.lower()
                    result = self.invoke(bounds=[f'--{prefix}-start', start,
                                                 f'--{prefix}-end', end])
                    self.assert_rejected_without_effects(result, before, [start, end])
                    self.assert_window_recovery(result[2], run)

    def test_validation_failure_preserves_existing_output_and_inputs(self):
        existing = self.root / 'EXISTING_OUTPUT_CANARY'
        existing.mkdir()
        (existing / 'report.html').write_bytes(b'previous synthetic report')
        (existing / 'keep.bin').write_bytes(b'\x00\xff synthetic preserved bytes')
        missing = self.root / 'MISSING_EXISTING_CANARY.jsonl'
        cases = [([self.paths[0], missing], (), [str(missing)]),
                 (self.paths, ['--a-start', 'PRIVATE_BOUND_CANARY'],
                  ['PRIVATE_BOUND_CANARY'])]
        for paths, bounds, private in cases:
            with self.subTest(bounds=bool(bounds)):
                before = self.snapshot()
                result = self.invoke(paths=paths, bounds=bounds, target=existing)
                self.assert_rejected_without_effects(result, before, [str(existing), *private])

    def assert_successful_recovery(self, result, before):
        code, stdout, stderr = result
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(stdout,
                         'Run B input: 28.8% fewer.\n'
                         'Reports written: report.html | summary.json | share.svg\n'
                         'Open report.html in your chosen output directory. '
                         'Review aggregates before sharing.\n')
        self.assertEqual({path.name for path in self.target.iterdir()},
                         {'report.html', 'summary.json', 'share.svg'})
        after = self.snapshot()
        self.assertEqual({name: after[name] for name in before}, before)
        data = json.loads((self.target / 'summary.json').read_text(encoding='utf-8'))
        self.assertFalse(data['synthetic'])
        expected = {'A': (52000, 36000, 4000, 2500, 56000, 8),
                    'B': (37000, 24000, 3500, 2200, 40500, 6)}
        counters = ('input_tokens', 'cached_input_tokens', 'output_tokens',
                    'reasoning_output_tokens', 'total_tokens')
        for run, values in expected.items():
            self.assertEqual(tuple(data['runs'][run]['tokens'][key] for key in counters),
                             values[:5])
            self.assertEqual(data['runs'][run]['tool_calls'], values[5])
        self.assertEqual(data['changes']['input_tokens'],
                         {'absolute': -15000, 'percent': -28.8})
        self.assert_private(stdout)
        for path in self.target.iterdir():
            self.assert_private(path.read_text(encoding='utf-8'))

    def test_retry_after_fixing_missing_path_with_spaces_succeeds(self):
        repaired = self.root / 'repaired B path with spaces.jsonl'
        before = self.snapshot()
        result = self.invoke(paths=[self.paths[0], repaired])
        self.assert_rejected_without_effects(result, before, [str(repaired)])
        self.write_demo(repaired, 'B')
        before = self.snapshot()
        # An argv element models a correctly quoted path received from the shell.
        result = self.invoke(paths=[self.paths[0], repaired])
        self.assert_successful_recovery(result, before)

    def test_retry_after_fixing_window_succeeds(self):
        bad_bound = 'PRIVATE_WINDOW_RECOVERY_CANARY'
        before = self.snapshot()
        result = self.invoke(bounds=['--b-end', bad_bound])
        self.assert_rejected_without_effects(result, before, [bad_bound])
        # Equivalent zoned upper bounds lie after every demo event, preserving
        # the full-run totals and the existing successful CLI output.
        bounds = ['--a-end', '2025-12-31T16:04:00-08:00',
                  '--b-end', '2026-01-01T00:04:00Z']
        result = self.invoke(bounds=bounds)
        self.assert_successful_recovery(result, before)


if __name__ == '__main__':
    unittest.main()
