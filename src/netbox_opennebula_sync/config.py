"""Configuration loading for netbox-opennebula-sync."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_EXCLUDE_INTERFACES = (
    r"^(lo|docker\d*|br-.*|veth.*|virbr\d*|cni\d*|flannel\..*|cali.*|tunl\d*)$"
)
DEFAULT_IGNORE_HOSTNAMES = ("localhost", "demo", "demo.local", "ubuntu", "debian")


@dataclass
class NetBoxConfig:
    url: str
    token: str
    verify_ssl: bool | str = True
    site: str = "default"
    tenant: str | None = None
    cluster_name: str | None = None
    create_missing_hosts: bool = True
    host_device_role: str = "Hypervisor"
    host_manufacturer: str = "Generic"
    host_device_type: str = "KVM Host"
    dns_suffix: str = ""
    socks_proxy: str | None = None
    timeout: float = 30.0


@dataclass
class OpenNebulaConfig:
    endpoint: str
    username: str
    token: str
    timeout: float = 30.0

    @property
    def credentials(self) -> str:
        return f"{self.username}:{self.token}"


@dataclass
class SnmpConfig:
    enabled: bool = True
    community: str = "public"
    timeout: float = 1.0
    retries: int = 0
    exclude_interfaces: str = DEFAULT_EXCLUDE_INTERFACES
    ignore_hostnames: list[str] = field(
        default_factory=lambda: list(DEFAULT_IGNORE_HOSTNAMES)
    )


@dataclass
class SyncConfig:
    orphan_policy: str = "mark_offline"  # mark_offline | delete | ignore
    tags: list[str] = field(default_factory=lambda: ["opennebula", "discovered"])
    interval: int = 900
    dry_run: bool = False


@dataclass
class AppConfig:
    netbox: NetBoxConfig
    opennebula: OpenNebulaConfig
    snmp: SnmpConfig = field(default_factory=SnmpConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)

    def exclude_iface_re(self) -> re.Pattern[str]:
        return re.compile(self.snmp.exclude_interfaces, re.IGNORECASE)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load YAML config and overlay environment variables."""
    data: dict[str, Any] = {}
    if path:
        raw = Path(path).read_text(encoding="utf-8")
        loaded = yaml.safe_load(raw) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config root must be a mapping: {path}")
        data = loaded

    nb = data.get("netbox") or {}
    one = data.get("opennebula") or {}
    snmp = data.get("snmp") or {}
    sync = data.get("sync") or {}

    netbox_url = _env("NETBOX_URL", nb.get("url"))
    netbox_token = _env("NETBOX_TOKEN", nb.get("token"))
    one_endpoint = _env("ONE_ENDPOINT", one.get("endpoint"))
    one_user = _env("ONE_USERNAME", one.get("username"))
    one_token = _env("ONE_TOKEN", one.get("token") or _env("ONE_PASSWORD"))
    # ONE_CREDENTIALS=username:token overrides split username/token when set
    one_creds = _env("ONE_CREDENTIALS")
    if one_creds and ":" in one_creds:
        one_user, one_token = one_creds.split(":", 1)

    missing = [
        name
        for name, value in (
            ("netbox.url / NETBOX_URL", netbox_url),
            ("netbox.token / NETBOX_TOKEN", netbox_token),
            ("opennebula.endpoint / ONE_ENDPOINT", one_endpoint),
            ("opennebula.username / ONE_USERNAME", one_user),
            ("opennebula.token / ONE_TOKEN", one_token),
        )
        if not value
    ]
    if missing:
        raise SystemExit("Missing required configuration: " + ", ".join(missing))

    verify = _env("NETBOX_VERIFY_SSL", nb.get("verify_ssl"))
    if verify is None:
        verify_ssl: bool | str = True
    elif str(verify).lower() in {"false", "0", "no", "off"}:
        verify_ssl = False
    elif str(verify).lower() in {"true", "1", "yes", "on"}:
        verify_ssl = True
    else:
        verify_ssl = str(verify)

    socks = _env("ALL_PROXY") or _env("HTTPS_PROXY") or _env("NETBOX_SOCKS") or nb.get(
        "socks_proxy"
    )

    ignore = snmp.get("ignore_hostnames") or list(DEFAULT_IGNORE_HOSTNAMES)
    if isinstance(ignore, str):
        ignore = [x.strip() for x in ignore.split(",") if x.strip()]

    return AppConfig(
        netbox=NetBoxConfig(
            url=str(netbox_url).rstrip("/"),
            token=str(netbox_token),
            verify_ssl=verify_ssl,
            site=str(_env("NETBOX_SITE", nb.get("site") or "default")),
            tenant=_env("NETBOX_TENANT", nb.get("tenant")),
            cluster_name=_env("NETBOX_CLUSTER_NAME", nb.get("cluster_name")),
            create_missing_hosts=_as_bool(
                _env("NETBOX_CREATE_MISSING_HOSTS", nb.get("create_missing_hosts")),
                True,
            ),
            host_device_role=str(nb.get("host_device_role") or "Hypervisor"),
            host_manufacturer=str(nb.get("host_manufacturer") or "Generic"),
            host_device_type=str(nb.get("host_device_type") or "KVM Host"),
            dns_suffix=str(_env("NETBOX_DNS_SUFFIX", nb.get("dns_suffix") or "")).lstrip(
                "."
            ),
            socks_proxy=socks,
            timeout=float(_env("NETBOX_TIMEOUT", nb.get("timeout") or 30)),
        ),
        opennebula=OpenNebulaConfig(
            endpoint=str(one_endpoint),
            username=str(one_user),
            token=str(one_token),
            timeout=float(_env("ONE_TIMEOUT", one.get("timeout") or 30)),
        ),
        snmp=SnmpConfig(
            enabled=_as_bool(_env("SNMP_ENABLED", snmp.get("enabled")), True),
            community=str(_env("SNMP_COMMUNITY", snmp.get("community") or "public")),
            timeout=float(_env("SNMP_TIMEOUT", snmp.get("timeout") or 1)),
            retries=int(_env("SNMP_RETRIES", snmp.get("retries") or 0)),
            exclude_interfaces=str(
                snmp.get("exclude_interfaces") or DEFAULT_EXCLUDE_INTERFACES
            ),
            ignore_hostnames=[str(x).lower() for x in ignore],
        ),
        sync=SyncConfig(
            orphan_policy=str(
                _env("SYNC_ORPHAN_POLICY", sync.get("orphan_policy") or "mark_offline")
            ),
            tags=list(sync.get("tags") or ["opennebula", "discovered"]),
            interval=int(_env("SYNC_INTERVAL", sync.get("interval") or 900)),
            dry_run=_as_bool(_env("SYNC_DRY_RUN", sync.get("dry_run")), False),
        ),
    )
