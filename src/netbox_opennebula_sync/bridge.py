"""Build standalone AppConfig from the Django plugin config model."""

from __future__ import annotations

from .config import (
    DEFAULT_EXCLUDE_INTERFACES,
    AppConfig,
    NetBoxConfig,
    OpenNebulaConfig,
    SnmpConfig,
    SyncConfig,
)
from .models import OpenNebulaSyncConfig


def app_config_from_db(cfg: OpenNebulaSyncConfig) -> AppConfig:
    """Map plugin settings to AppConfig (no NetBox HTTP credentials)."""
    one_token = cfg.get_one_token()
    if not cfg.one_endpoint or not cfg.one_username or not one_token:
        raise RuntimeError("OpenNebula endpoint/username/token are required")
    ignore = cfg.ignore_hostnames_list()
    return AppConfig(
        netbox=NetBoxConfig(
            site=(cfg.site.name if cfg.site_id else "default"),
            site_id=cfg.site_id,
            cluster_name=(cfg.cluster.name if cfg.cluster_id else None),
            cluster_id=cfg.cluster_id,
            create_missing_hosts=cfg.create_missing_hosts,
            dns_suffix=(cfg.dns_suffix or "").lstrip("."),
            timeout=float(cfg.one_timeout or 30),
        ),
        opennebula=OpenNebulaConfig(
            endpoint=cfg.one_endpoint,
            username=cfg.one_username,
            token=one_token,
            timeout=float(cfg.one_timeout or 30),
        ),
        snmp=SnmpConfig(
            enabled=cfg.snmp_enabled,
            community=cfg.snmp_community or "public",
            ignore_hostnames=ignore,
            exclude_interfaces=cfg.snmp_exclude_interfaces or DEFAULT_EXCLUDE_INTERFACES,
        ),
        sync=SyncConfig(
            orphan_policy=cfg.orphan_policy or "mark_offline",
            interval=int(cfg.sync_interval or 15) * 60,
            dry_run=cfg.dry_run,
        ),
    )
