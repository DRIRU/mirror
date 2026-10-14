from django.urls import path
from . import views

urlpatterns = [
    path("", views.options_chain_view, name="options_chain"),
    path("chain-table/", views.chain_table_partial, name="chain_table"),
    path("fetch-quotes/", views.fetch_quotes_action, name="fetch_quotes"),
    path("refresh-instruments/", views.refresh_instruments_action, name="refresh_instruments"),
    path("contract-drawer/", views.contract_drawer_partial, name="contract_drawer"),
]

