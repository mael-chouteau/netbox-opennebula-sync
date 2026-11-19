"""Idempotent OpenNebula → NetBox reconciler."""

from __future__ import annotations

import logging
from typing import Any

from .config import AppConfig
from .models import Inventory, VmInfo
from .netbox import NetBoxClient, slugify
from .opennebula import OpenNebulaClient, slugify_vm_name
from .snmp import enrich_inventory

log = logging.getLogger(__name__)

CUSTOM_FIELDS = [
    {
        "name": "opennebula_zone_id",
        "label": "OpenNebula Zone ID",
        "type": "integer",
        "object_types": ["virtualization.clustergroup"],
        "description": "OpenNebula zone identifier",
        "filter_logic": "exact",
        "ui_visible": "always",
        "ui_editable": "yes",
    },
    {
        "name": "opennebula_cluster_id",
        "label": "OpenNebula Cluster ID",
        "type": "integer",
        "object_types": ["virtualization.cluster"],
        "description": "OpenNebula cluster identifier",
        "filter_logic": "exact",
        "ui_visible": "always",
        "ui_editable": "yes",
    },
    {
        "name": "opennebula_host_id",
        "label": "OpenNebula Host ID",
        "type": "integer",
        "object_types": ["dcim.device"],
        "description": "OpenNebula hypervisor host identifier",
        "filter_logic": "exact",
        "ui_visible": "always",
        "ui_editable": "yes",
        "unique": True,
    },
    {
        "name": "opennebula_vm_id",
        "label": "OpenNebula VM ID",
        "type": "integer",
        "object_types": ["virtualization.virtualmachine"],
        "description": "OpenNebula virtual machine identifier",
        "filter_logic": "exact",
        "ui_visible": "always",
        "ui_editable": "yes",
        "unique": True,
    },
    {
        "name": "opennebula_vm_uuid",
        "label": "OpenNebula VM UUID",
        "type": "text",
        "object_types": ["virtualization.virtualmachine"],
        "description": "Guest UUID from OpenNebula OS section",
        "filter_logic": "exact",
        "ui_visible": "always",
        "ui_editable": "yes",
    },
    {
        "name": "opennebula_template_id",
        "label": "OpenNebula Template ID",
        "type": "integer",
        "object_types": ["virtualization.virtualmachine"],
        "description": "Source OpenNebula template identifier",
        "filter_logic": "exact",
        "ui_visible": "always",
        "ui_editable": "yes",
    },
]


class Reconciler:
    def __init__(self, cfg: AppConfig, nb: NetBoxClient):
        self.cfg = cfg
        self.nb = nb
        self.tag_ids: list[int] = []
        self.site_id: int | None = None
        self.tenant_id: int | None = None
        self.cluster_id: int | None = None
        self.cluster_type_id: int | None = None
        self.cluster_group_id: int | None = None
        self.host_map: dict[str, int] = {}  # hostname lower -> device id
        self.vlan_map: dict[int, int] = {}  # vid -> vlan id
        self.role_id: int | None = None
        self.dtype_id: int | None = None

    def bootstrap(self) -> None:
        """Create schema objects required for sync (safe to re-run)."""
        self._ensure_tags()
        for field in CUSTOM_FIELDS:
            existing = self.nb.find_one(
                "api/extras/custom-fields/", {"name": field["name"]}
            )
            if existing:
                self.nb.stats["skipped"] += 1
                continue
            self.nb._write("POST", "custom-field", "api/extras/custom-fields/", field, None)

        ctype = self.nb.ensure(
            "cluster-type",
            "api/virtualization/cluster-types/",
            {"slug": "opennebula-kvm"},
            {
                "name": "OpenNebula KVM",
                "slug": "opennebula-kvm",
                "description": "OpenNebula KVM hypervisors",
            },
        )
        self.cluster_type_id = ctype["id"] if ctype else None
        log.info("Bootstrap complete")

    def sync(self, inventory: Inventory) -> None:
        self._ensure_tags()
        self._resolve_site_tenant()
        self._ensure_cluster(inventory)
        self._load_vlans()
        self._ensure_hosts(inventory)
        managed_vm_ids = self._sync_vms(inventory)
        self._handle_orphans(managed_vm_ids)

    def _ensure_tags(self) -> None:
        ids: list[int] = []
        for name in self.cfg.sync.tags:
            slug = slugify(name)
            obj = self.nb.ensure(
                "tag",
                "api/extras/tags/",
                {"slug": slug},
                {"name": name, "slug": slug, "color": "9e9e9e"},
            )
            if obj:
                ids.append(obj["id"])
        self.tag_ids = ids

    def _tag_payload(self) -> list[int]:
        return list(self.tag_ids)

    def _resolve_site_tenant(self) -> None:
        site = self.nb.find_one(
            "api/dcim/sites/", {"slug": slugify(self.cfg.netbox.site)}
        ) or self.nb.find_one("api/dcim/sites/", {"name": self.cfg.netbox.site})
        if not site:
            site = self.nb.ensure(
                "site",
                "api/dcim/sites/",
                {"slug": slugify(self.cfg.netbox.site)},
                {
                    "name": self.cfg.netbox.site,
                    "slug": slugify(self.cfg.netbox.site),
                    "status": "active",
                },
            )
        self.site_id = site["id"] if site else None
        if self.cfg.netbox.tenant:
            tenant = self.nb.find_one(
                "api/tenancy/tenants/", {"slug": slugify(self.cfg.netbox.tenant)}
            ) or self.nb.find_one(
                "api/tenancy/tenants/", {"name": self.cfg.netbox.tenant}
            )
            self.tenant_id = tenant["id"] if tenant else None

    def _ensure_cluster(self, inventory: Inventory) -> None:
        ctype = self.nb.find_one(
            "api/virtualization/cluster-types/", {"slug": "opennebula-kvm"}
        )
        if not ctype:
            self.bootstrap()
            ctype = self.nb.find_one(
                "api/virtualization/cluster-types/", {"slug": "opennebula-kvm"}
            )
        self.cluster_type_id = ctype["id"] if ctype else None

        group = self.nb.ensure(
            "cluster-group",
            "api/virtualization/cluster-groups/",
            {"slug": slugify(inventory.zone_name)},
            {
                "name": inventory.zone_name,
                "slug": slugify(inventory.zone_name),
                "description": f"OpenNebula zone {inventory.zone_id}",
                "custom_fields": {"opennebula_zone_id": inventory.zone_id},
            },
            update_fields=["custom_fields", "description"],
        )
        self.cluster_group_id = group["id"] if group else None

        cluster_name = self.cfg.netbox.cluster_name or f"OpenNebula {inventory.cluster_name}"
        payload: dict[str, Any] = {
            "name": cluster_name,
            "type": self.cluster_type_id,
            "group": self.cluster_group_id,
            "status": "active",
            "scope_type": "dcim.site",
            "scope_id": self.site_id,
            "tags": self._tag_payload(),
            "custom_fields": {"opennebula_cluster_id": inventory.cluster_id},
        }
        if self.tenant_id:
            payload["tenant"] = self.tenant_id
        cluster = self.nb.ensure(
            "cluster",
            "api/virtualization/clusters/",
            {"name": cluster_name},
            payload,
            update_fields=[
                "type",
                "group",
                "scope_type",
                "scope_id",
                "tags",
                "custom_fields",
                "status",
            ],
        )
        self.cluster_id = cluster["id"] if cluster else None

    def _load_vlans(self) -> None:
        if not self.site_id:
            return
        for vlan in self.nb.list_all("api/ipam/vlans/", {"site_id": self.site_id}):
            vid = vlan.get("vid")
            if vid is not None:
                self.vlan_map[int(vid)] = vlan["id"]

    def _ensure_host_role_type(self) -> None:
        role = self.nb.ensure(
            "device-role",
            "api/dcim/device-roles/",
            {"slug": slugify(self.cfg.netbox.host_device_role)},
            {
                "name": self.cfg.netbox.host_device_role,
                "slug": slugify(self.cfg.netbox.host_device_role),
                "color": "2196f3",
                "vm_role": False,
            },
        )
        self.role_id = role["id"] if role else None
        manuf = self.nb.ensure(
            "manufacturer",
            "api/dcim/manufacturers/",
            {"slug": slugify(self.cfg.netbox.host_manufacturer)},
            {
                "name": self.cfg.netbox.host_manufacturer,
                "slug": slugify(self.cfg.netbox.host_manufacturer),
            },
        )
        manuf_id = manuf["id"] if manuf else None
        dtype = self.nb.ensure(
            "device-type",
            "api/dcim/device-types/",
            {
                "slug": slugify(
                    f"{self.cfg.netbox.host_manufacturer}-{self.cfg.netbox.host_device_type}"
                )
            },
            {
                "manufacturer": manuf_id,
                "model": self.cfg.netbox.host_device_type,
                "slug": slugify(
                    f"{self.cfg.netbox.host_manufacturer}-{self.cfg.netbox.host_device_type}"
                ),
                "u_height": 1,
            },
        )
        self.dtype_id = dtype["id"] if dtype else None

    def _ensure_hosts(self, inventory: Inventory) -> None:
        self._ensure_host_role_type()
        # Prefill from existing devices on site
        for dev in self.nb.list_all("api/dcim/devices/", {"site_id": self.site_id}):
            self.host_map[dev["name"].lower()] = dev["id"]

        for host in inventory.hosts:
            existing_id = self.host_map.get(host.name.lower())
            if existing_id:
                payload = {
                    "cluster": self.cluster_id,
                    "status": host.status,
                    "tags": self._tag_payload(),
                    "custom_fields": {"opennebula_host_id": host.one_id},
                }
                self.nb._write(
                    "PATCH",
                    "device",
                    f"api/dcim/devices/{existing_id}/",
                    payload,
                    {"id": existing_id, "name": host.name},
                )
                continue
            if not self.cfg.netbox.create_missing_hosts:
                log.warning("host %s missing in NetBox and create_missing_hosts=false", host.name)
                continue
            created = self.nb.ensure(
                "device",
                "api/dcim/devices/",
                {"name": host.name, "site_id": self.site_id},
                {
                    "name": host.name,
                    "device_type": self.dtype_id,
                    "role": self.role_id,
                    "site": self.site_id,
                    "cluster": self.cluster_id,
                    "status": host.status,
                    "tags": self._tag_payload(),
                    "custom_fields": {"opennebula_host_id": host.one_id},
                    "tenant": self.tenant_id,
                },
            )
            if created:
                self.host_map[host.name.lower()] = created["id"]

    def _platform_id(self, name: str | None) -> int | None:
        if not name:
            return None
        obj = self.nb.ensure(
            "platform",
            "api/dcim/platforms/",
            {"slug": slugify(name)},
            {"name": name, "slug": slugify(name)},
        )
        return obj["id"] if obj else None

    def _find_vm_by_one_id(self, one_id: int) -> dict[str, Any] | None:
        # NetBox custom field filter: cf_opennebula_vm_id
        return self.nb.find_one(
            "api/virtualization/virtual-machines/",
            {"cf_opennebula_vm_id": one_id},
        )

    def _sync_vms(self, inventory: Inventory) -> set[int]:
        managed: set[int] = set()
        for vm in inventory.vms:
            nb_vm = self._upsert_vm(vm)
            if not nb_vm:
                continue
            managed.add(nb_vm["id"])
            self._sync_vm_interfaces(nb_vm, vm)
        return managed

    def _upsert_vm(self, vm: VmInfo) -> dict[str, Any] | None:
        name = slugify_vm_name(vm.name)
        if self.cfg.netbox.dns_suffix and not vm.dns_name.endswith(
            "." + self.cfg.netbox.dns_suffix
        ):
            if "." not in vm.dns_name:
                vm.dns_name = f"{vm.dns_name}.{self.cfg.netbox.dns_suffix}"

        device_id = None
        if vm.host_name:
            device_id = self.host_map.get(vm.host_name.lower())

        payload: dict[str, Any] = {
            "name": name[:64],
            "status": vm.status,
            "cluster": self.cluster_id,
            "site": self.site_id,
            "vcpus": vm.vcpus,
            "memory": vm.memory_mb,
            # NetBox VM.disk and VirtualDisk.size are both in MB
            "disk": max(1, sum(d.size_mb for d in vm.disks)) if vm.disks else None,
            "platform": self._platform_id(vm.platform),
            "device": device_id,
            "tags": self._tag_payload(),
            "comments": vm.comments,
            "custom_fields": {
                "opennebula_vm_id": vm.one_id,
                "opennebula_vm_uuid": vm.uuid or None,
                "opennebula_template_id": vm.template_id,
            },
        }
        if self.tenant_id:
            payload["tenant"] = self.tenant_id
        # drop null disk
        if payload["disk"] is None:
            del payload["disk"]

        existing = self._find_vm_by_one_id(vm.one_id)
        if existing:
            return self.nb._write(
                "PATCH",
                "virtual-machine",
                f"api/virtualization/virtual-machines/{existing['id']}/",
                payload,
                existing,
            )
        # Fallback by name to avoid duplicates during first migration
        name_lookup: dict[str, Any] = {"name": name}
        # Skip cluster filter in dry-run (cluster id is synthetic)
        if self.cluster_id and not self.nb.dry_run:
            name_lookup["cluster_id"] = self.cluster_id
        by_name = self.nb.find_one(
            "api/virtualization/virtual-machines/",
            name_lookup,
        )
        if by_name:
            return self.nb._write(
                "PATCH",
                "virtual-machine",
                f"api/virtualization/virtual-machines/{by_name['id']}/",
                payload,
                by_name,
            )
        return self.nb._write(
            "POST",
            "virtual-machine",
            "api/virtualization/virtual-machines/",
            payload,
            None,
        )

    def _sync_vm_interfaces(self, nb_vm: dict[str, Any], vm: VmInfo) -> None:
        vm_id = nb_vm["id"]
        # Dry-run stubs are not queryable via NetBox filters
        if self.nb.dry_run:
            for idx, nic in enumerate(vm.nics):
                ifname = nic.name or f"eth{idx}"
                self.nb._write(
                    "POST",
                    "vminterface",
                    "api/virtualization/interfaces/",
                    {"name": ifname, "virtual_machine": vm_id},
                    None,
                )
                if nic.mac:
                    self.nb._write(
                        "POST",
                        "mac-address",
                        "api/dcim/mac-addresses/",
                        {"mac_address": nic.mac},
                        None,
                    )
                if nic.ip:
                    self.nb._write(
                        "POST",
                        "ip-address",
                        "api/ipam/ip-addresses/",
                        {"address": f"{nic.ip}/{nic.prefix_len}"},
                        None,
                    )
            for disk in vm.disks:
                self.nb._write(
                    "POST",
                    "virtual-disk",
                    "api/virtualization/virtual-disks/",
                    {"name": disk.name or "disk", "size": disk.size_mb},
                    None,
                )
            return

        existing_ifaces = {
            i["name"]: i
            for i in self.nb.list_all(
                "api/virtualization/interfaces/", {"virtual_machine_id": vm_id}
            )
        }
        primary_ip_id = None
        for idx, nic in enumerate(vm.nics):
            ifname = nic.name or f"eth{idx}"
            vlan_id = self.vlan_map.get(nic.vlan_id) if nic.vlan_id else None
            iface_payload: dict[str, Any] = {
                "virtual_machine": vm_id,
                "name": ifname,
                "enabled": True,
                "mtu": nic.mtu,
                "description": nic.network or "",
                "tags": self._tag_payload(),
            }
            if vlan_id:
                iface_payload["untagged_vlan"] = vlan_id
            if iface_payload["mtu"] is None:
                del iface_payload["mtu"]

            iface = existing_ifaces.get(ifname)
            if iface:
                iface = self.nb._write(
                    "PATCH",
                    "vminterface",
                    f"api/virtualization/interfaces/{iface['id']}/",
                    iface_payload,
                    iface,
                ) or iface
            else:
                iface = self.nb._write(
                    "POST",
                    "vminterface",
                    "api/virtualization/interfaces/",
                    iface_payload,
                    None,
                )
            if not iface:
                continue

            if nic.mac:
                self._ensure_mac(iface, nic.mac)

            if nic.ip:
                ip_obj = self._ensure_ip(vm, iface, nic)
                if ip_obj and primary_ip_id is None and ":" not in nic.ip:
                    primary_ip_id = ip_obj["id"]

        existing_disks = {
            d["name"]: d
            for d in self.nb.list_all(
                "api/virtualization/virtual-disks/", {"virtual_machine_id": vm_id}
            )
        }
        for disk in vm.disks:
            dname = disk.name or "disk"
            payload = {
                "virtual_machine": vm_id,
                "name": dname,
                "size": max(1, disk.size_mb),
                "description": disk.image[:200] if disk.image else "",
                "tags": self._tag_payload(),
            }
            existing = existing_disks.get(dname)
            if existing:
                self.nb._write(
                    "PATCH",
                    "virtual-disk",
                    f"api/virtualization/virtual-disks/{existing['id']}/",
                    payload,
                    existing,
                )
            else:
                self.nb._write(
                    "POST",
                    "virtual-disk",
                    "api/virtualization/virtual-disks/",
                    payload,
                    None,
                )

        if primary_ip_id:
            self.nb._write(
                "PATCH",
                "virtual-machine",
                f"api/virtualization/virtual-machines/{vm_id}/",
                {"primary_ip4": primary_ip_id},
                nb_vm,
            )

    def _ensure_mac(self, iface: dict[str, Any], mac: str) -> None:
        mac = mac.lower()
        existing = self.nb.find_one("api/dcim/mac-addresses/", {"mac_address": mac})
        payload = {
            "mac_address": mac,
            "assigned_object_type": "virtualization.vminterface",
            "assigned_object_id": iface["id"],
            "description": "opennebula-managed",
        }
        if existing:
            mac_obj = self.nb._write(
                "PATCH",
                "mac-address",
                f"api/dcim/mac-addresses/{existing['id']}/",
                payload,
                existing,
            )
        else:
            mac_obj = self.nb._write(
                "POST",
                "mac-address",
                "api/dcim/mac-addresses/",
                payload,
                None,
            )
        mac_id = (mac_obj or existing or {}).get("id")
        if mac_id and iface.get("primary_mac_address") != mac_id:
            # NetBox may expect nested or id
            current = iface.get("primary_mac_address")
            current_id = current.get("id") if isinstance(current, dict) else current
            if current_id != mac_id:
                self.nb._write(
                    "PATCH",
                    "vminterface",
                    f"api/virtualization/interfaces/{iface['id']}/",
                    {"primary_mac_address": mac_id},
                    iface,
                )

    def _ensure_ip(self, vm: VmInfo, iface: dict[str, Any], nic: Any) -> dict[str, Any] | None:
        address = f"{nic.ip}/{nic.prefix_len}"
        existing = self.nb.find_one("api/ipam/ip-addresses/", {"address": nic.ip})
        dns = vm.dns_name
        if self.cfg.netbox.dns_suffix and dns and "." not in dns:
            dns = f"{dns}.{self.cfg.netbox.dns_suffix}"
        payload: dict[str, Any] = {
            "address": address,
            "status": "active",
            "dns_name": dns or "",
            "description": f"{vm.name} {nic.network}".strip()[:200],
            "assigned_object_type": "virtualization.vminterface",
            "assigned_object_id": iface["id"],
            "tags": self._tag_payload(),
        }
        if self.tenant_id:
            payload["tenant"] = self.tenant_id
        if existing:
            return self.nb._write(
                "PATCH",
                "ip-address",
                f"api/ipam/ip-addresses/{existing['id']}/",
                payload,
                existing,
            )
        return self.nb._write(
            "POST",
            "ip-address",
            "api/ipam/ip-addresses/",
            payload,
            None,
        )

    def _handle_orphans(self, managed_ids: set[int]) -> None:
        policy = self.cfg.sync.orphan_policy
        if policy == "ignore":
            return
        if not self.cluster_id or self.nb.dry_run:
            return
        for vm in self.nb.list_all(
            "api/virtualization/virtual-machines/",
            {"cluster_id": self.cluster_id, "tag": "opennebula"},
        ):
            if vm["id"] in managed_ids:
                continue
            if policy == "mark_offline":
                if vm.get("status", {}).get("value") != "offline":
                    self.nb._write(
                        "PATCH",
                        "virtual-machine",
                        f"api/virtualization/virtual-machines/{vm['id']}/",
                        {"status": "offline"},
                        vm,
                    )
            elif policy == "delete":
                self.nb.delete("api/virtualization/virtual-machines/", vm["id"])


def run_bootstrap(cfg: AppConfig) -> int:
    with NetBoxClient(cfg.netbox, dry_run=cfg.sync.dry_run) as nb:
        nb.ping()
        Reconciler(cfg, nb).bootstrap()
        log.info("stats=%s", nb.stats)
        return 1 if nb.stats["errors"] else 0


def run_sync(cfg: AppConfig) -> int:
    with NetBoxClient(cfg.netbox, dry_run=cfg.sync.dry_run) as nb:
        status = nb.ping()
        log.info(
            "NetBox %s dry_run=%s",
            status.get("netbox-version"),
            cfg.sync.dry_run,
        )
        one = OpenNebulaClient(cfg.opennebula, proxy=cfg.netbox.socks_proxy)
        try:
            inventory = one.collect()
            enrich_inventory(inventory, cfg.snmp, cfg.netbox.dns_suffix)
            # Apply DNS suffix defaults for VMs without SNMP
            for vm in inventory.vms:
                if cfg.netbox.dns_suffix and "." not in vm.dns_name:
                    vm.dns_name = f"{slugify_vm_name(vm.name)}.{cfg.netbox.dns_suffix}"
                elif not vm.dns_name:
                    vm.dns_name = slugify_vm_name(vm.name)
            rec = Reconciler(cfg, nb)
            rec.bootstrap()
            rec.sync(inventory)
            log.info("stats=%s", nb.stats)
            return 1 if nb.stats["errors"] else 0
        finally:
            one.close()
