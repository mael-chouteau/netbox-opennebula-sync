"""Synchronize OpenNebula inventory into NetBox Community (plugin + CLI)."""

__version__ = "0.3.0"

try:
    from netbox.plugins import PluginConfig
except ImportError:  # Standalone CLI / unit tests without NetBox
    config = None
else:

    class OpenNebulaSyncConfig(PluginConfig):
        name = "netbox_opennebula_sync"
        verbose_name = "OpenNebula Sync"
        description = "Discover and synchronize OpenNebula infrastructure into NetBox"
        version = __version__
        author = "NetBox OpenNebula Sync contributors"
        author_email = "dev@localhost"
        base_url = "opennebula"
        min_version = "4.2"
        default_settings = {}
        required_settings = []

        def ready(self):
            super().ready()
            from . import jobs  # noqa: F401

    config = OpenNebulaSyncConfig
