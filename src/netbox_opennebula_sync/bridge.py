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


def ensure_netbox_api_token(cfg: OpenNebulaSyncConfig) -> str:
    """Return a usable NetBox API token, creating a dedicated v2 token if needed."""
    existing = cfg.get_netbox_token()
    if existing:
        return existing
    from users.models import Token, User

    user = User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
    if user is None:
        raise RuntimeError("No active superuser available to mint a NetBox API token")
    token_obj = Token(
        user=user,
        description="netbox-opennebula-sync-plugin",
        write_enabled=True,
        version=2,
    )
    token_obj.save()
    secret = token_obj.token
    key = token_obj.key
    if not secret or not key:
        raise RuntimeError(
            "Could not read newly created NetBox token; set NetBox API token in Settings"
        )
    full = f"nbt_{key}.{secret}"
    cfg.set_netbox_token(full)
    OpenNebulaSyncConfig.objects.filter(pk=cfg.pk).update(
        netbox_token_encrypted=cfg.netbox_token_encrypted
    )
    return full


def app_config_from_db(cfg: OpenNebulaSyncConfig) -> AppConfig:
    token = ensure_netbox_api_token(cfg)
    one_token = cfg.get_one_token()
    if not cfg.one_endpoint or not cfg.one_username or not one_token:
        raise RuntimeError("OpenNebula endpoint/username/token are required")
    ignore = cfg.ignore_hostnames_list()
    return AppConfig(
        netbox=NetBoxConfig(
            url=cfg.netbox_url.rstrip("/"),
            token=token,
            verify_ssl=cfg.netbox_verify_ssl,
            site=cfg.site_name or "default",
            cluster_name=cfg.cluster_name or None,
            create_missing_hosts=cfg.create_missing_hosts,
            dns_suffix=(cfg.dns_suffix or "").lstrip("."),
            host_header=cfg.netbox_host_header or None,
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
