"""SNMP enrichment helpers."""

from __future__ import annotations

import re

from netbox_opennebula_sync.config import DEFAULT_EXCLUDE_INTERFACES, SnmpConfig
from netbox_opennebula_sync.inventory import Inventory, NicInfo, VmInfo
from netbox_opennebula_sync.snmp import (
    _normalize_hostname,
    enrich_inventory,
    should_skip_interface,
)


def test_exclude_docker_interfaces():
    pat = re.compile(DEFAULT_EXCLUDE_INTERFACES, re.IGNORECASE)
    assert should_skip_interface("lo", pat)
    assert should_skip_interface("docker0", pat)
    assert should_skip_interface("br-abc123", pat)
    assert should_skip_interface("vethdeadbeef", pat)
    assert should_skip_interface("cni0", pat)
    assert not should_skip_interface("eth0", pat)
    assert not should_skip_interface("ens3", pat)


def test_normalize_hostname_with_suffix():
    label, dns = _normalize_hostname("belenios.europe", "europe")
    assert label == "belenios"
    assert dns == "belenios.europe"


def test_normalize_hostname_short():
    label, dns = _normalize_hostname("penpot", "europe")
    assert label == "penpot"
    assert dns == "penpot.europe"


def test_enrich_skips_placeholder(monkeypatch):
    inv = Inventory(
        zone_id=0,
        zone_name="z",
        cluster_id=0,
        cluster_name="c",
        vms=[
            VmInfo(
                one_id=1,
                name="openpencil",
                status="active",
                host_name="forum",
                vcpus=2,
                memory_mb=4096,
                dns_name="openpencil",
                nics=[NicInfo(name="eth0", network="LAN", ip="10.0.0.1", mac="aa:bb")],
            )
        ],
    )

    def fake_snmpget(ip, cfg, oid):
        if oid.endswith(".5.0"):
            return "demo.europe"
        return "Linux Ubuntu 26.04"

    monkeypatch.setattr("netbox_opennebula_sync.snmp._snmpget", fake_snmpget)
    monkeypatch.setattr("netbox_opennebula_sync.snmp.shutil.which", lambda _: "/usr/bin/snmpget")

    cfg = SnmpConfig(ignore_hostnames=["demo", "demo.europe", "localhost"])
    enrich_inventory(inv, cfg, dns_suffix="europe")
    assert inv.vms[0].name == "openpencil"
