"""OpenNebula XML-RPC inventory collector."""

from __future__ import annotations

import ipaddress
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any
from xml.sax.saxutils import escape
from xmlrpc.client import ServerProxy, Transport

import httpx

from .config import OpenNebulaConfig
from .models import DiskInfo, HostInfo, Inventory, NicInfo, VmInfo, VNetInfo

log = logging.getLogger(__name__)

# Host states: 0 init, 1 monitor_init, 2 on, 3 error, 4 disabled, 5 monitor_error
HOST_ACTIVE_STATES = {0, 1, 2}
# VM states: 3 ACTIVE, 8 POWEROFF, 9 UNDEPLOYED, 4 STOPPED, 5 SUSPENDED, 6 DONE, ...
VM_STATE_MAP = {
    3: "active",
    5: "staged",  # suspended
    4: "offline",
    8: "offline",
    9: "offline",
}


def _text(el: ET.Element | None, path: str, default: str = "") -> str:
    if el is None:
        return default
    found = el.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def _int(el: ET.Element | None, path: str, default: int = 0) -> int:
    raw = _text(el, path)
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def mask_to_prefixlen(mask: str) -> int:
    if not mask:
        return 32
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except ValueError:
        return 32


def slugify_vm_name(name: str) -> str:
    """Normalize OpenNebula VM names for NetBox / DNS labels."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    return cleaned.lower() or "vm"


def guess_platform(image: str, sysdescr: str = "") -> str | None:
    blob = f"{image} {sysdescr}".lower()
    for needle, platform in (
        ("ubuntu 26.04", "Ubuntu 26.04"),
        ("ubuntu 24.04", "Ubuntu 24.04"),
        ("ubuntu 22.04", "Ubuntu 22.04"),
        ("ubuntu 20.04", "Ubuntu 20.04"),
        ("debian 13", "Debian 13"),
        ("debian 12", "Debian 12"),
        ("centos", "CentOS"),
        ("rocky", "Rocky Linux"),
        ("alma", "AlmaLinux"),
    ):
        if needle in blob:
            return platform
    if "ubuntu" in blob:
        return "Ubuntu"
    if "linux" in blob:
        return "Linux"
    return None


class _TimeoutTransport(Transport):
    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host: Any) -> Any:
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


def _rpc_value_xml(value: Any) -> str:
    if isinstance(value, bool):
        return f"<value><boolean>{1 if value else 0}</boolean></value>"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"<value><i4>{value}</i4></value>"
    if isinstance(value, float):
        return f"<value><double>{value}</double></value>"
    return f"<value><string>{escape(str(value))}</string></value>"


def _parse_rpc_value(el: ET.Element) -> Any:
    child = next(iter(el), None)
    if child is None:
        return (el.text or "").strip()
    tag = child.tag.lower()
    text = (child.text or "").strip()
    if tag == "boolean":
        return text in {"1", "true"}
    if tag in {"i4", "int"}:
        return int(text)
    if tag == "i8":
        return int(text)
    if tag == "double":
        return float(text)
    if tag == "string":
        return text
    if tag == "array":
        data = child.find("data")
        if data is None:
            return []
        return [_parse_rpc_value(v) for v in data.findall("value")]
    if tag == "struct":
        out: dict[str, Any] = {}
        for member in child.findall("member"):
            name = (member.findtext("name") or "").strip()
            val = member.find("value")
            out[name] = _parse_rpc_value(val) if val is not None else None
        return out
    return text


class OpenNebulaClient:
    def __init__(self, cfg: OpenNebulaConfig, proxy: str | None = None):
        self.cfg = cfg
        self.proxy = proxy
        self._http: httpx.Client | None = None
        self.proxy_rpc = bool(proxy)
        if not self.proxy_rpc:
            transport = _TimeoutTransport(cfg.timeout)
            self.proxy_rpc_client = ServerProxy(
                cfg.endpoint, allow_none=True, transport=transport
            )
        else:
            self._http = httpx.Client(
                proxy=proxy,
                timeout=cfg.timeout,
                follow_redirects=True,
            )

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    def _call(self, method: str, *args: Any) -> str:
        if self.proxy_rpc:
            return self._call_httpx(method, *args)
        fn = getattr(self.proxy_rpc_client, method)
        result = fn(self.cfg.credentials, *args)
        if not isinstance(result, (list, tuple)) or len(result) < 2:
            raise RuntimeError(f"{method}: unexpected response {result!r}")
        ok, payload = result[0], result[1]
        if not ok:
            raise RuntimeError(f"{method}: {payload}")
        return str(payload)

    def _call_httpx(self, method: str, *args: Any) -> str:
        assert self._http is not None
        params = [_rpc_value_xml(self.cfg.credentials), *(_rpc_value_xml(a) for a in args)]
        body = (
            '<?xml version="1.0"?>'
            f"<methodCall><methodName>{escape(method)}</methodName><params>"
            + "".join(f"<param>{p}</param>" for p in params)
            + "</params></methodCall>"
        )
        resp = self._http.post(
            self.cfg.endpoint,
            content=body.encode("utf-8"),
            headers={"Content-Type": "text/xml"},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"{method}: HTTP {resp.status_code}: {resp.text[:300]}")
        root = ET.fromstring(resp.text)
        fault = root.find("fault")
        if fault is not None:
            raise RuntimeError(f"{method}: XML-RPC fault: {resp.text[:300]}")
        value = root.find("./params/param/value")
        if value is None:
            raise RuntimeError(f"{method}: empty XML-RPC response")
        parsed = _parse_rpc_value(value)
        if not isinstance(parsed, list) or len(parsed) < 2:
            raise RuntimeError(f"{method}: unexpected response {parsed!r}")
        ok, payload = parsed[0], parsed[1]
        if not ok:
            raise RuntimeError(f"{method}: {payload}")
        return str(payload)

    def collect(self) -> Inventory:
        zone_xml = self._call("one.zonepool.info")
        cluster_xml = self._call("one.clusterpool.info")
        host_xml = self._call("one.hostpool.info")
        vn_xml = self._call("one.vnpool.info", -2, -1, -1)
        vm_xml = self._call("one.vmpool.info", -2, -1, -1, -1)

        zones = ET.fromstring(zone_xml).findall("ZONE")
        if not zones:
            raise RuntimeError("no OpenNebula zone found")
        zone = zones[0]
        zone_id = _int(zone, "ID")
        zone_name = _text(zone, "NAME", "OpenNebula")

        clusters = ET.fromstring(cluster_xml).findall("CLUSTER")
        if not clusters:
            raise RuntimeError("no OpenNebula cluster found")
        cluster = clusters[0]
        cluster_id = _int(cluster, "ID")
        cluster_name = _text(cluster, "NAME", "default")

        vnets: dict[str, VNetInfo] = {}
        for vn in ET.fromstring(vn_xml).findall("VNET"):
            name = _text(vn, "NAME")
            mask = _text(vn, "TEMPLATE/NETWORK_MASK")
            vlan_raw = _text(vn, "VLAN_ID") or _text(vn, "TEMPLATE/VLAN_ID")
            mtu_raw = _text(vn, "TEMPLATE/GUEST_MTU") or _text(vn, "TEMPLATE/MTU")
            info = VNetInfo(
                one_id=_int(vn, "ID"),
                name=name,
                network_address=_text(vn, "TEMPLATE/NETWORK_ADDRESS"),
                network_mask=mask,
                vlan_id=int(vlan_raw) if vlan_raw.isdigit() else None,
                mtu=int(mtu_raw) if mtu_raw.isdigit() else None,
                prefix_len=mask_to_prefixlen(mask),
            )
            vnets[name] = info

        hosts: list[HostInfo] = []
        for host in ET.fromstring(host_xml).findall("HOST"):
            state = _int(host, "STATE")
            hosts.append(
                HostInfo(
                    one_id=_int(host, "ID"),
                    name=_text(host, "NAME"),
                    state=state,
                    status="active" if state in HOST_ACTIVE_STATES else "offline",
                )
            )

        vms: list[VmInfo] = []
        for vm in ET.fromstring(vm_xml).findall("VM"):
            state = _int(vm, "STATE")
            status = VM_STATE_MAP.get(state, "offline")
            if state == 3 and _int(vm, "LCM_STATE") not in {3, 0}:
                status = "active"

            history = vm.findall("HISTORY_RECORDS/HISTORY")
            host_name = None
            if history:
                host_name = _text(history[-1], "HOSTNAME") or None

            tpl = vm.find("TEMPLATE")
            nics: list[NicInfo] = []
            for idx, nic in enumerate(tpl.findall("NIC") if tpl is not None else []):
                net = _text(nic, "NETWORK")
                vnet = vnets.get(net)
                vlan_raw = _text(nic, "VLAN_ID")
                nics.append(
                    NicInfo(
                        name=_text(nic, "NAME") or f"eth{idx}",
                        network=net,
                        ip=_text(nic, "IP"),
                        mac=_text(nic, "MAC").lower(),
                        vlan_id=(
                            int(vlan_raw)
                            if vlan_raw.isdigit()
                            else (vnet.vlan_id if vnet else None)
                        ),
                        mtu=vnet.mtu if vnet else None,
                        prefix_len=vnet.prefix_len if vnet else 32,
                    )
                )

            disks: list[DiskInfo] = []
            for disk in tpl.findall("DISK") if tpl is not None else []:
                size = _int(disk, "SIZE")  # MB in OpenNebula
                target = _text(disk, "TARGET") or _text(disk, "DISK_ID") or "disk"
                disks.append(
                    DiskInfo(
                        name=target,
                        size_mb=size,
                        image=_text(disk, "IMAGE"),
                        target=target,
                    )
                )

            image_hint = disks[0].image if disks else ""
            os_uuid = _text(tpl, "OS/UUID") if tpl is not None else ""
            template_id = _int(tpl, "TEMPLATE_ID") if tpl is not None else 0
            name = _text(vm, "NAME")
            vms.append(
                VmInfo(
                    one_id=_int(vm, "ID"),
                    name=name,
                    status=status,
                    host_name=host_name,
                    vcpus=_int(tpl, "VCPU") or max(1, int(float(_text(tpl, "CPU") or "1"))),
                    memory_mb=_int(tpl, "MEMORY"),
                    uuid=os_uuid,
                    template_id=template_id or None,
                    platform=guess_platform(image_hint),
                    dns_name=slugify_vm_name(name),
                    nics=nics,
                    disks=disks,
                    comments=f"OpenNebula VM ID {_int(vm, 'ID')}",
                )
            )

        log.info(
            "OpenNebula inventory: zone=%s cluster=%s hosts=%d vnets=%d vms=%d",
            zone_name,
            cluster_name,
            len(hosts),
            len(vnets),
            len(vms),
        )
        return Inventory(
            zone_id=zone_id,
            zone_name=zone_name,
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            hosts=hosts,
            vnets=vnets,
            vms=vms,
        )
