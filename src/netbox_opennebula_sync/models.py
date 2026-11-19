"""Django models for the OpenNebula Sync plugin."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel
from netbox.models.features import JobsMixin

from .crypto_util import decrypt_secret, encrypt_secret

ORPHAN_CHOICES = (
    ("mark_offline", "Mark offline"),
    ("ignore", "Ignore"),
    ("delete", "Delete"),
)


class OpenNebulaSyncConfig(JobsMixin, NetBoxModel):
    """Singleton configuration for OpenNebula → NetBox synchronization."""

    name = models.CharField(max_length=100, default="default", unique=True)

    # Connection
    one_endpoint = models.CharField(
        max_length=255,
        blank=True,
        help_text="OpenNebula XML-RPC URL, e.g. http://opennebula:2633/RPC2",
    )
    one_username = models.CharField(max_length=100, blank=True)
    one_token_encrypted = models.TextField(blank=True)
    one_timeout = models.PositiveIntegerField(default=30)

    # NetBox API used by the sync engine (localhost gunicorn by default)
    netbox_url = models.CharField(
        max_length=255,
        default="http://127.0.0.1:8001",
        help_text="Base URL the sync job uses to write to NetBox (usually local gunicorn)",
    )
    netbox_host_header = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional Host header (e.g. netbox.example.com)",
    )
    netbox_token_encrypted = models.TextField(blank=True)
    netbox_verify_ssl = models.BooleanField(default=False)

    # Schedule
    sync_enabled = models.BooleanField(default=True)
    sync_interval = models.PositiveIntegerField(
        default=15,
        help_text="Minutes between automatic sync runs",
    )
    orphan_policy = models.CharField(
        max_length=20, choices=ORPHAN_CHOICES, default="mark_offline"
    )
    dry_run = models.BooleanField(default=False)

    # Mapping
    site_name = models.CharField(max_length=100, blank=True, default="")
    cluster_name = models.CharField(max_length=100, blank=True, default="OpenNebula")
    dns_suffix = models.CharField(max_length=100, blank=True, default="")
    create_missing_hosts = models.BooleanField(default=True)

    # SNMP
    snmp_enabled = models.BooleanField(default=True)
    snmp_community = models.CharField(max_length=100, blank=True, default="public")
    snmp_ignore_hostnames = models.TextField(
        blank=True,
        default="localhost\ndemo\ndemo.europe\nubuntu\ndebian",
        help_text="One hostname per line",
    )
    snmp_exclude_interfaces = models.CharField(
        max_length=255,
        blank=True,
        default=r"^(lo|docker\d*|br-.*|veth.*|virbr\d*|cni\d*|flannel\..*|cali.*|tunl\d*)$",
    )

    # Last run summary
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_duration_seconds = models.FloatField(null=True, blank=True)
    last_stats_created = models.PositiveIntegerField(default=0)
    last_stats_updated = models.PositiveIntegerField(default=0)
    last_stats_skipped = models.PositiveIntegerField(default=0)
    last_stats_errors = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "OpenNebula sync configuration"
        verbose_name_plural = "OpenNebula sync configurations"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_opennebula_sync:status")

    @classmethod
    def get_solo(cls) -> OpenNebulaSyncConfig:
        obj, _ = cls.objects.get_or_create(name="default")
        return obj

    def set_one_token(self, plaintext: str) -> None:
        if plaintext:
            self.one_token_encrypted = encrypt_secret(plaintext)

    def get_one_token(self) -> str:
        return decrypt_secret(self.one_token_encrypted)

    def set_netbox_token(self, plaintext: str) -> None:
        if plaintext:
            self.netbox_token_encrypted = encrypt_secret(plaintext)

    def get_netbox_token(self) -> str:
        return decrypt_secret(self.netbox_token_encrypted)

    def ignore_hostnames_list(self) -> list[str]:
        return [
            line.strip().lower()
            for line in (self.snmp_ignore_hostnames or "").splitlines()
            if line.strip()
        ]
