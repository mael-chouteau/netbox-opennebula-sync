# NetBox Labs Plugin Certification — submission draft

**To:** plugincertification@netboxlabs.com  

**Subject:** Plugin Certification application — netbox-opennebula-sync

---

## Required fields (fill before send)

| Field | Value |
|-------|--------|
| GitHub repository | https://github.com/mael-chouteau/netbox-opennebula-sync |
| GitHub user ID | `mael-chouteau` (numeric id `101983244`) |
| PyPI package | https://pypi.org/project/netbox-opennebula-sync/ |
| PyPI user ID | `mchouteau` |
| NetDev Slack handle | Maël Chouteau |

## Email body

Hello,

### Plugin Overview

**netbox-opennebula-sync** is a NetBox Community plugin that discovers OpenNebula zones, hypervisors and virtual machines and reconciles them into NetBox Virtualization, DCIM and IPAM.

It provides:

- a NetBox UI (Live Status + Settings) under Plugins → OpenNebula  
- RQ-scheduled and on-demand sync jobs  
- optional SNMPv2c guest enrichment  
- in-process Django ORM writes (no NetBox API token required for the plugin path)  
- a standalone CLI for remote NetBox over HTTP  

We are applying for Plugin Certification so operators running OpenNebula can discover a maintained, documented integration in the official NetBox Labs plugin catalog, with clear compatibility expectations for NetBox Community / Cloud / Enterprise.

**License:** Apache-2.0  
**NetBox support:** 4.2+ (tested on NetBox Community 4.7.4)  
**Install:** `pip install netbox-opennebula-sync` then `PLUGINS = ['netbox_opennebula_sync']`

### GitHub Repository

https://github.com/mael-chouteau/netbox-opennebula-sync

### PyPI Package Entry

https://pypi.org/project/netbox-opennebula-sync/

### Maintainer IDs

- **GitHub:** mael-chouteau (`101983244`)  
- **PyPI:** mchouteau

### Slack Handle

Maël Chouteau on NetDev Community Slack (`#netbox-plugins`)

Thank you for considering this submission.

Best regards,  
Maël Chouteau
