"""
URL configuration for mirror project.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.market_data.urls")),
    path("replication/", include("apps.replication.urls")),
]

