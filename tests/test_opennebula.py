"""Unit tests for OpenNebula helpers and XML parsing."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from netbox_opennebula_sync.opennebula import (
    guess_platform,
    mask_to_prefixlen,
    slugify_vm_name,
)


def test_mask_to_prefixlen():
    assert mask_to_prefixlen("255.255.254.0") == 23
    assert mask_to_prefixlen("255.255.0.0") == 16
    assert mask_to_prefixlen("255.255.255.0") == 24
    assert mask_to_prefixlen("") == 32
    assert mask_to_prefixlen("bad") == 32


def test_slugify_vm_name():
    assert slugify_vm_name("Belenios") == "belenios"
    assert slugify_vm_name("passerelle_admin") == "passerelle-admin"
    assert slugify_vm_name("  Foo  Bar!! ") == "foo-bar"
    assert slugify_vm_name("...") == "vm"


def test_guess_platform():
    assert guess_platform("Base Ubuntu 26.04") == "Ubuntu 26.04"
    assert guess_platform("", "Linux Ubuntu 24.04.1 LTS") == "Ubuntu 24.04"
    assert guess_platform("rocky-9-base") == "Rocky Linux"
    assert guess_platform("custom") is None


def test_parse_vnet_mask_from_xml():
    xml = """
    <VNET_POOL>
      <VNET>
        <ID>1</ID>
        <NAME>LAN</NAME>
        <TEMPLATE>
          <NETWORK_ADDRESS>192.168.0.0</NETWORK_ADDRESS>
          <NETWORK_MASK>255.255.254.0</NETWORK_MASK>
          <GUEST_MTU>9000</GUEST_MTU>
        </TEMPLATE>
      </VNET>
    </VNET_POOL>
    """
    vn = ET.fromstring(xml).find("VNET")
    assert vn is not None
    mask = vn.findtext("TEMPLATE/NETWORK_MASK")
    assert mask_to_prefixlen(mask or "") == 23
