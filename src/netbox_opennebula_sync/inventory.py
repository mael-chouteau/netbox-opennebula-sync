"""Internal inventory models collected from OpenNebula (+ optional SNMP)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NicInfo:
    name: str
    network: str
    ip: str
    mac: str
    vlan_id: int | None = None
    mtu: int | None = None
    prefix_len: int = 32


@dataclass
class DiskInfo:
    name: str
    size_mb: int
    image: str = ""
    target: str = ""


@dataclass
class HostInfo:
    one_id: int
    name: str
    state: int
    status: str  # active | offline


@dataclass
class VmInfo:
    one_id: int
    name: str
    status: str  # active | offline | staged
    host_name: str | None
    vcpus: int
    memory_mb: int
    uuid: str = ""
    template_id: int | None = None
    platform: str | None = None
    dns_name: str = ""
    nics: list[NicInfo] = field(default_factory=list)
    disks: list[DiskInfo] = field(default_factory=list)
    comments: str = ""


@dataclass
class VNetInfo:
    one_id: int
    name: str
    network_address: str = ""
    network_mask: str = ""
    vlan_id: int | None = None
    mtu: int | None = None
    prefix_len: int = 32


@dataclass
class Inventory:
    zone_id: int
    zone_name: str
    cluster_id: int
    cluster_name: str
    hosts: list[HostInfo] = field(default_factory=list)
    vnets: dict[str, VNetInfo] = field(default_factory=dict)
    vms: list[VmInfo] = field(default_factory=list)
