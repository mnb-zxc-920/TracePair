"""Made-up Codex-shaped events, generated locally for a reproducible demo."""
import datetime as dt
import json


def demo_log(variant):
    """No real transcript, identifier, model, or performance claim is used."""
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    events = []
    def add(seconds, kind, payload):
        events.append({"timestamp": (start + dt.timedelta(seconds=seconds)).isoformat(), "type": kind, "payload": payload})
    add(0, 'session_meta', {'id': f'synthetic-{variant}'})
    add(0, 'turn_context', {'model': 'synthetic-demo-model'})
    inputs = (40000, 12000) if variant == 'A' else (30000, 7000)
    cached = (28000, 8000) if variant == 'A' else (20000, 4000)
    outputs = (2400, 1600) if variant == 'A' else (2100, 1400)
    reasoning = (1600, 900) if variant == 'A' else (1400, 800)
    total = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0, 'reasoning_output_tokens': 0, 'total_tokens': 0}
    for index in range(2):
        last = dict(zip(total, (inputs[index], cached[index], outputs[index], reasoning[index], inputs[index] + outputs[index])))
        total = {key: total[key] + last[key] for key in total}
        payload = {'type': 'token_count', 'info': {'total_token_usage': total, 'last_token_usage': last}}
        add(30 + index * (150 if variant == 'A' else 110), 'event_msg', payload)
        if index == 0:
            add(31, 'event_msg', payload)  # A quota refresh repeats the counters.
        names = ('exec_command', 'exec_command', 'apply_patch', 'exec') if variant == 'A' else ('exec_command', 'apply_patch', 'exec')
        for j, name in enumerate(names):
            add(32 + index * (150 if variant == 'A' else 110) + j, 'response_item',
                {'type': 'function_call', 'name': name, 'call_id': f'demo-{index}-{j}', 'arguments': '{"example":"synthetic only"}'})
    return ''.join(json.dumps(event, separators=(',', ':')) + '\n' for event in events)
