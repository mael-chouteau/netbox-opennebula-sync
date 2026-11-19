# netbox-opennebula-sync

NetBox Community **plugin** that discovers OpenNebula zones, hosts and VMs and reconciles them into Virtualization / IPAM — with a clean **Live Status** page and **Settings** UI (sync rate, credentials, SNMP).

Also ships a standalone CLI for automation and CI.

## Features

- Plugins → **OpenNebula** → Live Status (live ONE probe) + Settings
- Configurable sync interval (minutes), orphan policy, dry-run
- RQ background job (`Sync now` + automatic schedule)
- Optional SNMPv2c guest enrichment
- Apache-2.0, NetBox 4.2+ / 4.7

## Install (plugin)

```bash
/opt/netbox/venv/bin/pip install /path/to/netbox-opennebula-sync
```

In `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = [
    'netbox_opennebula_sync',
]
```

```bash
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate netbox_opennebula_sync
sudo systemctl restart netbox netbox-rq
```

Open **Plugins → OpenNebula → Settings**, enter the OpenNebula XML-RPC URL and credentials, set the sync interval, Save. Use **Live Status → Sync now** for a first run.

The RQ worker (`netbox-rq`) must be running for scheduled and on-demand sync jobs.

## Standalone CLI

```bash
pip install .
cp config.example.yaml config.yaml
netbox-opennebula-sync -c config.yaml bootstrap
netbox-opennebula-sync -c config.yaml sync --dry-run
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
