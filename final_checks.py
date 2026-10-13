"""Current pinned official checks plus exact reference counts; no synthetic host_metrics."""
import json
from pathlib import Path
import pyarrow.parquet as pq
from qfbench2_common.contracts import stable_output_binding, OrganizerFault
from qfbench2_track_simulation import batch, limits, telemetry
import checks


def current_contract(unit, out, card):
    snapshot = checks.snapshot(unit, out, card)
    if not all(x['status'] == 'PASS' for x in snapshot.values()):
        raise AssertionError('Supplemental schema/ledger checks failed')
    if batch.batch_meta(unit):
        entries = [(s['sub'], unit/'checks/reference_data'/s['sub'], out/s['sub'], s.get('n_events'))
                   for s in batch.load_subs(unit)]
    else:
        entries = [('single', unit, out, None)]
    rows = {}
    counts = {}
    for name, reference, candidate, declared in entries:
        actual = int(pq.ParquetFile(candidate/'trace.parquet').metadata.num_rows)
        expected = int(pq.ParquetFile(reference/'trace.parquet').metadata.num_rows)
        if actual != expected:
            raise AssertionError('All-tier exact reference event-count mismatch: '+name)
        if declared is not None and (type(declared) is not int or declared != expected):
            raise OrganizerFault('Organizer batch declaration/reference mismatch')
        if (reference/'events.json').exists():
            if json.loads((reference/'events.json').read_text())['n_events'] != expected:
                raise OrganizerFault('Organizer reference footer/sidecar mismatch')
        # Conservative generation/check: no card or missing declaration is not an omission permission.
        required = name != 'single' or card.get('scoring', {}).get('params', {}).get('requires_message_ledger') is not False
        if required and not (candidate/'message_trace.parquet').is_file():
            raise AssertionError('Required message ledger absent')
        if (candidate/'message_trace.parquet').exists() and snapshot[name]['message_semantics']['status'] != 'PASS':
            raise AssertionError('Present message ledger semantics failed')
        rows[(candidate/'trace.parquet').relative_to(out).as_posix()] = actual
        counts[name] = {'actual': actual, 'reference': expected, 'declared': declared,
                        'reference_sha256': checks.sha(reference/'trace.parquet')}
    telemetry.validate_repeat_sidecars(unit, out, rows)
    policy = limits.stable_repeat_policy_for(unit)
    binding = stable_output_binding(out, **policy)
    return {'status': 'PASS', 'sub_contracts': snapshot, 'exact_reference_counts': counts,
            'row_counts': rows, 'n_events': sum(rows.values()), 'stable_policy': policy,
            'stable_binding': binding, 'repeat_sidecars': 'PASS'}


def stable_equal(left, right):
    # Timing JSON is validated separately for every run, never frozen byte-for-byte.
    return left['stable_binding'] == right['stable_binding']
