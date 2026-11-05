"""
Sandbox tool wrappers for the Celesto autograder agent.

Every tool that executes code, writes files, or installs packages runs
through these wrappers — NEVER directly on the host.

The sandbox is simulated here for local testing without a Celesto account.
When CELESTO_PROVIDER=cloud, the real Celesto SDK is used instead.
"""

import os
import time
import uuid
import logging
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.safety_hooks import pre_command_hook, post_command_hook, CommandBlockedError

logger = logging.getLogger(__name__)

COMMAND_LOG = Path(__file__).parent.parent / "logs" / "commands.jsonl"
CELESTO_PROVIDER = os.getenv("CELESTO_PROVIDER", "local_sim")


def _log_command(sandbox_name: str, command: str, decision: str):
    """Append a command audit line to logs/commands.jsonl."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sandbox_name": sandbox_name,
        "command": command,
        "decision": decision,
        "execution_target": "celesto_sandbox",
    }
    COMMAND_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMAND_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


class SandboxResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str, ok: bool):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.ok = ok

    def __repr__(self):
        return f"SandboxResult(exit_code={self.exit_code}, ok={self.ok})"


class CelestoSandbox:
    """
    Wraps a Celesto sandbox (real or simulated).
    Applies safety hooks before every command.
    Cleans up on success, failure, and Ctrl-C via context manager.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        network_policy: str = "off",
        problem_id: str = "unknown",
    ):
        self.name = name or self._unique_name()
        self.network_policy = network_policy
        self.problem_id = problem_id
        self._sandbox = None
        self._boot_start: Optional[float] = None
        self._boot_ready: Optional[float] = None
        self._tmpdir: Optional[tempfile.TemporaryDirectory] = None

    @staticmethod
    def _unique_name() -> str:
        """Generate a unique sandbox name matching sbx-[a-z0-9]{8,}."""
        uid = uuid.uuid4().hex[:12]  # 12 lowercase hex chars
        return f"sbx-{uid}"

    def __enter__(self):
        self._boot_start = time.monotonic()
        logger.info("[SANDBOX] Creating sandbox %s (network=%s)", self.name, self.network_policy)

        if CELESTO_PROVIDER in ("local_sim", ""):
            # Local simulation: use a temp directory as the "sandbox"
            self._tmpdir = tempfile.TemporaryDirectory(prefix=f"celesto_{self.name}_")
            self._sandbox_dir = Path(self._tmpdir.name)
        else:
            # Real Celesto SDK
            try:
                from celesto import Computer  # type: ignore
                self._sdk_computer = Computer(
                    name=self.name,
                    provider=CELESTO_PROVIDER,
                )
                self._sdk_computer.__enter__()
            except ImportError:
                logger.warning("celesto SDK not installed; falling back to local simulation")
                self._tmpdir = tempfile.TemporaryDirectory(prefix=f"celesto_{self.name}_")
                self._sandbox_dir = Path(self._tmpdir.name)

        self._boot_ready = time.monotonic()
        logger.info(
            "[SANDBOX] Ready %s (boot=%.2fs)", self.name,
            self._boot_ready - self._boot_start,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()
        return False  # don't suppress exceptions

    def _cleanup(self):
        logger.info("[SANDBOX] Deleting sandbox %s", self.name)
        if self._tmpdir:
            try:
                self._tmpdir.cleanup()
            except Exception as e:
                logger.warning("[SANDBOX] Cleanup error for %s: %s", self.name, e)
        if hasattr(self, "_sdk_computer"):
            try:
                self._sdk_computer.__exit__(None, None, None)
            except Exception as e:
                logger.warning("[SANDBOX] SDK cleanup error for %s: %s", self.name, e)

    @property
    def boot_to_ready_s(self) -> float:
        if self._boot_start and self._boot_ready:
            return round(self._boot_ready - self._boot_start, 3)
        return 0.0

    def run(self, command: str) -> SandboxResult:
        """
        Run a command inside the sandbox after passing it through the safety hook.
        NEVER runs on the host directly.
        """
        # Safety hook
        hook_result = pre_command_hook(self.name, command, self.network_policy)
        _log_command(self.name, command, hook_result["decision"])

        if hook_result["decision"] == "block":
            raise CommandBlockedError(hook_result["reason"])

        # Execute inside sandbox
        if hasattr(self, "_sdk_computer"):
            r = self._sdk_computer.run(command)
            result = SandboxResult(r.exit_code, r.stdout, r.stderr, r.exit_code == 0)
        else:
            # Local simulation: run in a subprocess restricted to the tmpdir
            try:
                # On Windows use cmd; on Linux/Mac use bash
                shell_cmd = ["cmd", "/c", command] if os.name == "nt" else ["bash", "-c", command]
                proc = subprocess.run(
                    shell_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(self._sandbox_dir),
                )
                result = SandboxResult(
                    proc.returncode,
                    proc.stdout,
                    proc.stderr,
                    proc.returncode == 0,
                )
            except subprocess.TimeoutExpired:
                result = SandboxResult(124, "", "Command timed out after 30s", False)
            except Exception as e:
                result = SandboxResult(1, "", str(e), False)

        post_command_hook(self.name, command, result.exit_code, result.stdout)
        return result

    def write_file(self, path: str, content: str):
        """Write a file into the sandbox workspace."""
        if hasattr(self, "_sdk_computer"):
            self._sdk_computer.upload(path, content.encode())
        else:
            target = self._sandbox_dir / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def read_file(self, path: str) -> str:
        """Read a file from the sandbox workspace."""
        if hasattr(self, "_sdk_computer"):
            return self._sdk_computer.download(path).decode()
        else:
            target = self._sandbox_dir / path.lstrip("/")
            return target.read_text(encoding="utf-8")
