from django import forms

from .models import ORPHAN_CHOICES, OpenNebulaSyncConfig


class OpenNebulaSyncConfigForm(forms.ModelForm):
    one_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "••••••••"}),
        label="OpenNebula token / password",
        help_text="Leave blank to keep the current secret",
    )
    netbox_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "••••••••"}),
        label="NetBox API token",
        help_text="Optional. Leave blank to auto-create a dedicated token on first sync",
    )
    sync_interval = forms.IntegerField(
        min_value=1,
        max_value=10080,
        help_text="Minutes between automatic syncs (presets: 5 / 15 / 30 / 60)",
    )
    orphan_policy = forms.ChoiceField(choices=ORPHAN_CHOICES)
    snmp_ignore_hostnames = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One hostname per line",
    )

    class Meta:
        model = OpenNebulaSyncConfig
        fields = (
            "one_endpoint",
            "one_username",
            "one_timeout",
            "sync_enabled",
            "sync_interval",
            "orphan_policy",
            "dry_run",
            "site_name",
            "cluster_name",
            "dns_suffix",
            "create_missing_hosts",
            "netbox_url",
            "netbox_host_header",
            "netbox_verify_ssl",
            "snmp_enabled",
            "snmp_community",
            "snmp_ignore_hostnames",
            "snmp_exclude_interfaces",
        )

    def save(self, commit=True):
        obj = super().save(commit=False)
        one_token = self.cleaned_data.get("one_token")
        if one_token:
            obj.set_one_token(one_token)
        nb_token = self.cleaned_data.get("netbox_token")
        if nb_token:
            obj.set_netbox_token(nb_token)
        if commit:
            obj.save()
        return obj
