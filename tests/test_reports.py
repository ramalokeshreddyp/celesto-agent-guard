"""
tests/test_reports.py

Automated validation of all report files required by the Celesto Agent Guard
hackathon submission. Run with: python -m pytest tests/ -v
"""

import json
import math
import re
import os
import sys
from pathlib import Path
from datetime import datetime

import pytest

REPO_ROOT = Path(__file__).parent.parent
REPORTS = REPO_ROOT / "reports"
LOGS = REPO_ROOT / "logs"

SANDBOX_NAME_RE = re.compile(r"^sbx-[a-z0-9]{8,}$")
VALID_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}
VALID_EXECUTION_TARGETS = {"celesto_sandbox"}
VALID_CAPABILITY_IDS = {
    "persistence", "snapshots", "celestofs", "browser", "published_ports",
    "network_policy", "safety_hooks", "host_mounts", "coding_agent_preset",
    "agentor_durable",
}
VALID_ATTACKS = {"prompt_injection_exfil", "destructive_command", "suspicious_package"}
VALID_POLICIES = {"resume", "rollback", "fresh"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def load_json(path: Path):
    assert path.exists(), f"Missing required file: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path):
    assert path.exists(), f"Missing required file: {path}"
    lines = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError as e:
                    pytest.fail(f"{path} line {i} is not valid JSON: {e}")
    return lines


# ---------------------------------------------------------------------------
# 1. docker-compose.yml
# ---------------------------------------------------------------------------

def test_docker_compose_exists():
    assert (REPO_ROOT / "docker-compose.yml").exists()


def test_docker_compose_services():
    import yaml  # optional dep; skip gracefully
    try:
        import yaml
    except ImportError:
        pytest.skip("pyyaml not installed; skipping compose parse")

    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
    services = compose.get("services", {})
    assert "api" in services, "Missing 'api' service"
    assert "ledger" in services, "Missing 'ledger' service"
    for svc in ("api", "ledger"):
        assert "healthcheck" in services[svc], f"Service '{svc}' missing healthcheck"
        hc = services[svc]["healthcheck"]
        for key in ("interval", "timeout", "retries", "start_period"):
            assert key in hc, f"Service '{svc}' healthcheck missing '{key}'"


# ---------------------------------------------------------------------------
# 2. .env.example
# ---------------------------------------------------------------------------

def test_env_example_exists():
    assert (REPO_ROOT / ".env.example").exists(), ".env.example not found"


def test_no_live_env_file():
    assert not (REPO_ROOT / ".env").exists(), ".env must not be committed"


def test_env_example_required_keys():
    content = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    required = [
        "CELESTO_PROVIDER", "CELESTO_API_KEY", "LLM_API_KEY",
        "LLM_MODEL", "DATABASE_URL", "API_PORT",
    ]
    for key in required:
        assert key in content, f".env.example missing key: {key}"


# ---------------------------------------------------------------------------
# 3. reports/problem.json
# ---------------------------------------------------------------------------

def test_problem_json():
    d = load_json(REPORTS / "problem.json")
    assert len(d.get("who", "")) >= 40, "who must be >= 40 characters"
    assert len(d.get("agent_work", "")) >= 40, "agent_work must be >= 40 characters"
    assert len(d.get("proof_output", "")) >= 20, "proof_output must be >= 20 characters"
    assert d.get("idea_source") in ("idea_bank", "original"), \
        "idea_source must be 'idea_bank' or 'original'"


# ---------------------------------------------------------------------------
# 4. logs/commands.jsonl
# ---------------------------------------------------------------------------

def test_commands_jsonl_exists():
    assert (LOGS / "commands.jsonl").exists()


def test_commands_jsonl_format():
    lines = load_jsonl(LOGS / "commands.jsonl")
    assert len(lines) >= 1, "commands.jsonl must have at least one entry"
    for entry in lines:
        assert "ts" in entry
        assert "sandbox_name" in entry
        assert SANDBOX_NAME_RE.match(entry["sandbox_name"]), \
            f"Bad sandbox_name: {entry['sandbox_name']}"
        assert "command" in entry and entry["command"]
        assert entry.get("decision") in ("allow", "block"), \
            f"decision must be allow or block, got: {entry.get('decision')}"
        assert entry.get("execution_target") == "celesto_sandbox", \
            f"execution_target must be celesto_sandbox, got: {entry.get('execution_target')}"


# ---------------------------------------------------------------------------
# 5. reports/capabilities.json
# ---------------------------------------------------------------------------

def test_capabilities_json():
    d = load_json(REPORTS / "capabilities.json")
    caps = d.get("capabilities", [])
    assert len(caps) >= 2, "Need at least 2 capabilities"
    ids_seen = set()
    for cap in caps:
        cid = cap.get("id")
        assert cid in VALID_CAPABILITY_IDS, f"Invalid capability id: {cid}"
        assert cid not in ids_seen, f"Duplicate capability id: {cid}"
        ids_seen.add(cid)
        assert len(cap.get("why", "")) >= 80, f"Capability '{cid}' why must be >= 80 characters"
        ep = cap.get("evidence_path", "")
        assert (REPO_ROOT / ep).exists(), f"evidence_path not found: {ep}"


# ---------------------------------------------------------------------------
# 6. reports/lifecycle.json
# ---------------------------------------------------------------------------

def test_lifecycle_json():
    d = load_json(REPORTS / "lifecycle.json")
    assert d.get("cleanup_on_success") is True
    assert d.get("cleanup_on_failure") is True
    assert d.get("cleanup_on_interrupt") is True
    names = d.get("sandbox_names", [])
    assert len(names) >= 1
    seen = set()
    for name in names:
        assert SANDBOX_NAME_RE.match(name), f"Bad sandbox_name: {name}"
        assert name not in seen, f"Duplicate sandbox_name: {name}"
        seen.add(name)

    # Each name must appear in commands.jsonl or reliability.json
    cmd_names = set()
    if (LOGS / "commands.jsonl").exists():
        for entry in load_jsonl(LOGS / "commands.jsonl"):
            cmd_names.add(entry.get("sandbox_name"))
    rel_names = set()
    if (REPORTS / "reliability.json").exists():
        rel = load_json(REPORTS / "reliability.json")
        for r in rel.get("runs", []):
            rel_names.add(r.get("sandbox_name"))
    all_known = cmd_names | rel_names
    for name in names:
        assert name in all_known, \
            f"lifecycle sandbox_name {name} not found in commands or reliability"


# ---------------------------------------------------------------------------
# 7. reports/reliability.json + postmortem.md
# ---------------------------------------------------------------------------

def test_reliability_json_structure():
    d = load_json(REPORTS / "reliability.json")
    runs = d.get("runs", [])
    n = len(runs)
    assert n >= 20, f"Need at least 20 runs, got {n}"
    assert d.get("run_count") == n, "run_count must equal len(runs)"

    names_seen = set()
    for run in runs:
        assert run.get("fresh") is True, "Every run must have fresh=true"
        name = run.get("sandbox_name", "")
        assert SANDBOX_NAME_RE.match(name), f"Bad sandbox_name: {name}"
        assert name not in names_seen, f"Duplicate sandbox_name: {name}"
        names_seen.add(name)
        assert isinstance(run.get("success"), bool)
        assert isinstance(run.get("wall_clock_s"), (int, float))
        assert run["wall_clock_s"] >= 0
        assert isinstance(run.get("boot_to_ready_s"), (int, float))
        assert run["boot_to_ready_s"] >= 0
        assert isinstance(run.get("cost_usd"), (int, float))
        assert run["cost_usd"] >= 0


def test_reliability_statistics():
    d = load_json(REPORTS / "reliability.json")
    runs = d["runs"]
    n = len(runs)

    successes = sum(1 for r in runs if r["success"])
    expected_rate = round(successes / n, 4)
    assert abs(d["success_rate"] - expected_rate) <= 0.001, \
        f"success_rate mismatch: got {d['success_rate']}, expected {expected_rate}"

    wall_clocks = sorted(r["wall_clock_s"] for r in runs)
    mid_lo = wall_clocks[n // 2 - 1]
    mid_hi = wall_clocks[n // 2]
    expected_median = round((mid_lo + mid_hi) / 2, 3) if n % 2 == 0 else wall_clocks[n // 2]
    assert abs(d["median_wall_clock_s"] - expected_median) <= 0.001, \
        f"median_wall_clock_s mismatch"

    p90_idx = math.ceil(0.90 * n) - 1
    expected_p90 = wall_clocks[p90_idx]
    assert abs(d["p90_wall_clock_s"] - expected_p90) <= 0.001, \
        f"p90_wall_clock_s mismatch"

    boot_times = sorted(r["boot_to_ready_s"] for r in runs)
    mid_lo_b = boot_times[n // 2 - 1]
    mid_hi_b = boot_times[n // 2]
    expected_median_b = round((mid_lo_b + mid_hi_b) / 2, 3) if n % 2 == 0 else boot_times[n // 2]
    assert abs(d["median_boot_to_ready_s"] - expected_median_b) <= 0.001

    expected_cost = round(sum(r["cost_usd"] for r in runs), 6)
    assert abs(d["total_cost_usd"] - expected_cost) <= 0.01

    assert d.get("postmortem_path") == "reports/postmortem.md"
    pm = REPO_ROOT / "reports" / "postmortem.md"
    assert pm.exists() and len(pm.read_text(encoding="utf-8")) >= 200


# ---------------------------------------------------------------------------
# 8. reports/containment.json
# ---------------------------------------------------------------------------

def test_containment_json():
    d = load_json(REPORTS / "containment.json")
    assert d.get("attack") in VALID_ATTACKS
    assert d.get("blocked") is True
    assert d.get("host_untouched") is True
    eps = d.get("evidence_paths", [])
    assert len(eps) >= 1
    for ep in eps:
        assert (REPO_ROOT / ep).exists(), f"evidence_path not found: {ep}"


# ---------------------------------------------------------------------------
# 9. reports/failure_policy.json + failure_trace.jsonl
# ---------------------------------------------------------------------------

def test_failure_policy_json():
    d = load_json(REPORTS / "failure_policy.json")
    assert d.get("failed_step") == 7
    assert d.get("total_steps") == 10
    assert d.get("policy") in VALID_POLICIES
    assert len(d.get("rationale", "")) >= 200, "rationale must be >= 200 characters"
    trace_path = d.get("trace_path", "")
    assert (REPO_ROOT / trace_path).exists(), f"trace_path not found: {trace_path}"

    trace = load_jsonl(REPO_ROOT / trace_path)
    policy = d["policy"]
    matched = any(
        e.get("event") == "policy_applied" and e.get("policy") == policy
        for e in trace
    )
    assert matched, f"No policy_applied line with policy={policy} in trace"


# ---------------------------------------------------------------------------
# 10. reports/concurrency.json
# ---------------------------------------------------------------------------

def test_concurrency_json():
    d = load_json(REPORTS / "concurrency.json")
    jobs = d.get("jobs", [])
    assert len(jobs) >= 5, f"Need >= 5 jobs, got {len(jobs)}"
    names_seen = set()
    for job in jobs:
        name = job.get("sandbox_name", "")
        assert SANDBOX_NAME_RE.match(name), f"Bad sandbox_name: {name}"
        assert name not in names_seen, f"Duplicate sandbox_name: {name}"
        names_seen.add(name)
        assert job.get("started_at"), "started_at must be non-empty"
    notes = d.get("breakage_notes", "")
    assert len(notes) >= 40, "breakage_notes must be >= 40 characters"


# ---------------------------------------------------------------------------
# 11. README.md required phrases
# ---------------------------------------------------------------------------

def test_readme_required_phrases():
    readme = (REPO_ROOT / "README.md")
    assert readme.exists(), "README.md not found"
    content = readme.read_text(encoding="utf-8")
    required = [
        "Problem statement",
        "How I used Celesto",
        "Eval report",
        "Containment test",
        "State and failure design",
        "Setup",
    ]
    for phrase in required:
        assert phrase in content, f"README.md missing phrase: '{phrase}'"
