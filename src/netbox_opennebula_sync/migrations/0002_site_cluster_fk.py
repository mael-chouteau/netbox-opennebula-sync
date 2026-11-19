import django.db.models.deletion
from django.db import migrations, models


def forwards_map_names(apps, schema_editor):
    Config = apps.get_model("netbox_opennebula_sync", "OpenNebulaSyncConfig")
    Site = apps.get_model("dcim", "Site")
    Cluster = apps.get_model("virtualization", "Cluster")
    for cfg in Config.objects.all():
        site_name = getattr(cfg, "site_name", "") or ""
        cluster_name = getattr(cfg, "cluster_name", "") or ""
        if site_name:
            site = Site.objects.filter(name=site_name).first()
            if site:
                cfg.site_id = site.pk
        if cluster_name:
            cluster = Cluster.objects.filter(name=cluster_name).first()
            if cluster:
                cfg.cluster_id = cluster.pk
        cfg.save()


class Migration(migrations.Migration):
    dependencies = [
        ("dcim", "0251_fix_ltree_cascade_triggers"),
        ("virtualization", "0060_consolidate_unique_constraints"),
        ("netbox_opennebula_sync", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="opennebulasyncconfig",
            name="site",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="dcim.site",
            ),
        ),
        migrations.AddField(
            model_name="opennebulasyncconfig",
            name="cluster",
            field=models.ForeignKey(
                blank=True,
                help_text="Target NetBox cluster for synchronized VMs",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="virtualization.cluster",
            ),
        ),
        migrations.RunPython(forwards_map_names, migrations.RunPython.noop),
        migrations.RemoveField(model_name="opennebulasyncconfig", name="site_name"),
        migrations.RemoveField(model_name="opennebulasyncconfig", name="cluster_name"),
    ]
