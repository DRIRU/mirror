from django.urls import path
from . import views

urlpatterns = [
    path("", views.replication_overview_view, name="replication_overview"),
    path("accounts/", views.follower_accounts_list_view, name="follower_accounts_list"),
    path("accounts/add/", views.follower_account_create_view, name="follower_account_create"),
    path("accounts/<int:account_id>/edit/", views.follower_account_edit_view, name="follower_account_edit"),
    path("accounts/<int:account_id>/toggle/", views.follower_account_toggle_view, name="follower_account_toggle"),
    path("accounts/<int:account_id>/delete/", views.follower_account_delete_view, name="follower_account_delete"),
    path("accounts/validate-syntax/", views.validate_credentials_syntax_view, name="validate_credentials_syntax"),
]
