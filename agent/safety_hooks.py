"""
Safety hooks for Celesto sandboxes.

These hooks run BEFORE a command reaches the guest VM.
They can log, audit, or block (raise CommandBlockedError) dangerous commands.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Patterns that are always blocked (regardless of network policy)
BLOCKED_PATTERNS = [
    # Fork bombs
    re.compile(r":\(\s*\)\s*\{"),
    re.compile(r"fork\s*bomb"),
    # Attempts to read host secrets
    re.compile(r"/etc/shadow"),
    re.compile(r"/proc/\d+/environ"),
    # Exfiltration via curl/wget to external hosts (when network_policy=off)
    re.compile(r"curl\s+.*-d\s+.*\$\w+"),
    re.compile(r"wget\s+.*--post-data"),
    # Attempts to escape container
    re.compile(r"nsenter"),
    re.compile(r"unshare\s+--pid"),
    # Crypto miners
    re.compile(r"xmrig|minergate|nicehash"),
]

# Patterns that are suspicious but allowed (logged with WARNING)
SUSPICIOUS_PATTERNS = [
    re.compile(r"rm\s+-rf\s+/"),
    re.compile(r"dd\s+if=/dev/zero"),
    re.compile(r"chmod\s+777\s+/"),
    re.compile(r"curl\s+.*\|\s*bash"),
    re.compile(r"wget\s+.*\|\s*sh"),
]


class CommandBlockedError(Exception):
    """Raised when a safety hook blocks a command."""
    pass


def pre_command_hook(
    sandbox_name: str,
    command: str,
    network_policy: str = "off",
) -> dict:
    """
    Pre-command safety hook. Called before every command sent to the sandbox.

    Returns a dict with:
      - decision: "allow" or "block"
      - reason: human-readable explanation
    """
    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if pattern.search(command):
            reason = f"Command matches blocked pattern: {pattern.pattern!r}"
            logger.warning(
                "[HOOK BLOCK] sandbox=%s command=%r reason=%s",
                sandbox_name, command, reason,
            )
            return {"decision": "block", "reason": reason}

    # Check suspicious patterns — log but allow
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.search(command):
            logger.warning(
                "[HOOK SUSPICIOUS] sandbox=%s command=%r pattern=%s",
                sandbox_name, command, pattern.pattern,
            )

    # Network-off sandbox: block any outbound curl/wget/nc
    if network_policy == "off":
        net_exfil = re.compile(
            r"\b(curl|wget|nc|ncat|netcat|python3?\s+-c.*urllib|requests\.get)\b"
        )
        if net_exfil.search(command):
            reason = "Network policy is OFF; outbound network command blocked"
            logger.warning(
                "[HOOK BLOCK] sandbox=%s command=%r reason=%s",
                sandbox_name, command, reason,
            )
            return {"decision": "block", "reason": reason}

    logger.debug("[HOOK ALLOW] sandbox=%s command=%r", sandbox_name, command)
    return {"decision": "allow", "reason": ""}


def post_command_hook(sandbox_name: str, command: str, exit_code: int, stdout: str):
    """Post-command hook for auditing output."""
    if exit_code != 0:
        logger.info(
            "[HOOK POST] sandbox=%s exit_code=%d command=%r",
            sandbox_name, exit_code, command,
        )
