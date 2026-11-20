# Changelog

## 0.3.3

- Remove personal catalog/certification draft docs from the public package README / repo.

## 0.3.2

- Fix ORM IP lookup: use `address__net_host` so sync no longer recreates duplicate `IPAddress` rows.
- Assign primary FQDN only to the primary NIC; Admin/iSCSI secondaries get a role suffix or stay empty.
- Sanitize `_` → `-` in VM / DNS labels for RFC 1035 and `netbox-plugin-dns` compatibility.

## 0.3.1

- Fix sidenav double-highlight: Live Status and Settings are sibling URLs (`/status/`, `/settings/`) so NetBox no longer marks both active.

## 0.3.0

- Plugin sync writes via Django ORM (no NetBox URL / API token in Settings).
- Site and Cluster settings use NetBox dropdowns (foreign keys).
- Management command `opennebula_sync`.
- Public GitHub + PyPI packaging for community / certification.

## 0.2.0

- NetBox plugin UI: Live Status, Settings, RQ sync jobs.
