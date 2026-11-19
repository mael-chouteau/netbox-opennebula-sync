"""Live OpenNebula status probe (cheap; not a full reconcile)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .config import OpenNebulaConfig
from .models import OpenNebulaSyncConfig
from .opennebula import OpenNebulaClient


@dataclass
class LiveStatus:
    reachable: bool
    latency_ms: float | None
    version: str = ""
    zone_id: int | None = None
    zone_name: str = ""
    cluster_id: int | None = None
    cluster_name: str = ""
    hosts_active: int = 0
    hosts_offline: int = 0
    vms_active: int = 0
    vms_offline: int = 0
    vms_other: int = 0
    vnets: int = 0
    error: str = ""


def probe_opennebula(cfg: OpenNebulaSyncConfig) -> LiveStatus:
    token = cfg.get_one_token()
    if not cfg.one_endpoint or not cfg.one_username or not token:
        return LiveStatus(
            reachable=False,
            latency_ms=None,
            error="OpenNebula connection is not configured",
        )
    one_cfg = OpenNebulaConfig(
        endpoint=cfg.one_endpoint,
        username=cfg.one_username,
        token=token,
        timeout=float(cfg.one_timeout or 30),
    )
    client = OpenNebulaClient(one_cfg)
    started = time.monotonic()
    try:
        # Cheap version call first
        version = client._call("one.system.version")
        inventory = client.collect()
        latency = (time.monotonic() - started) * 1000
        hosts_active = sum(1 for h in inventory.hosts if h.status == "active")
        hosts_offline = len(inventory.hosts) - hosts_active
        vms_active = sum(1 for v in inventory.vms if v.status == "active")
        vms_offline = sum(1 for v in inventory.vms if v.status == "offline")
        vms_other = len(inventory.vms) - vms_active - vms_offline
        return LiveStatus(
            reachable=True,
            latency_ms=round(latency, 1),
            version=str(version),
            zone_id=inventory.zone_id,
            zone_name=inventory.zone_name,
            cluster_id=inventory.cluster_id,
            cluster_name=inventory.cluster_name,
            hosts_active=hosts_active,
            hosts_offline=hosts_offline,
            vms_active=vms_active,
            vms_offline=vms_offline,
            vms_other=vms_other,
            vnets=len(inventory.vnets),
        )
    except Exception as exc:
        latency = (time.monotonic() - started) * 1000
        return LiveStatus(
            reachable=False,
            latency_ms=round(latency, 1),
            error=str(exc)[:500],
        )
    finally:
        client.close()
