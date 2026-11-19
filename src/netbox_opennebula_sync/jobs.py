"""Background sync job (RQ) for the OpenNebula plugin."""

from __future__ import annotations

import time

from django.utils import timezone
from netbox.jobs import JobRunner

from .bridge import app_config_from_db
from .models import OpenNebulaSyncConfig
from .reconciler import run_sync


class SyncJob(JobRunner):
    class Meta:
        name = "OpenNebula Sync"

    def run(self, *args, **kwargs):
        cfg = OpenNebulaSyncConfig.get_solo()
        started = time.monotonic()
        stats: dict[str, int] = {}
        try:
            app_cfg = app_config_from_db(cfg)
            rc = run_sync(app_cfg, out_stats=stats)
            duration = time.monotonic() - started
            OpenNebulaSyncConfig.objects.filter(pk=cfg.pk).update(
                last_success_at=timezone.now() if rc == 0 else cfg.last_success_at,
                last_failure_at=cfg.last_failure_at if rc == 0 else timezone.now(),
                last_duration_seconds=duration,
                last_stats_created=stats.get("created", 0),
                last_stats_updated=stats.get("updated", 0),
                last_stats_skipped=stats.get("skipped", 0),
                last_stats_errors=stats.get("errors", 0),
                last_error="" if rc == 0 else f"sync finished with errors (rc={rc})",
            )
            if rc:
                self.logger.error("OpenNebula sync finished with errors (rc=%s)", rc)
            else:
                self.logger.info(
                    "OpenNebula sync completed in %.1fs stats=%s", duration, stats
                )
            if cfg.sync_enabled and cfg.sync_interval:
                SyncJob.enqueue_once(instance=cfg, interval=int(cfg.sync_interval))
        except Exception as exc:
            duration = time.monotonic() - started
            OpenNebulaSyncConfig.objects.filter(pk=cfg.pk).update(
                last_failure_at=timezone.now(),
                last_duration_seconds=duration,
                last_error=str(exc)[:2000],
            )
            self.logger.error("OpenNebula sync failed: %s", exc)
            raise


def schedule_from_config(cfg: OpenNebulaSyncConfig | None = None) -> None:
    cfg = cfg or OpenNebulaSyncConfig.get_solo()
    if cfg.sync_enabled and cfg.sync_interval and cfg.one_endpoint:
        SyncJob.enqueue_once(instance=cfg, interval=int(cfg.sync_interval))
