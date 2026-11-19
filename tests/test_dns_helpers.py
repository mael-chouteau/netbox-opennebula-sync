"""DNS label sanitization and multi-NIC dns_name helpers."""

from netbox_opennebula_sync.opennebula import dns_name_for_nic, slugify_vm_name


def test_slugify_replaces_underscores():
    assert slugify_vm_name("passerelle_admin") == "passerelle-admin"
    assert slugify_vm_name("Passerelle_Admin.Europe") == "passerelle-admin.europe"


def test_dns_name_primary_keeps_fqdn():
    assert (
        dns_name_for_nic("cloudpmb.europe", is_primary=True, network="Réseau")
        == "cloudpmb.europe"
    )


def test_dns_name_secondary_empty_by_default():
    assert dns_name_for_nic("cloudpmb.europe", is_primary=False, network="Guest") == ""


def test_dns_name_secondary_admin_suffix():
    assert (
        dns_name_for_nic("cloudpmb.europe", is_primary=False, network="Administration")
        == "cloudpmb-admin.europe"
    )


def test_dns_name_secondary_iscsi_suffix():
    assert (
        dns_name_for_nic("acropole.europe", is_primary=False, network="ISCSI")
        == "acropole-iscsi.europe"
    )
