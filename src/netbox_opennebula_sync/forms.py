from django import forms
from dcim.models import Site
from utilities.forms.fields import DynamicModelChoiceField
from virtualization.models import Cluster

from .models import ORPHAN_CHOICES, OpenNebulaSyncConfig


class OpenNebulaSyncConfigForm(forms.ModelForm):
    one_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"placeholder": "••••••••"}),
        label="OpenNebula token / password",
        help_text="Leave blank to keep the current secret",
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
    site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label="Site",
        help_text="NetBox site that owns synchronized objects",
    )
    cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
        label="Cluster",
        help_text="Existing NetBox cluster used as sync target",
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
            "site",
            "cluster",
            "dns_suffix",
            "create_missing_hosts",
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
        if commit:
            obj.save()
        return obj
