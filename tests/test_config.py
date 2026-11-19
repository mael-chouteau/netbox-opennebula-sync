"""Configuration loading."""

from __future__ import annotations

from pathlib import Path

from netbox_opennebula_sync.config import load_config


def test_load_from_yaml(tmp_path: Path, monkeypatch):
    for key in (
        "NETBOX_URL",
        "NETBOX_TOKEN",
        "ONE_ENDPOINT",
        "ONE_USERNAME",
        "ONE_TOKEN",
        "ONE_CREDENTIALS",
        "ALL_PROXY",
        "HTTPS_PROXY",
    ):
        monkeypatch.delenv(key, raising=False)

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
netbox:
  url: https://netbox.example
  token: nbt_test
  dns_suffix: example.com
  verify_ssl: false
opennebula:
  endpoint: http://one.example:2633/RPC2
  username: sync
  token: secret
snmp:
  ignore_hostnames: [localhost, demo]
sync:
  orphan_policy: mark_offline
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg.netbox.url == "https://netbox.example"
    assert cfg.netbox.token == "nbt_test"
    assert cfg.netbox.verify_ssl is False
    assert cfg.netbox.dns_suffix == "example.com"
    assert cfg.opennebula.credentials == "sync:secret"
    assert "demo" in cfg.snmp.ignore_hostnames
    assert cfg.sync.orphan_policy == "mark_offline"


def test_one_credentials_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("NETBOX_URL", "https://nb")
    monkeypatch.setenv("NETBOX_TOKEN", "nbt_x")
    monkeypatch.setenv("ONE_ENDPOINT", "http://one:2633/RPC2")
    monkeypatch.setenv("ONE_CREDENTIALS", "user:tok")
    monkeypatch.delenv("ONE_USERNAME", raising=False)
    monkeypatch.delenv("ONE_TOKEN", raising=False)
    cfg = load_config(None)
    assert cfg.opennebula.username == "user"
    assert cfg.opennebula.token == "tok"
