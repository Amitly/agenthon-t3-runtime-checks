# Frozen F/I Final-style acceptance, preregistered 2026-10-13

This explicitly replaces the unexecuted original 26-call Core004C schedule. Run
37648545629 remains a Config.Image preflight failure, with zero simulations and
zero resource probes. Its failure is not candidate output failure. The repaired
digest-bound identity comparator and its original regression tests are retained.

The fixed source pair is official T3 fe32378d92b9767a0452c8fbb9911dcf722a8c87
and common v2.5.1 / 50fb2dc2b39c70f4cf81fcd269943782eddfaed0. `frozen.json`
continues to preserve the old historical-tool plan and exact image identities;
`final_plan.json` controls this replacement. `run_ci.py` is retained to test the
old 26-call schedule but is not invoked by the workflow. The new entry is
`final_run.py`. No simulator, image bytes, or upstream verifier are changed.

Each listed unit/version block runs five fresh serial containers with the exact
same unmodified input seed. Run zero is a mandatory successful warmup, excluded
only from the four-rate median. The first 60 calls comprise I eight blocks and
F four blocks. Unit and version-block order is frozen in `final_plan.json`:

| Unit | Block order (each block is five calls) |
|---|---|
| s001 | I |
| eq-deterministic-baseline | I |
| mp05 | F then I |
| as06 | I |
| ra03 | I |
| sf-01 | I then F |
| mega | F then I |
| homog-4 | I then F |

Every invocation must pass current content/schema/ledger/telemetry checks, exact
reference event counts for all tiers, real resource readback, 300-second timeout,
and the candidate's own stable-output binding. Volatile timing JSON is checked
on every invocation, never frozen. Cross-candidate stable equality is reported
separately. The current public `_stage_input` still copies only scenario input
files; no reference traces, checks, scoring cache, or card are mounted. F/I always
produce their full ledgers. This cannot validate a candidate that requires the
new optional platform card mount, but these exact candidates do not read it.

Primary local performance is `n_events / (Docker FinishedAt - StartedAt)`, then
the median of four rates, preserving nanosecond daemon timestamp input. This is
not `n_events / median(time)` for an even number of repeats. Complete Docker CLI
wall and original self time are also retained, without subtracting overhead.
The reused official local timer caps the complete Docker CLI at 300 seconds;
the daemon interval must also be at most 300 seconds. This conservative local
envelope can stop before a full 300-second daemon interval and is not claimed
as exact production timeout enforcement. Such a stop is explicitly classified
for review, not automatically attributed to the candidate.
There is no fabricated `host_metrics.json`, C1/C2 signature, production attestation,
hidden-set score, or new Development/Final platform result.

The preregistered local risk flag is I median daemon time more than 5% AND more
than 50 ms above F median on any of the four comparison units. This is a local
candidate-selection rule, not an official gate or reliable significance test.
After all 60 calls pass, no risk flags yields I review-ready. A flag yields F
conditional acceptance on the remaining four units, five calls each. No sample
is repeated, and the maximum is 80 attempts. A true resource/output/timeout
failure stops the controller instead of automatically switching candidates;
root-cause review is needed before any separately recorded continuation.

Resources remain native linux/amd64, runc, actual 4-CPU CFS quota, 16 GiB memory
with no swap, UID/GID 65534, read-only root/input, network none, no capabilities,
no new privileges, 256 PIDs, nofile 1024, nproc 256, /tmp 64 MiB/noexec. The sole
old-limit change is current T3's 256 MiB file and output-tree limit. File size is
enforced by rlimit; output-tree size is checked after exit, not advertised as a
live aggregate filesystem quota. Both raw and inspected image Config must have
no nonempty VOLUME declaration; runtime mounts must be only input/output plus
the declared tmpfs. A short I resource/native-ABI probe is charged separately.

The workflow remains named `Frozen I CFS spot check`, manual workflow_dispatch
only, no inputs, one standard ubuntu-24.04 job, attempt one only, no new secrets
or paid runner. Necessary workflow changes are the new offline test/entry names,
360-minute job ceiling and seven-day bounded artifact retention. Controller
admission stops new calls by 340 minutes so final evidence can be retained.
The job does not dispatch itself, publish images, pack a Team claim or upload.

All metadata is retained; Parquet retention remains capped at 100 MiB with
hash-bound duplicate aliases and explicit omissions. This is not a complete
backup of all repeated raw output. Only new evidence is included. Actual CI
results must be downloaded promptly and independently reviewed before a private
acceptance receipt can enable Final packaging. `REVIEW_READY` is not `READY`.
