"""Behavioral tests of projection, export privacy, and command-line effects."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tracepair.cli import main
from tracepair.compare import change, compare_runs
from tracepair.demo import demo_log
from tracepair.parser import parse_run
from tracepair.render import render_html, render_svg


class ReportsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = [self.root / f'{name}.jsonl' for name in ('A', 'B')]
        for path, name in zip(self.paths, ('A', 'B')):
            path.write_text(demo_log(name), encoding='utf-8')

    def pair(self):
        return [parse_run(path) for path in self.paths]

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def test_demo_has_exact_reproducible_totals_and_is_labeled(self):
        a, b = self.pair()
        self.assertEqual(a['tokens']['input_tokens'], 52000)
        self.assertEqual(b['tokens']['input_tokens'], 37000)
        self.assertEqual(a['tokens']['total_tokens'], 56000)
        self.assertEqual(b['tokens']['total_tokens'], 40500)
        self.assertEqual((a['tool_calls'], b['tool_calls']), (8, 6))
        data = compare_runs(a, b, synthetic=True)
        self.assertEqual(data['changes']['input_tokens'], {'absolute': -15000, 'percent': -28.8})
        self.assertIn('SYNTHETIC DEMO', render_html(data))
        self.assertIn('SYNTHETIC DEMO', render_svg(data))
        ET.fromstring(render_svg(data))

    def test_zero_and_unknown_have_different_delta_semantics(self):
        self.assertEqual(change(0, 50), {'absolute': 50, 'percent': None})
        self.assertEqual(change(0, 0), {'absolute': 0, 'percent': None})
        self.assertEqual(change(5, 0), {'absolute': -5, 'percent': -100.0})
        self.assertEqual(change(None, 0), {'absolute': None, 'percent': None})

    def test_projection_does_not_export_unexpected_parser_fields_or_fingerprints(self):
        a, b = self.pair()
        a['future_transcript_field'] = 'PRIVATE_TRANSCRIPT_SENTINEL'
        a['model_fingerprints'] = ['PRIVATE_MODEL_FINGERPRINT_SENTINEL']
        data = compare_runs(a, b)
        for text in (json.dumps(data), render_html(data), render_svg(data)):
            self.assertNotIn('PRIVATE_TRANSCRIPT_SENTINEL', text)
            self.assertNotIn('PRIVATE_MODEL_FINGERPRINT_SENTINEL', text)
            self.assertNotIn('synthetic-demo-model', text)
        self.assertEqual(data['model_relation'], 'different')

    def test_sentinel_content_does_not_reach_any_output(self):
        secret = 'PRIVATE_CANARY_93a7'
        # Place a distinct canary into fields that are deliberately excluded.
        events = [json.loads(line) for line in demo_log('A').splitlines()]
        for event in events:
            event['payload']['cwd'] = 'C:/PRIVATE_CANARY_93a7/project'
            event['payload']['text'] = '<script>PRIVATE_CANARY_93a7</script>'
            if event['type'] == 'turn_context':
                event['payload']['model'] = secret
            if event['type'] == 'response_item':
                event['payload'].update(name=secret, arguments=secret, call_id=secret + event['payload']['call_id'])
        self.paths[0].write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
        target = self.root / 'report'
        code, _, _ = self.invoke(['compare', *map(str, self.paths), '--out', str(target)])
        self.assertEqual(code, 0)
        for path in target.iterdir():
            self.assertNotIn(secret, path.read_text(encoding='utf-8'))
            self.assertNotIn(str(self.root), path.read_text(encoding='utf-8'))

    def test_cli_writes_exactly_three_files_and_preserves_inputs(self):
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in self.paths]
        target = self.root / 'result'
        code, out, err = self.invoke(['compare', *map(str, self.paths), '--out', str(target)])
        self.assertEqual((code, err), (0, ''))
        self.assertEqual({p.name for p in target.iterdir()}, {'report.html', 'summary.json', 'share.svg'})
        self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in self.paths])
        self.assertFalse(json.loads((target / 'summary.json').read_text())['synthetic'])
        self.assertIn('Reports written', out)

    def test_existing_output_is_not_overwritten(self):
        target = self.root / 'existing'
        target.mkdir()
        marker = target / 'report.html'
        marker.write_bytes(b'irreplaceable existing report')
        code, _, err = self.invoke(['demo', '--out', str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(marker.read_bytes(), b'irreplaceable existing report')
        self.assertEqual(len(list(target.iterdir())), 1)
        self.assertIn('already exists', err)

    def test_missing_input_error_does_not_expose_path(self):
        code, _, err = self.invoke(['compare', str(self.root/'PRIVATE_FILENAME_SENTINEL'), str(self.paths[1]), '--out', str(self.root/'out')])
        self.assertEqual(code, 2)
        self.assertNotIn('PRIVATE_FILENAME_SENTINEL', err)
        self.assertFalse((self.root/'out').exists())

    def test_generated_html_has_no_remote_assets_or_scripts(self):
        text = render_html(compare_runs(*self.pair()))
        self.assertNotIn('<script', text.lower())
        self.assertNotIn('src="https://', text.lower())
        self.assertNotIn('@import', text.lower())
        self.assertIn("default-src 'none'", text)


if __name__ == '__main__':
    unittest.main()
