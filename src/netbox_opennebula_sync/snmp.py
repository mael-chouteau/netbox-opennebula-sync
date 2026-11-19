"""Optional SNMPv2c guest enrichment (hostname / OS) without QEMU guest agent."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from .config import SnmpConfig
from .inventory import Inventory
from .opennebula import guess_platform, slugify_vm_name

log = logging.getLogger(__name__)

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
SYS_DESCR_OID = "1.3.6.1.2.1.1.1.0"


def _snmpget(ip: str, cfg: SnmpConfig, oid: str) -> str | None:
    binary = shutil.which("snmpget")
    if not binary:
        return None
    cmd = [
        binary,
        "-v2c",
        "-c",
        cfg.community,
        "-t",
        str(cfg.timeout),
        "-r",
        str(cfg.retries),
        "-Oqv",
        ip,
        oid,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg.timeout + 2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip().strip('"')
    return value or None


def _normalize_hostname(sysname: str, dns_suffix: str) -> tuple[str, str]:
    """Return (vm_name_label, dns_name)."""
    host = sysname.strip().rstrip(".").lower()
    if dns_suffix and host.endswith("." + dns_suffix.lower()):
        label = host[: -(len(dns_suffix) + 1)]
        return slugify_vm_name(label), host
    if "." in host:
        label = host.split(".", 1)[0]
        return slugify_vm_name(label), host
    dns = f"{host}.{dns_suffix}" if dns_suffix else host
    return slugify_vm_name(host), dns


def enrich_inventory(
    inventory: Inventory,
    snmp: SnmpConfig,
    dns_suffix: str = "",
) -> Inventory:
    """Mutate VM names/platforms from SNMP when available and trustworthy."""
    if not snmp.enabled:
        return inventory
    if not shutil.which("snmpget"):
        log.warning("snmpget not found; SNMP guest enrichment disabled")
        return inventory

    ignore = {h.lower() for h in snmp.ignore_hostnames}
    for vm in inventory.vms:
        if vm.status != "active":
            continue
        ip = next((n.ip for n in vm.nics if n.ip), None)
        if not ip:
            continue
        sysname = _snmpget(ip, snmp, SYS_NAME_OID)
        sysdescr = _snmpget(ip, snmp, SYS_DESCR_OID) or ""
        if not sysname:
            log.debug("SNMP unreachable for %s (%s)", vm.name, ip)
            continue
        short = sysname.split(".", 1)[0].lower()
        if sysname.lower() in ignore or short in ignore:
            log.debug("Ignoring placeholder SNMP hostname %s for %s", sysname, vm.name)
            continue
        label, dns_name = _normalize_hostname(sysname, dns_suffix)
        vm.dns_name = dns_name
        # Keep OpenNebula display name unless SNMP gives a cleaner label
        if label and label != "vm":
            vm.name = label
        platform = guess_platform("", sysdescr)
        if platform:
            vm.platform = platform
        log.debug(
            "SNMP enriched %s -> name=%s dns=%s platform=%s",
            ip,
            vm.name,
            dns_name,
            vm.platform,
        )
    return inventory


def should_skip_interface(name: str, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.match(name or ""))
