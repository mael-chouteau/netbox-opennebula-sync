# netbox-opennebula-sync

[![CI](https://github.com/pmbservices/netbox-opennebula-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/pmbservices/netbox-opennebula-sync/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

Discover OpenNebula zones, clusters, KVM hosts and virtual machines, then reconcile them into
**NetBox Community** (4.2+ / 4.7+) using the same object model as the official NetBox Labs
VMware vCenter and Proxmox VE integrations — without requiring NetBox Enterprise or Assurance.

Optional SNMPv2c guest enrichment (hostname / OS) works without a QEMU guest agent.

## Architecture

```text
OpenNebula XML-RPC ──► Collector ──► Idempotent Reconciler ──► NetBox REST API
Optional SNMPv2c ─────► Guest Enricher ─┘
```

| OpenNebula | NetBox |
|---|---|
| Zone | Cluster Group (`opennebula_zone_id`) |
| Cluster | Cluster + Cluster Type `OpenNebula KVM` |
| Host | Device (hypervisor) + `opennebula_host_id` |
| VM | Virtual Machine + `opennebula_vm_id` / UUID / template |
| DISK | Virtual Disk |
| NIC + VNet | VM Interface, MAC Address, IP Address (CIDR from `NETWORK_MASK`) |

Managed objects are tagged `opennebula` + `discovered`. Orphans default to **`mark_offline`**
(never delete VMs/IPs during cold-backup power-offs).

## Requirements

- Python 3.11+
- NetBox Community 4.2+ (Virtual Disks / MAC Address model; tested on 4.7)
- OpenNebula 6.x XML-RPC endpoint
- Optional: `snmpget` (net-snmp) for guest enrichment

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .

cp config.example.yaml config.yaml
# edit config.yaml — never commit secrets

netbox-opennebula-sync -c config.yaml bootstrap
netbox-opennebula-sync -c config.yaml sync --dry-run
netbox-opennebula-sync -c config.yaml sync
```

### Docker

```bash
cp config.example.yaml config.yaml
docker compose -f docker-compose.example.yaml up --build -d
```

### systemd (oneshot timer)

```bash
sudo mkdir -p /opt/netbox-opennebula-sync /etc/netbox-opennebula-sync
sudo python3 -m venv /opt/netbox-opennebula-sync/venv
sudo /opt/netbox-opennebula-sync/venv/bin/pip install /path/to/netbox-opennebula-sync
sudo install -m 0600 config.yaml /etc/netbox-opennebula-sync/config.yaml
sudo cp contrib/systemd/netbox-opennebula-sync.service \
        contrib/systemd/netbox-opennebula-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now netbox-opennebula-sync.timer
```

The unit uses `DynamicUser=yes` and `LoadCredential=` so the process never needs a permanent
system account or world-readable secrets under `/etc`.

## OpenNebula read-only user

Create a dedicated user with **read** ACL on `VM+HOST+NET+ZONE+CLUSTER` only. Pass credentials as
`username:token` (OpenNebula auth token) via config or `ONE_CREDENTIALS`.

## Configuration

See [`config.example.yaml`](config.example.yaml). Environment overrides:

| Variable | Purpose |
|---|---|
| `NETBOX_URL` / `NETBOX_TOKEN` | NetBox base URL and API token (`nbt_…` → Bearer, else Token) |
| `NETBOX_VERIFY_SSL` | `true` / `false` / path to CA file |
| `NETBOX_DNS_SUFFIX` | Appended to short names for `dns_name` |
| `ONE_ENDPOINT` | XML-RPC URL |
| `ONE_CREDENTIALS` | `username:token` |
| `ONE_USERNAME` / `ONE_TOKEN` | Split credentials |
| `SNMP_COMMUNITY` / `SNMP_ENABLED` | Guest enrichment |
| `ALL_PROXY` / `HTTPS_PROXY` | SOCKS/HTTP proxy for NetBox (e.g. `socks5h://127.0.0.1:1080`) |
| `SYNC_ORPHAN_POLICY` | `mark_offline` (default) / `delete` / `ignore` |
| `SYNC_DRY_RUN` | `true` to log actions without writing |

SNMP `ignore_hostnames` skips golden-image placeholders (`localhost`, `demo`, …) and falls back
to the OpenNebula VM name. `exclude_interfaces` drops Docker/K8s bridge noise.

## CLI

```text
netbox-opennebula-sync bootstrap [--dry-run]
netbox-opennebula-sync sync [--dry-run]
netbox-opennebula-sync daemon [--interval 900] [--dry-run]
```

## Safe ingestion

1. Always run `bootstrap` once.
2. Run `sync --dry-run` and review logs.
3. Prefer `orphan_policy: mark_offline`.
4. Use a dedicated NetBox token with write scope limited to virtualization/IPAM/DCIM as needed.
5. Keep secrets out of git (`config.yaml` is gitignored).

## Development

```bash
pip install -e ".[dev]"
ruff check src tests
pytest -q
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
