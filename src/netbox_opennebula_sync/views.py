from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from .forms import OpenNebulaSyncConfigForm
from .jobs import SyncJob, schedule_from_config
from .models import OpenNebulaSyncConfig
from .status import probe_opennebula


class StatusView(PermissionRequiredMixin, TemplateView):
    template_name = "netbox_opennebula_sync/status.html"
    permission_required = "netbox_opennebula_sync.view_opennebulasyncconfig"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cfg = OpenNebulaSyncConfig.get_solo()
        context.update(
            {
                "config": cfg,
                "live": probe_opennebula(cfg),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        cfg = OpenNebulaSyncConfig.get_solo()
        action = request.POST.get("action")
        if action == "sync_now":
            SyncJob.enqueue(instance=cfg)
            messages.success(request, "OpenNebula sync job enqueued.")
        elif action == "test_connection":
            live = probe_opennebula(cfg)
            if live.reachable:
                total = live.vms_active + live.vms_offline + live.vms_other
                messages.success(
                    request,
                    f"Connected to OpenNebula {live.version} "
                    f"({live.latency_ms} ms) — {total} VMs",
                )
            else:
                messages.error(request, f"Connection failed: {live.error}")
        return redirect("plugins:netbox_opennebula_sync:status")


class SettingsView(PermissionRequiredMixin, View):
    permission_required = "netbox_opennebula_sync.change_opennebulasyncconfig"
    template_name = "netbox_opennebula_sync/settings.html"

    def get(self, request):
        cfg = OpenNebulaSyncConfig.get_solo()
        form = OpenNebulaSyncConfigForm(instance=cfg)
        return render(
            request,
            self.template_name,
            {"form": form, "object": cfg, "interval_presets": (5, 15, 30, 60)},
        )

    def post(self, request):
        cfg = OpenNebulaSyncConfig.get_solo()
        form = OpenNebulaSyncConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            obj = form.save()
            messages.success(request, "Settings saved.")
            try:
                if obj.sync_enabled and obj.one_endpoint:
                    schedule_from_config(obj)
                    messages.info(
                        request,
                        f"Automatic sync scheduled every {obj.sync_interval} minutes.",
                    )
            except Exception as exc:
                messages.warning(request, f"Could not schedule sync job: {exc}")
            return redirect("plugins:netbox_opennebula_sync:settings")
        return render(
            request,
            self.template_name,
            {"form": form, "object": cfg, "interval_presets": (5, 15, 30, 60)},
        )
