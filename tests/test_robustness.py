"""Regression cases discovered during integration and independent review."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tracepair.parser import parse_run, MAX_LINE


def usage(i=100, c=40, o=20, r=10):
    return dict(input_tokens=i, cached_input_tokens=c, output_tokens=o,
                reasoning_output_tokens=r, total_tokens=i+o)


def snap(second, total, last=None):
    return {'timestamp':f'2026-01-01T00:00:{second:02d}Z', 'type':'event_msg',
            'payload':{'type':'token_count','info':{'total_token_usage':total,'last_token_usage':last}}}


class RobustnessTest(unittest.TestCase):
    def read(self, events, prefix=b'', **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'synthetic.jsonl'
            p.write_bytes(prefix + ''.join(json.dumps(e)+'\n' for e in events).encode('utf-8'))
            return parse_run(p, **kwargs)

    def test_delta_components_must_fit_within_delta_input_and_output(self):
        for changed in (usage(110,60,22,11), usage(110,45,22,15), usage(100,50,20,10)):
            with self.subTest(changed=changed):
                r = self.read([snap(0, usage()), snap(1, changed)])
                self.assertEqual(r['quality'],'unavailable')
                self.assertIn('INVALID_COUNTER',r['warnings'])
                self.assertTrue(all(v is None for v in r['tokens'].values()))

    def test_missing_optional_does_not_hide_a_reset(self):
        first = usage(100,80,20,10)
        missing = usage(110,80,22,11)
        del missing['cached_input_tokens']
        r = self.read([snap(0,first,first),snap(1,missing),snap(2,usage(120,70,25,12))])
        self.assertIn('COUNTER_RESET',r['warnings'])
        self.assertEqual(r['quality'],'unavailable')

    def test_unknown_unhashable_types_are_ignored_and_surrogates_are_opaque(self):
        events = [{'type':'response_item','payload':{'type':kind}} for kind in ([],{},False,1)]
        events += [{'timestamp':'2026-01-01T00:00:00Z','type':'turn_context','payload':{'model':'private\ud800'}},
                   {'timestamp':'2026-01-01T00:00:00Z','type':'response_item','payload':{'type':'function_call','call_id':'private\ud800','name':'private\ud800'}},
                   snap(1, usage(), usage())]
        r = self.read(events)
        self.assertEqual(r['tokens']['total_tokens'],120)
        self.assertNotIn('private',json.dumps(r))
        self.assertEqual(r['tool_calls'],1)

    def test_invalid_total_container_does_not_disappear_silently(self):
        for malformed in ([], None, 123, 'private'):
            r = self.read([snap(0,usage(),usage()),snap(1,malformed),snap(2,usage(150,60,30,15))])
            self.assertIn('INVALID_COUNTER',r['warnings'])
            self.assertIsNone(r['tokens']['total_tokens'])

    def test_bom_oversized_first_line_does_not_hide_following_usage(self):
        prefix = b'\xef\xbb\xbf' + b'{"text":"' + b'x' * MAX_LINE + b'"}\n'
        r = self.read([snap(1,usage(),usage())], prefix=prefix)
        self.assertEqual(r['malformed_lines'],1)
        self.assertEqual(r['tokens']['total_tokens'],120)

    def test_window_does_not_report_duplicates_from_outside_it(self):
        def tool(t, cid):
            return {'timestamp':f'2026-01-01T00:00:{t:02d}Z','type':'response_item','payload':{'type':'function_call','name':'bash','call_id':cid}}
        r = self.read([tool(0,'a'),tool(1,'a'),tool(10,'b'),tool(11,'b'),tool(20,'c'),tool(21,'c')],
                      start='2026-01-01T00:00:05Z',end='2026-01-01T00:00:15Z')
        self.assertEqual(r['tool_calls'],1)
        self.assertEqual(r['duplicate_tool_calls'],1)

    def test_future_out_of_order_records_do_not_invalidate_an_ended_window(self):
        r = self.read([snap(0,usage()),snap(10,usage(110,45,22,11)),
                       snap(50,usage(150,50,30,15)),snap(40,usage(140,50,30,15))],
                      start='2026-01-01T00:00:05Z',end='2026-01-01T00:00:20Z')
        self.assertEqual(r['tokens']['total_tokens'],12)
        self.assertNotIn('OUT_OF_ORDER',r['warnings'])

    def test_window_uses_nearest_prestart_snapshot_even_if_older_prefix_is_unordered(self):
        r = self.read([snap(3,usage(110,45,22,11)),snap(0,usage()),snap(10,usage(120,50,24,12))],
                      start='2026-01-01T00:00:05Z',end='2026-01-01T00:00:20Z')
        self.assertEqual(r['tokens']['total_tokens'],12)
        self.assertNotIn('OUT_OF_ORDER',r['warnings'])

    def test_new_prestart_baseline_after_selected_data_is_not_silently_applied(self):
        r = self.read([snap(0,usage()),snap(10,usage(120,50,24,12)),snap(3,usage(110,45,22,11))],
                      start='2026-01-01T00:00:05Z',end='2026-01-01T00:00:20Z')
        self.assertEqual(r['quality'],'unavailable')
        self.assertIn('OUT_OF_ORDER',r['warnings'])


if __name__ == '__main__':
    unittest.main()
