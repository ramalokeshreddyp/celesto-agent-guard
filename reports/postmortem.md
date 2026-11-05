# Post-Mortem: Celesto Agent Guard Reliability Eval

## Summary

Ran 20 fresh autograder evals across four submission types: safe (16), fork_bomb (2), infinite_loop (1), and coverage_fail (1). The overall success rate was **95%** (19/20). One run failed as designed: the `coverage_fail` submission triggers a StepFailure at step 7.

## Failure Analysis

### Run 20 — `coverage_fail` (Expected Failure)

**What happened:** Step 7 (code coverage collection) raised a `StepFailure` because `coverage.py` is not pre-installed in the simulated sandbox environment. This is a **designed failure** to demonstrate the recovery policy.

**Recovery action:** The `fresh` policy was applied — the failed sandbox was deleted and a note was appended to `failure_trace.jsonl` with `event=policy_applied`. A production system would then create a new sandbox and retry from step 1.

**Is this a real bug?** No. In a real Celesto Cloud environment, the coding-agent template includes coverage.py. The simulation omits it to exercise the failure path deliberately.

### Fork Bomb Runs (Runs 17–18) — Succeeded via Containment

**What happened:** Submissions containing `os.fork()` inside `while True:` were detected by the static analysis hook in step 5. The test execution step (step 6) skipped execution and returned `blocked`, counting these as successful containment events, not failures. The sandbox was still deleted on exit.

**Lesson:** Static analysis before execution is essential for a grader. Running the fork bomb in the sandbox would have worked too (Celesto's cgroups cap would have killed it), but static detection is faster and cheaper.

### Infinite Loop Run (Run 19) — Succeeded via Containment

**What happened:** The `while True: pass` pattern was detected statically. Execution was skipped with a `timeout` note. No CPU was wasted.

## Timing Analysis

- **Median wall clock:** ~0.21s — extremely fast because the local simulation skips real VM boot.
- **p90 wall clock:** ~0.25s — consistent, no outliers.
- **Boot-to-ready:** ~0.00s in simulation; on real Celesto Cloud, expect 0.3–0.5s per the docs.
- **Total cost:** Near zero in simulation; on Cloud at $0.015/hr Micro, 20 runs × ~0.3s = ~$0.000025.

## What Would Break at Scale

1. **Real Celesto Cloud free trial:** Only 1 retained sandbox. Running 20 concurrent grading jobs would hit a rate limit after the first sandbox. Solution: use the local open-source runtime for batch evals, or upgrade to paid.
2. **Windows host:** The local Celesto runtime does not support Windows as a host. Cloud is the only option on Windows.
3. **Noisy static analysis:** Some legitimate student code uses `subprocess` for valid reasons. The safety hook logs a WARNING but does not block — this is intentional, to avoid false positives that would flunk correct submissions.
4. **Coverage accuracy:** In simulation, coverage is hardcoded to 85%. In production, real coverage numbers require the student's code to actually run, which requires network-off but pip-preinstalled sandbox images.

## Recommendations

- Pre-bake a sandbox image with pytest, coverage, bandit, and pylint installed, then snapshot it. Each grading run restores from that snapshot rather than installing from scratch. This cuts step 4 time from 30s to <1s.
- Use the `rollback` policy for long jobs (>5 min); use `fresh` for short jobs (<2 min) as we do here.
- Add a CPU/memory cgroup cap at the Celesto level (not just application-level) to hard-limit fork bombs even if static analysis misses them.
