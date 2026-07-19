"""Detect the Mac's Tailscale hostname if Tailscale is installed and up.

Callers get the FQDN (e.g. "gaurangs-macbook-pro.tail-abcd.ts.net") or None.
An explicit TAILSCALE_HOSTNAME env var always wins. Any CLI/JSON failure
returns None silently — a Mac without Tailscale is a supported
configuration, not an error condition.
"""
import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def get_tailscale_hostname() -> Optional[str]:
    override = os.environ.get("TAILSCALE_HOSTNAME")
    if override:
        return override.strip().rstrip(".")
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.debug("tailscale CLI unavailable: %s", e)
        return None
    if result.returncode != 0:
        logger.debug("tailscale status exited %s", result.returncode)
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.debug("tailscale status JSON parse failed: %s", e)
        return None
    dns_name = (data.get("Self") or {}).get("DNSName") or ""
    dns_name = dns_name.strip().rstrip(".")
    return dns_name or None
