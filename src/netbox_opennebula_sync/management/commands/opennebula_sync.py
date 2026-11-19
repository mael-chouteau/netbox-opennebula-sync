"""Run OpenNebula → NetBox sync via Django ORM (same path as the RQ job)."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from netbox_opennebula_sync.bridge import app_config_from_db
from netbox_opennebula_sync.django_store import DjangoStore
from netbox_opennebula_sync.models import OpenNebulaSyncConfig
from netbox_opennebula_sync.reconciler import run_bootstrap, run_sync


class Command(BaseCommand):
    help = "Synchronize OpenNebula inventory into NetBox using the ORM store"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bootstrap-only",
            action="store_true",
            help="Only ensure tags / custom fields / cluster type",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log changes without writing",
        )

    def handle(self, *args, **options):
        cfg = OpenNebulaSyncConfig.get_solo()
        try:
            app_cfg = app_config_from_db(cfg)
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        if options["dry_run"]:
            app_cfg.sync.dry_run = True

        store = DjangoStore(dry_run=app_cfg.sync.dry_run)
        if options["bootstrap_only"]:
            rc = run_bootstrap(app_cfg, store=store)
        else:
            stats: dict[str, int] = {}
            rc = run_sync(app_cfg, out_stats=stats, store=store)
            self.stdout.write(self.style.NOTICE(f"stats={stats}"))

        if rc:
            raise CommandError(f"sync finished with errors (rc={rc})")
        self.stdout.write(self.style.SUCCESS("OpenNebula sync completed"))
