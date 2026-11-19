# Changelog

## 0.3.1

- Fix sidenav double-highlight: Live Status and Settings are sibling URLs (`/status/`, `/settings/`) so NetBox no longer marks both active.

## 0.3.0

- Plugin sync writes via Django ORM (no NetBox URL / API token in Settings).
- Site and Cluster settings use NetBox dropdowns (foreign keys).
- Management command `opennebula_sync`.
- Public GitHub + PyPI packaging for community / certification.

## 0.2.0

- NetBox plugin UI: Live Status, Settings, RQ sync jobs.
