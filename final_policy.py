"""Pure Final-style scheduling/statistics controls; no container or scoring calls."""
import datetime
import math
import re
import statistics


def schedule(plan, fallback=False):
    blocks = plan['conditional_F_blocks'] if fallback else plan['blocks']
    rows = []
    for block_index, (unit, version) in enumerate(blocks, 1):
        for repeat in range(5):
            rows.append({'unit': unit, 'version': version, 'block': block_index,
                         'repeat': repeat, 'stage': 'warmup' if repeat == 0 else 'formal',
                         'scope': 'conditional_F' if fallback else 'initial_60',
                         'block_order': 'I_then_conditional_F' if fallback else ''.join(v for u, v in plan['blocks'] if u == unit)})
    assert len(rows) == (20 if fallback else 60)
    assert plan['maximum_attempts'] == 80
    return rows


def timestamp_ns(value):
    # Docker RFC3339Nano: preserve all nine digits rather than truncating to micros.
    if type(value) is not str:
        raise ValueError('Docker timestamp must be a string')
    match = re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)', value)
    if not match or value.startswith('0001-'):
        raise ValueError('Invalid/unstarted Docker timestamp: ' + value)
    moment = datetime.datetime.fromisoformat(match[1] + ('+00:00' if match[3] == 'Z' else match[3]))
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    delta = moment - epoch
    whole = delta.days * 86400 + delta.seconds
    return whole * 1000000000 + int((match[2] or '').ljust(9, '0'))


def daemon_seconds(state):
    if state.get('Running') is not False or state.get('Status') != 'exited':
        raise ValueError('Container did not reach a completed exit')
    value = (timestamp_ns(state['FinishedAt']) - timestamp_ns(state['StartedAt'])) / 1e9
    if not math.isfinite(value) or not 0 < value <= 300:
        raise ValueError('Invalid or over-300-second daemon interval')
    return value


def no_volumes(config):
    if type(config) is not dict:
        raise AssertionError('Config must be an object')
    if 'Volumes' not in config or config['Volumes'] is None:
        return True
    if type(config['Volumes']) is dict and not config['Volumes']:
        return True
    raise AssertionError('Inherited or explicit Docker VOLUME is forbidden')


def block_summary(records):
    if len(records) != 5 or [r['repeat'] for r in records] != list(range(5)):
        raise AssertionError('Exactly one successful consecutive five-run block is required')
    if not all(r['state'] == 'PASS' for r in records):
        raise AssertionError('Warmup and all four measurements must pass')
    if len({(r['unit'], r['version'], r['n_events']) for r in records}) != 1:
        raise AssertionError('Block identity or event count changed')
    result = {'unit': records[0]['unit'], 'version': records[0]['version'],
              'n_events': records[0]['n_events'], 'indices': [r['index'] for r in records],
              'warmup_index': records[0]['index'], 'measured_indices': [r['index'] for r in records[1:]],
              'block_order': records[0]['block_order']}
    for metric in ('daemon', 'self', 'host'):
        values = [r[metric + '_wall_sec'] for r in records[1:]]
        if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in values):
            raise AssertionError('Invalid elapsed time')
        result[metric + '_median_sec'] = statistics.median(values)
        result[metric + '_median_EPS'] = statistics.median(result['n_events'] / x for x in values)
    return result


def comparisons(summaries):
    rows = []
    for unit in sorted({s['unit'] for s in summaries}):
        versions = {s['version']: s for s in summaries if s['unit'] == unit}
        if set(versions) != {'F', 'I'}:
            continue
        f, i = versions['F'], versions['I']
        if f['n_events'] != i['n_events']:
            raise AssertionError('Cross-candidate event counts differ')
        row = {'unit': unit, 'block_order': f['block_order'] if f['block_order']=='I_then_conditional_F' else i['block_order'], 'F_indices': f['indices'], 'I_indices': i['indices']}
        for metric in ('daemon', 'self', 'host'):
            ft, it = f[metric + '_median_sec'], i[metric + '_median_sec']
            row.update({metric + '_F_median_sec': ft, metric + '_I_median_sec': it,
                        metric + '_delta_sec': it-ft, metric + '_time_change_pct': (it/ft-1)*100,
                        metric + '_median_rate_ratio': i[metric + '_median_EPS']/f[metric + '_median_EPS']})
        row['material_daemon_regression'] = row['daemon_time_change_pct'] > 5 and row['daemon_delta_sec'] > .05
        rows.append(row)
    return rows
