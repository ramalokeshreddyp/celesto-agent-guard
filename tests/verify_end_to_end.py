"""
End-to-end audit script verifying all 12 Core Requirements of the hackathon submission.
"""
import os
import sys
import json
import re
import math
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).parent.parent
ERRORS = []
PASSES = []

def check(name, condition, msg=''):
    if condition:
        PASSES.append(name)
        print(f"  [PASS] {name}")
    else:
        ERRORS.append(f"{name}: {msg}")
        print(f"  [FAIL] {name}: {msg}")

def run():
    print("=== 1. Control Plane & Compose Check ===")
    compose_path = REPO / "docker-compose.yml"
    dockerfile_path = REPO / "Dockerfile"
    check("docker-compose.yml exists", compose_path.exists())
    check("Dockerfile exists", dockerfile_path.exists())
    compose_txt = compose_path.read_text(encoding="utf-8")
    check("services: api and ledger present", "api:" in compose_txt and "ledger:" in compose_txt)
    check("healthchecks defined on both", compose_txt.count("healthcheck:") >= 2)
    check("seeds volume mounted", "./seeds" in compose_txt or "seeds:" in compose_txt)

    print("\n=== 2. Environment Variables Check ===")
    env_ex = REPO / ".env.example"
    live_env = REPO / ".env"
    check(".env.example exists", env_ex.exists())
    check("No live .env committed", not live_env.exists())
    env_txt = env_ex.read_text(encoding="utf-8")
    for k in ["CELESTO_PROVIDER", "CELESTO_API_KEY", "LLM_API_KEY", "LLM_MODEL", "DATABASE_URL", "API_PORT"]:
        check(f"Key {k} in .env.example", k in env_txt)

    print("\n=== 3. Problem JSON Check ===")
    prob = json.loads((REPO / "reports" / "problem.json").read_text(encoding="utf-8"))
    check("problem.json keys present", all(k in prob for k in ["who", "agent_work", "proof_output", "idea_source"]))
    check("who length >= 40", len(prob.get("who", "")) >= 40)
    check("agent_work length >= 40", len(prob.get("agent_work", "")) >= 40)
    check("proof_output length >= 20", len(prob.get("proof_output", "")) >= 20)
    check("idea_source valid", prob.get("idea_source") in ["idea_bank", "original"])

    print("\n=== 4. Command Audit Log Check ===")
    cmd_lines = [json.loads(l) for l in (REPO / "logs" / "commands.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    check("commands.jsonl has lines", len(cmd_lines) > 0)
    sbx_re = re.compile(r"^sbx-[a-z0-9]{8,}$")
    all_valid_cmds = all(
        "ts" in c and sbx_re.match(c.get("sandbox_name", "")) and c.get("command") and
        c.get("decision") in ["allow", "block"] and c.get("execution_target") == "celesto_sandbox"
        for c in cmd_lines
    )
    check("All command lines valid celesto_sandbox", all_valid_cmds)

    print("\n=== 5. Capabilities JSON Check ===")
    caps = json.loads((REPO / "reports" / "capabilities.json").read_text(encoding="utf-8"))["capabilities"]
    check(">= 2 capabilities", len(caps) >= 2)
    allowed_caps = {"persistence", "snapshots", "celestofs", "browser", "published_ports", "network_policy", "safety_hooks", "host_mounts", "coding_agent_preset", "agentor_durable"}
    check("Valid unique capabilities", len(caps) == len(set(c["id"] for c in caps)) and all(c["id"] in allowed_caps for c in caps))
    check("Capability why >= 80 chars", all(len(c["why"]) >= 80 for c in caps))
    check("Evidence paths exist", all((REPO / c["evidence_path"]).exists() for c in caps))

    print("\n=== 6. Lifecycle JSON Check ===")
    life = json.loads((REPO / "reports" / "lifecycle.json").read_text(encoding="utf-8"))
    check("All 3 cleanup flags true", life.get("cleanup_on_success") and life.get("cleanup_on_failure") and life.get("cleanup_on_interrupt"))
    check("Sandbox names valid & unique", len(life["sandbox_names"]) == len(set(life["sandbox_names"])) and all(sbx_re.match(n) for n in life["sandbox_names"]))

    print("\n=== 7. Reliability & Postmortem Check ===")
    rel = json.loads((REPO / "reports" / "reliability.json").read_text(encoding="utf-8"))
    runs = rel["runs"]
    check(">= 20 runs", len(runs) >= 20 and rel["run_count"] == len(runs))
    check("All runs fresh=true", all(r.get("fresh") is True for r in runs))
    check("Run sandbox names unique & valid", len(runs) == len(set(r["sandbox_name"] for r in runs)) and all(sbx_re.match(r["sandbox_name"]) for r in runs))
    succ_rate = sum(1 for r in runs if r["success"]) / len(runs)
    check("success_rate arithmetic", abs(rel["success_rate"] - succ_rate) <= 0.001)
    wcs = sorted(r["wall_clock_s"] for r in runs)
    n = len(runs)
    med_wc = (wcs[n//2-1] + wcs[n//2]) / 2 if n % 2 == 0 else wcs[n//2]
    p90_wc = wcs[math.ceil(0.90 * n) - 1]
    check("median_wall_clock_s arithmetic", abs(rel["median_wall_clock_s"] - med_wc) <= 0.001)
    check("p90_wall_clock_s arithmetic", abs(rel["p90_wall_clock_s"] - p90_wc) <= 0.001)
    pm_txt = (REPO / rel["postmortem_path"]).read_text(encoding="utf-8")
    check("postmortem.md >= 200 chars", len(pm_txt) >= 200)

    print("\n=== 8. Containment JSON Check ===")
    cont = json.loads((REPO / "reports" / "containment.json").read_text(encoding="utf-8"))
    check("Valid attack type", cont.get("attack") in ["prompt_injection_exfil", "destructive_command", "suspicious_package"])
    check("blocked and host_untouched true", cont.get("blocked") is True and cont.get("host_untouched") is True)
    check("evidence paths exist", all((REPO / ep).exists() for ep in cont.get("evidence_paths", [])))

    print("\n=== 9. Failure Policy & Trace Check ===")
    fp = json.loads((REPO / "reports" / "failure_policy.json").read_text(encoding="utf-8"))
    check("failed_step=7, total_steps=10", fp.get("failed_step") == 7 and fp.get("total_steps") == 10)
    check("policy in allowed set", fp.get("policy") in ["resume", "rollback", "fresh"])
    check("rationale >= 200 chars", len(fp.get("rationale", "")) >= 200)
    trace_lines = [json.loads(l) for l in (REPO / fp["trace_path"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    check("Trace has policy_applied event matching policy", any(t.get("event") == "policy_applied" and t.get("policy") == fp["policy"] for t in trace_lines))

    print("\n=== 10. Concurrency JSON Check ===")
    conc = json.loads((REPO / "reports" / "concurrency.json").read_text(encoding="utf-8"))
    check(">= 5 concurrent jobs", len(conc.get("jobs", [])) >= 5)
    check("Job sandbox names valid & unique", len(conc["jobs"]) == len(set(j["sandbox_name"] for j in conc["jobs"])) and all(sbx_re.match(j["sandbox_name"]) for j in conc["jobs"]))
    check("breakage_notes >= 40 chars", len(conc.get("breakage_notes", "")) >= 40)

    print("\n=== 11. Live Ledger API HTTP Checks ===")
    try:
        with urllib.request.urlopen("http://localhost:8080/health") as resp:
            h = json.loads(resp.read().decode())
            check("GET /health returns 200 {'status': 'ok'}", resp.status == 200 and h.get("status") == "ok")
    except Exception as e:
        check("GET /health reachable", False, str(e))

    try:
        with urllib.request.urlopen("http://localhost:8080/api/runs") as resp:
            runs_api = json.loads(resp.read().decode())
            check("GET /api/runs includes seeded sbx-seeddemo1", resp.status == 200 and any(r["sandbox_name"] == "sbx-seeddemo1" for r in runs_api))
    except Exception as e:
        check("GET /api/runs reachable", False, str(e))

    try:
        req = urllib.request.Request(
            "http://localhost:8080/api/runs",
            data=json.dumps({
                "run_id": "final-check-run-100",
                "sandbox_name": "sbx-finalcheck100",
                "problem_id": "final-verify",
                "state": "succeeded",
                "execution_target": "celesto_sandbox"
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            res = json.loads(resp.read().decode())
            check("POST /api/runs valid returns 201", resp.status == 201 and res.get("sandbox_name") == "sbx-finalcheck100")
    except Exception as e:
        check("POST /api/runs valid returns 201", False, str(e))

    try:
        req = urllib.request.Request(
            "http://localhost:8080/api/runs",
            data=json.dumps({
                "run_id": "final-check-bad-target-100",
                "sandbox_name": "sbx-finalcheck100",
                "problem_id": "final-verify",
                "state": "running",
                "execution_target": "host"
            }).encode(),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)
        check("POST execution_target: host returns 400", False, "Did not fail with 400")
    except urllib.error.HTTPError as e:
        check("POST execution_target: host returns 400", e.code == 400, f"Got status {e.code}")
    except Exception as e:
        check("POST execution_target: host returns 400", False, str(e))

    print("\n=== 12. README.md Required Phrases Check ===")
    readme_txt = (REPO / "README.md").read_text(encoding="utf-8")
    for p in ["Problem statement", "How I used Celesto", "Eval report", "Containment test", "State and failure design", "Setup"]:
        check(f"Phrase '{p}' present in README", p in readme_txt)

    print("\n========================================")
    print(f"TOTAL: {len(PASSES)} Passed, {len(ERRORS)} Failed")
    print("========================================")
    if ERRORS:
        sys.exit(1)

if __name__ == "__main__":
    run()
