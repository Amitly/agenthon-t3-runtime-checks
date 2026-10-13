> Current 2026-10-13 entry: [Final-style acceptance plan](FINAL_PLAN.md).
> This explicitly replaces the unexecuted 26-call plan below with 60 initial
> calls and, only on a recorded material daemon regression, 20 remaining F
> calls. The workflow invokes `final_run.py`; `run_ci.py` remains historical.
> Both use the same fixed public F/I images. Historical failure records remain.

# Frozen I CFS spot check

This repository runs one bounded local developer check of two published, immutable Track3 simulator images. It contains no simulator implementation, private research history, old run outputs, credentials, team proof or submission package. F remains the research control; publication or this small check does not promote I or establish official performance.

Only manually dispatched standard public ubuntu-24.04 x64 Actions are allowed. One serial job,60-minute timeout, no Secrets, no paid runner, no build. The owner authorizes one dispatch; a second new dispatch is allowed only after a wrapper failure before any simulator started. Do not use Re-run jobs. Once simulations start, do not retry or add samples. The local controller refuses duplicate execution in one workspace and caps26 attempts; repository write users must also honor the cross-run budget.

The fixed common2.4.2 / scorer3.1.0 comparison pins are historical and intentionally unchanged. Current upstream requires newer common>=2.4.4; this is not a claim of current submission-contract compatibility. Official scorer, input staging, sanitizer and timer are imported from pinned public sources. Candidate containers see only staged inputs and writable outputs, never reference answers or the host Docker socket.

Before any simulation: anonymous F/I digest pull and exact Config/RootFS checks; real4CPU CFS quota and parent readback;16GiB/no-swap limit, UID65534, read-only root/input,64MiB noexec tmp,256PIDs,1024nofile,64MiB fsize,networknone,all capabilities dropped; exact prebuilt I native extension import/hash. Current MemAvailable must be>=8GiB and >1.5*historical selected peak+2GiB. This does not certify exclusive16GiB RAM, writable-layer quota, B200 or the private official launcher.

At most one resource/import probe is currently planned (hard allowance two). Then I runs s001 and homog4 once. mp05,sf01,pop128,mega each run F/I warmups and FI then IF formal pairs:26 simulations. Correctness/resource failures stop immediately. Two orders both exceeding5% and50ms for the same self/host time metric stop later units. Keep all slow samples. No profiler or timing deductions. CFS observations and previous full cpuset validation remain separate; never claim FULL_CFS_VALIDATED.

Artifacts last one day and are capped100MiB. All new metadata/timings/errors and file inventories are retained first; first failure outputs and one representative successful invocation per unit are preferred. Equal bytes may reference a retained duplicate. The retention manifest explicitly lists unbacked-up outputs. No old2.44GB evidence or image tar is uploaded. Account-wide artifact allowance is unknown; standard public runner minutes are free, artifact storage has separate billing rules. No billing settings are changed.

After a successful check, the owner may separately prepare a private official submission package. This workflow never handles Team Key, uploads to CodaBench, changes repository visibility or publishes another image.

## Config representation repair (2026-10-08)

The first real dispatch, [37648545629](https://github.com/Amitly/agenthon-t3-runtime-checks/actions/runs/37648545629), attempt1 at root `f3a4c6fcb2eda8145eaed419b956b43a18bf1682`, remains failed. It stopped in F preflight with `AssertionError: Image`, before I pull, the resource probe or any simulator. Its original decision says calls0/probes[]; missing calls.json was caused by that execution position. No candidate correctness or CFS availability conclusion follows from the failure.

The expected Config is a reduced inspect representation. Fixed raw config bytes already contain these string values:

| Image | Raw `config.Image` |
|---|---|
| F | `sha256:d1c112377143a047cc1cd2b351754417f0c54991439ecd580d452d63fca09d62` |
| I | `sha256:62ef989ac31023f9328eb0134b7220ddd41845bb3b410cff5d600db1b0181e13` |

These are legacy fields inside the image configuration, not the top-level image `Id` or the running container's `Image` field. F's failed-run inspect contains the exact raw value; retained I inspect omits the field. The first run did not capture actual Docker Engine/API versions. The image metadata `DockerVersion=""` and hosted-runner version do not establish them. The next preflight saves `docker version` before comparisons.

The small `identity/` manifest/config files are exact metadata of the already-public digest references, with no layers, credentials, private history or simulation outputs. Before representation comparison, preflight verifies manifest SHA against the frozen registry reference; config SHA/size against that manifest and frozen image ID; raw and inspected ordered RootFS; linux/amd64; and actual image ID. Frozen references and expected Config are unchanged.

Only `Image` receives the new narrow rule: absent, an exactly typed empty string (the existing default rule), or the exact nonempty string in that image's digest-verified raw config. Each side is checked independently. Unknown nonempty strings, the other image's value, null, booleans, numbers, arrays and objects fail—even when actual and expected happen to agree. A nonempty value without verified raw evidence fails. The missing/default cases are explicit representation cases, not a claim that the raw config has an empty value.

Every other Config field retains strict recursive type/value/order comparison and the previous enumerated missing/default exceptions. Cmd, Entrypoint, Env, WorkingDir, User and Labels are still checked. Actual-vs-frozen, actual-vs-raw and frozen-vs-raw reports enumerate all fields and nested differences; both image reports are saved before raising a configuration error. Unknown fields are not discarded. Runtime resource flags, dependency pins, workflow and acceptance thresholds are unchanged.

Offline controls reproduce the original F failure with the old comparator and check both real inspect subsets against exact raw bytes. They exercise all three Image representations, unbound/cross-image/wrong-type values, changed runtime fields, config/manifest bytes, image ID, ordered RootFS, platform, and complete difference reporting. I's fixture is retained publication inspect, not an invented inspect from the failed CI. Fixture metadata is only for controls, never a simulator input.

After repair readback, the owner uses **Run workflow → main → Run workflow**, with no inputs, to create one new run. Do not use Re-run jobs on the failed run. Agent dispatch remains disabled. The cross-run simulation allowance stays26 and resource-probe allowance stays2; the failed preflight consumed0 of each. No image rebuild/push, current-contract rerun, automatic package or CodaBench upload is performed here. The separate newer offline content checks are not this historical CFS check or a current scoring-clock reproduction.
