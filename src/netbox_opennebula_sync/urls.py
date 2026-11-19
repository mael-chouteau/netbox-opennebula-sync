from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    # Sibling paths (not nested) so NetBox sidenav active matching does not
    # highlight Live Status when Settings is open (prefix RegExp match).
    path(
        "",
        RedirectView.as_view(
            pattern_name="plugins:netbox_opennebula_sync:status",
            permanent=False,
        ),
        name="home",
    ),
    path("status/", views.StatusView.as_view(), name="status"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
]
