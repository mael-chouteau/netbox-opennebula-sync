# NetBox plugins catalog submission

Use this when contacting the NetBox Labs plugin catalog team or posting in NetDev Slack `#netbox-plugins`.

**Suggested contacts**

- Catalog team (per [NetBox Plugins wiki](https://github.com/netbox-community/netbox/wiki/Plugins)): email the NetBox Labs plugins catalog team
- Community: NetDev Slack → `#netbox-plugins`
- Optional: [communityfund@netboxlabs.com](mailto:communityfund@netboxlabs.com) only if asking about certification / bounty programs

## Email / Slack template

**Subject:** Catalog suggestion — netbox-opennebula-sync (OpenNebula → NetBox)

Hello,

I would like to suggest a new community plugin for the NetBox plugins catalog:

- **Name:** netbox-opennebula-sync  
- **Repo:** https://github.com/mael-chouteau/netbox-opennebula-sync  
- **License:** Apache-2.0  
- **NetBox:** 4.2+ (tested on 4.7.4 Community)  
- **Category:** Virtualization / inventory sync  

**Summary:** Discovers OpenNebula zones, hosts and VMs and reconciles them into NetBox Virtualization, DCIM and IPAM. Ships a NetBox UI (Live Status + Settings), RQ-scheduled sync, optional SNMPv2c guest enrichment, and in-process Django ORM writes (no NetBox API token required for the plugin path). Also provides a standalone CLI for remote NetBox.

**Install:**

```text
pip install git+https://github.com/mael-chouteau/netbox-opennebula-sync.git
```

```python
PLUGINS = ['netbox_opennebula_sync']
```

Happy to adjust packaging (PyPI), docs or compatibility notes for listing / Compatible certification.

Thanks!
