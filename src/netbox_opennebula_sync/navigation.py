from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label="OpenNebula",
    icon_class="mdi mdi-cloud-sync",
    groups=(
        (
            "Sync",
            (
                PluginMenuItem(
                    link="plugins:netbox_opennebula_sync:status",
                    link_text="Live Status",
                    permissions=["netbox_opennebula_sync.view_opennebulasyncconfig"],
                ),
                PluginMenuItem(
                    link="plugins:netbox_opennebula_sync:settings",
                    link_text="Settings",
                    permissions=["netbox_opennebula_sync.change_opennebulasyncconfig"],
                ),
            ),
        ),
    ),
)
