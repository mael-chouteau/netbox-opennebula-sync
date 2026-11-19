# netbox-opennebula-sync

[![CI](https://github.com/mael-chouteau/netbox-opennebula-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/mael-chouteau/netbox-opennebula-sync/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/netbox-opennebula-sync.svg)](https://pypi.org/project/netbox-opennebula-sync/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![NetBox](https://img.shields.io/badge/NetBox-4.2%2B-green.svg)](https://github.com/netbox-community/netbox)

NetBox Community plugin that discovers **OpenNebula** zones, hypervisors and VMs and reconciles them into NetBox **Virtualization**, **DCIM** and **IPAM** — using the Django ORM in-process (no NetBox API token required for the plugin path).

Ideal for operators who already run OpenNebula and want NetBox as the single source of truth for guests, interfaces, MACs and IPs.

## Features

| Area | What you get |
|------|----------------|
| **UI** | Plugins → OpenNebula → **Live Status** (ONE probe) + **Settings** |
| **Sync** | RQ job: on-demand *Sync now* + configurable interval (minutes) |
| **Mapping** | Site & Cluster picked from existing NetBox objects (dropdowns) |
| **Inventory** | Cluster type/group, hypervisors as devices, VMs, VM interfaces, virtual disks |
| **IPAM** | MAC addresses, IP assignments, optional primary IPv4, VLAN hints |
| **SNMP** | Optional SNMPv2c guest enrichment (hostname / interfaces) |
| **Safety** | Dry-run, orphan policy (`mark_offline` / `delete` / `ignore`), OpenNebula custom fields |
| **CLI** | Standalone YAML+HTTP client for remote NetBox; `manage.py opennebula_sync` for ORM |

Compatible with **NetBox 4.2+** (tested on **4.7**). License: **Apache-2.0**.

## Screenshots

> Add screenshots of Live Status and Settings after first public release (optional).

## Requirements

- NetBox 4.2 or newer with **netbox-rq** running
- OpenNebula XML-RPC endpoint (user with inventory read rights)
- Python 3.11+

## Installation

```bash
/opt/netbox/venv/bin/pip install netbox-opennebula-sync
```

In `configuration.py`:

```python
PLUGINS = [
    'netbox_opennebula_sync',
]
```

```bash
sudo -u netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate netbox_opennebula_sync
sudo systemctl restart netbox netbox-rq
```

1. Open **Plugins → OpenNebula → Settings**
2. Set OpenNebula endpoint, username and token
3. Select **Site** and **Cluster** (existing NetBox objects)
4. Save, then **Live Status → Sync now**

The plugin writes through the **Django ORM**. You do **not** configure a NetBox URL or API token in the UI.

## Configuration reference

| Setting | Description |
|---------|-------------|
| OpenNebula endpoint / user / token | XML-RPC credentials |
| Sync interval | Minutes between automatic RQ runs |
| Orphan policy | What to do with NetBox VMs tagged `opennebula` that disappeared from ONE |
| Dry run | Log intended changes without writing |
| Site / Cluster | Target NetBox objects for synced inventory |
| DNS suffix | Appended to short guest names when needed |
| Create missing hosts | Create hypervisor devices if absent |
| SNMP | Community, ignore list, interface exclude regex |

Custom fields created on first sync: `opennebula_zone_id`, `opennebula_cluster_id`, `opennebula_host_id`, `opennebula_vm_id`, `opennebula_vm_uuid`, `opennebula_template_id`.

## Operations

```bash
# Same path as the RQ job (ORM)
sudo -u netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py opennebula_sync
sudo -u netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py opennebula_sync --dry-run
```

### Standalone CLI (remote NetBox over HTTP)

```bash
pip install .
cp config.example.yaml config.yaml   # fill NETBOX_* and ONE_*
netbox-opennebula-sync -c config.yaml bootstrap
netbox-opennebula-sync -c config.yaml sync --dry-run
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest -q
```

## Catalog / certification

- Catalog blurb: [`docs/CATALOG_SUBMISSION.md`](docs/CATALOG_SUBMISSION.md)  
- **Plugin Certification** application (email `plugincertification@netboxlabs.com`): [`docs/CERTIFICATION_SUBMISSION.md`](docs/CERTIFICATION_SUBMISSION.md)  

Certification requires a published **PyPI** package plus GitHub, PyPI and NetDev Slack maintainer IDs.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
