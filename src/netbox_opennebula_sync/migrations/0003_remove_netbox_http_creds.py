from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_opennebula_sync", "0002_site_cluster_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="opennebulasyncconfig",
            name="netbox_url",
        ),
        migrations.RemoveField(
            model_name="opennebulasyncconfig",
            name="netbox_host_header",
        ),
        migrations.RemoveField(
            model_name="opennebulasyncconfig",
            name="netbox_token_encrypted",
        ),
        migrations.RemoveField(
            model_name="opennebulasyncconfig",
            name="netbox_verify_ssl",
        ),
    ]
