"""In-process NetBox writes via Django ORM (plugin / manage.py path)."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .netbox import _needs_update, slugify

log = logging.getLogger(__name__)


def _norm_path(path: str) -> tuple[str, int | None]:
    path = path.strip("/")
    if path.startswith("api/"):
        path = path[4:]
    parts = [p for p in path.strip("/").split("/") if p]
    if parts and parts[-1].isdigit():
        return "/".join(parts[:-1]), int(parts[-1])
    return "/".join(parts), None


def _status_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"value": str(value)}


def _serialize(obj: Any) -> dict[str, Any]:
    """API-ish dict so Reconciler can keep using ``obj['id']`` etc."""
    data: dict[str, Any] = {"id": obj.pk}
    for attr in ("name", "slug", "vid", "mac_address", "address", "description"):
        if hasattr(obj, attr):
            val = getattr(obj, attr)
            if val is not None:
                data[attr] = str(val) if attr == "address" else val
    if hasattr(obj, "status"):
        data["status"] = _status_dict(obj.status)
    if hasattr(obj, "primary_mac_address_id"):
        data["primary_mac_address"] = obj.primary_mac_address_id
    if hasattr(obj, "custom_field_data") and obj.custom_field_data is not None:
        data["custom_fields"] = dict(obj.custom_field_data)
    if hasattr(obj, "tags"):
        data["tags"] = list(obj.tags.values_list("id", flat=True))
    # Nested FK ids commonly compared by _needs_update
    for fk in (
        "type_id",
        "group_id",
        "site_id",
        "cluster_id",
        "tenant_id",
        "role_id",
        "device_type_id",
        "platform_id",
        "device_id",
        "virtual_machine_id",
        "untagged_vlan_id",
        "primary_ip4_id",
        "manufacturer_id",
        "scope_id",
    ):
        if hasattr(obj, fk):
            short = fk[: -len("_id")] if fk.endswith("_id") else fk
            # API uses "type", "group", "site", ...
            data[short] = getattr(obj, fk)
    if hasattr(obj, "scope_type_id") and obj.scope_type_id:
        ct = obj.scope_type
        data["scope_type"] = f"{ct.app_label}.{ct.model}"
    return data


class DjangoStore:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
        self._models = self._build_model_map()

    def close(self) -> None:
        return None

    def __enter__(self) -> DjangoStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _build_model_map(self) -> dict[str, Any]:
        from dcim.models import (
            Device,
            DeviceRole,
            DeviceType,
            MACAddress,
            Manufacturer,
            Platform,
            Site,
        )
        from extras.models import CustomField, Tag
        from ipam.models import VLAN, IPAddress
        from tenancy.models import Tenant
        from virtualization.models import (
            Cluster,
            ClusterGroup,
            ClusterType,
            VirtualDisk,
            VirtualMachine,
            VMInterface,
        )

        return {
            "extras/tags": Tag,
            "extras/custom-fields": CustomField,
            "virtualization/cluster-types": ClusterType,
            "virtualization/cluster-groups": ClusterGroup,
            "virtualization/clusters": Cluster,
            "virtualization/virtual-machines": VirtualMachine,
            "virtualization/interfaces": VMInterface,
            "virtualization/virtual-disks": VirtualDisk,
            "dcim/sites": Site,
            "dcim/device-roles": DeviceRole,
            "dcim/manufacturers": Manufacturer,
            "dcim/device-types": DeviceType,
            "dcim/devices": Device,
            "dcim/platforms": Platform,
            "dcim/mac-addresses": MACAddress,
            "ipam/vlans": VLAN,
            "ipam/ip-addresses": IPAddress,
            "tenancy/tenants": Tenant,
        }

    def ping(self) -> dict[str, Any]:
        from django.conf import settings

        return {"netbox-version": getattr(settings, "VERSION", "orm")}

    def find_one(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        key, _ = _norm_path(path)
        model = self._models.get(key)
        if model is None:
            log.error("DjangoStore: unknown path %s", path)
            self.stats["errors"] += 1
            return None
        qs = self._filter(model, key, params)
        obj = qs.first()
        return _serialize(obj) if obj else None

    def list_all(
        self, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        key, _ = _norm_path(path)
        model = self._models.get(key)
        if model is None:
            log.error("DjangoStore: unknown path %s", path)
            self.stats["errors"] += 1
            return []
        qs = self._filter(model, key, params or {})
        return [_serialize(obj) for obj in qs.iterator()]

    def _filter(self, model: Any, key: str, params: dict[str, Any]) -> Any:
        qs = model.objects.all()
        for k, v in params.items():
            if k == "limit" or v is None:
                continue
            if k.startswith("cf_"):
                qs = qs.filter(**{f"custom_field_data__{k[3:]}": v})
            elif k == "tag":
                qs = qs.filter(tags__slug=v)
            elif k == "site_id":
                if key == "virtualization/clusters":
                    from dcim.models import Site

                    ct = ContentType.objects.get_for_model(Site)
                    qs = qs.filter(scope_type=ct, scope_id=v)
                else:
                    qs = qs.filter(site_id=v)
            elif k == "cluster_id":
                qs = qs.filter(cluster_id=v)
            elif k == "virtual_machine_id":
                qs = qs.filter(virtual_machine_id=v)
            elif k == "address":
                # django-netfields IPNetworkField: use net_host (not host/startswith)
                host = str(v).split("/")[0]
                qs = qs.filter(address__net_host=host)
            elif k.endswith("_id") and hasattr(model, k):
                qs = qs.filter(**{k: v})
            elif hasattr(model, k):
                qs = qs.filter(**{k: v})
            else:
                log.debug("DjangoStore: ignore filter %s=%s on %s", k, v, key)
        return qs.distinct()

    def ensure(
        self,
        kind: str,
        path: str,
        lookup: dict[str, Any],
        payload: dict[str, Any],
        update_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        existing = self.find_one(path, lookup)
        if existing:
            if update_fields:
                patch = {
                    k: payload[k]
                    for k in update_fields
                    if k in payload and _needs_update(existing.get(k), payload[k])
                }
                if patch:
                    return self._write(
                        "PATCH", kind, f"{path}{existing['id']}/", patch, existing
                    )
            self.stats["skipped"] += 1
            log.debug("skip %s %s id=%s", kind, lookup, existing.get("id"))
            return existing
        return self._write("POST", kind, path, payload, None)

    def _write(
        self,
        method: str,
        kind: str,
        path: str,
        payload: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        label = (
            payload.get("name")
            or payload.get("address")
            or payload.get("slug")
            or payload.get("mac_address")
            or path
        )
        if self.dry_run:
            action = "update" if existing else "create"
            log.info("[dry-run] %s %s %s", action, kind, label)
            if existing:
                self.stats["updated"] += 1
                return existing
            self.stats["created"] += 1
            stub = dict(payload)
            stub.setdefault("id", -abs(hash((kind, str(label)))) % 10_000_000 or 1)
            stub.setdefault("name", label)
            return stub

        key, obj_id = _norm_path(path)
        if method == "PATCH" and obj_id is None and existing:
            obj_id = existing["id"]
        model = self._models.get(key)
        if model is None:
            self.stats["errors"] += 1
            log.error("DjangoStore: unknown path for write %s", path)
            return existing

        try:
            with transaction.atomic():
                if key == "extras/custom-fields" and method == "POST":
                    obj = self._create_custom_field(payload)
                elif method == "POST":
                    obj = model()
                    self._apply(obj, payload, create=True)
                    obj.save()
                    self._apply_m2m(obj, payload)
                else:
                    obj = model.objects.get(pk=obj_id)
                    self._apply(obj, payload, create=False)
                    obj.save()
                    self._apply_m2m(obj, payload)
        except Exception as exc:
            self.stats["errors"] += 1
            log.error("%s %s %s failed: %s", method, kind, label, exc)
            return existing

        if existing:
            self.stats["updated"] += 1
            log.info("updated %s %s id=%s", kind, label, obj.pk)
        else:
            self.stats["created"] += 1
            log.info("created %s %s id=%s", kind, label, obj.pk)
        return _serialize(obj)

    def delete(self, path: str, obj_id: int) -> bool:
        if self.dry_run:
            log.info("[dry-run] delete %s%s", path, obj_id)
            return True
        key, _ = _norm_path(path)
        model = self._models.get(key)
        if model is None:
            return False
        try:
            model.objects.filter(pk=obj_id).delete()
            return True
        except Exception as exc:
            log.error("DELETE %s%s failed: %s", path, obj_id, exc)
            return False

    def _create_custom_field(self, payload: dict[str, Any]) -> Any:
        from extras.models import CustomField

        object_types = list(payload.get("object_types") or [])
        cf = CustomField(
            name=payload["name"],
            label=payload.get("label") or payload["name"],
            type=payload.get("type") or "text",
            description=payload.get("description") or "",
            filter_logic=payload.get("filter_logic") or "exact",
            ui_visible=payload.get("ui_visible") or "always",
            ui_editable=payload.get("ui_editable") or "yes",
            unique=bool(payload.get("unique", False)),
        )
        cf.save()
        cts = []
        for ot in object_types:
            app_label, model_name = ot.split(".", 1)
            cts.append(ContentType.objects.get(app_label=app_label, model=model_name))
        if cts:
            cf.object_types.set(cts)
        return cf

    def _apply(self, obj: Any, payload: dict[str, Any], *, create: bool) -> None:
        data = dict(payload)
        custom_fields = data.pop("custom_fields", None)
        data.pop("tags", None)  # applied after save
        data.pop("object_types", None)

        scope_type = data.pop("scope_type", None)
        scope_id = data.pop("scope_id", None)
        assigned_ot = data.pop("assigned_object_type", None)
        assigned_oid = data.pop("assigned_object_id", None)

        fk_map = {
            "type": "type_id",
            "group": "group_id",
            "site": "site_id",
            "cluster": "cluster_id",
            "tenant": "tenant_id",
            "role": "role_id",
            "device_type": "device_type_id",
            "manufacturer": "manufacturer_id",
            "platform": "platform_id",
            "device": "device_id",
            "virtual_machine": "virtual_machine_id",
            "untagged_vlan": "untagged_vlan_id",
            "primary_ip4": "primary_ip4_id",
            "primary_mac_address": "primary_mac_address_id",
        }
        for api_name, orm_name in fk_map.items():
            if api_name in data:
                val = data.pop(api_name)
                if hasattr(obj, orm_name):
                    setattr(obj, orm_name, val)

        if scope_type is not None and scope_id is not None:
            app_label, model_name = str(scope_type).split(".", 1)
            obj.scope_type = ContentType.objects.get(
                app_label=app_label, model=model_name
            )
            obj.scope_id = scope_id

        if assigned_ot is not None and assigned_oid is not None:
            app_label, model_name = str(assigned_ot).split(".", 1)
            obj.assigned_object_type = ContentType.objects.get(
                app_label=app_label, model=model_name
            )
            obj.assigned_object_id = assigned_oid

        for key, value in data.items():
            if key == "id":
                continue
            if hasattr(obj, key):
                setattr(obj, key, value)

        if custom_fields is not None and hasattr(obj, "custom_field_data"):
            merged = dict(obj.custom_field_data or {})
            for ck, cv in custom_fields.items():
                merged[ck] = cv
            obj.custom_field_data = merged

    def _apply_m2m(self, obj: Any, payload: dict[str, Any]) -> None:
        tags = payload.get("tags")
        if tags is not None and hasattr(obj, "tags"):
            from extras.models import Tag

            # NetBox taggit accepts Tag instances or slug strings — not raw PKs
            resolved: list[Any] = []
            for t in tags:
                if isinstance(t, Tag):
                    resolved.append(t)
                elif isinstance(t, dict):
                    if t.get("id") is not None:
                        resolved.append(t["id"])
                    elif t.get("slug"):
                        resolved.append(t["slug"])
                elif isinstance(t, str):
                    resolved.append(t)
                elif isinstance(t, int):
                    resolved.append(t)
            tag_objs = []
            for item in resolved:
                if isinstance(item, int):
                    tag = Tag.objects.filter(pk=item).first()
                    if tag:
                        tag_objs.append(tag)
                elif isinstance(item, str):
                    tag = Tag.objects.filter(slug=item).first() or Tag.objects.filter(
                        name=item
                    ).first()
                    if tag:
                        tag_objs.append(tag)
                else:
                    tag_objs.append(item)
            obj.tags.set(tag_objs)


# re-export for callers that need slugify without importing netbox HTTP helpers
__all__ = ["DjangoStore", "slugify"]
