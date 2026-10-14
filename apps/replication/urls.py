from django.urls import path
from . import views

urlpatterns = [
    path("", views.replication_overview_view, name="replication_overview"),
]

