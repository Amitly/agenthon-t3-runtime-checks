"""Reviewed supplemental I/O checks; official scoring is imported unchanged."""
from dataclasses import asdict
from enum import Enum
from pathlib import Path
import hashlib,json,math
import jsonschema,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
import qfbench2_common
from qfbench2_track_simulation import batch,scoring,semantics
STABLE_FIELDS = ("scenario_id", "seed", "n_events", "trace_sha256")
TRACE_TYPES = {"t_ns": pa.int64(), "agent_id": pa.int32(), "msg_type": pa.string(),
               "side": pa.string(), "price": pa.int64(), "size": pa.int64(), "order_id": pa.int64()}
EVENT_SCHEMA = json.loads((Path(qfbench2_common.__file__).parent / "schemas/sim_scenario.schema.json").read_text())["properties"]["events"]


def encode(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, default=encode, allow_nan=False) + "\n")
    temp.replace(path)


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def output_contract(config_path, out, require_ledger):
    """Supplementary I/O assertions, using the published event schema; no scoring math."""
    config = json.loads(config_path.read_text())
    event = json.loads((out / "events.json").read_text())
    errors = [error.message for error in jsonschema.Draft202012Validator(EVENT_SCHEMA).iter_errors(event)]
    table = pq.ParquetFile(out / "trace.parquet")
    schema = table.schema_arrow
    if schema.names != list(TRACE_TYPES):
        errors.append("trace columns/order disagree with published interface")
    for field, expected in TRACE_TYPES.items():
        if field not in schema.names or schema.field(field).type != expected:
            errors.append(f"wrong trace dtype: {field}")
    for field in ("scenario_id", "seed"):
        if event.get(field) != config.get(field):
            errors.append(f"events.{field} disagrees with scenario input")
    if event.get("n_events") != table.metadata.num_rows:
        errors.append("events.n_events disagrees with Parquet footer")
    if event.get("trace_sha256") != sha(out / "trace.parquet"):
        errors.append("events.trace_sha256 disagrees with emitted bytes")
    for field in ("wall_clock_sec", "events_per_sec"):
        value = event.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            errors.append(f"nonpositive/nonfinite events.{field}")
    if not errors:
        schema_gate = scoring._g1_schema({"unit_dir": config_path.parent, "output_dir": out,
                                         "_events": event, "_t3_profile": "developer"})
        if not schema_gate.passed:
            errors.append(f"official per-scenario g1: {schema_gate.detail}")
    hashes = {"trace.parquet": sha(out / "trace.parquet")}
    ledger = out / "message_trace.parquet"
    if require_ledger and not ledger.exists():
        errors.append("required message ledger absent")
    ledger_schema = None
    message_gate = {"status": "NOT_RUN"}
    if ledger.exists():
        hashes[ledger.name] = sha(ledger)
        ledger_schema = str(pq.ParquetFile(ledger).schema_arrow)
        passed, breaches = semantics.check_message_semantics(pd.read_parquet(ledger))
        message_gate = {"status": "PASS" if passed else "FAIL", "breaches": breaches}
        if require_ledger and not passed:
            errors.append("official message-ledger self-consistency failed")
    return {"status": "FAIL" if errors else "PASS", "errors": errors,
            "trace_schema": str(schema), "ledger_schema": ledger_schema,
            "rows": table.metadata.num_rows, "stable_events": {k: event.get(k) for k in STABLE_FIELDS},
            "actual_events": event, "parquet_hashes": hashes, "message_semantics": message_gate}


def grade(unit, out):
    ctx = {"unit_dir": unit, "output_dir": out}
    verdict = scoring.build_developer_verifier(ctx).run(ctx)
    result = asdict(verdict)
    result["gate_statuses"] = {name: ("PASS" if verdict.gate_results[name].passed else "FAIL")
                              if name in verdict.gate_results else "NOT_RUN"
                              for name in ("g0_integrity", "g1_schema", "g2_cutoff_resource", "g3_domain_semantics")}
    return result


def snapshot(unit, out, card):
    if batch.batch_meta(unit):
        return {s["sub"]: output_contract(unit / s["scenario_file"], out / s["sub"], True)
                for s in batch.load_subs(unit)}
    return {"single": output_contract(unit / "scenario.json", out,
                                      card["scoring"]["params"]["requires_message_ledger"])}


def identical(left, right):
    return (set(left) == set(right) and all(
        left[k]["parquet_hashes"] == right[k]["parquet_hashes"]
        and left[k]["stable_events"] == right[k]["stable_events"] for k in left))

