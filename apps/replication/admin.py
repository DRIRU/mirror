from django.contrib import admin
from .models import MasterAccount, FollowerAccount, ReplicationOrder, ReplicationAuditLog

@admin.register(MasterAccount)
class MasterAccountAdmin(admin.ModelAdmin):
    list_display = ("label", "base_currency", "is_active", "created_at")
    list_filter = ("is_active",)

@admin.register(FollowerAccount)
class FollowerAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "master", "equity_balance", "allocation_ratio", "max_contract_qty", "is_active")
    list_filter = ("is_active", "master")
    search_fields = ("name",)

@admin.register(ReplicationOrder)
class ReplicationOrderAdmin(admin.ModelAdmin):
    list_display = ("order_link_id", "symbol", "side", "follower", "follower_qty", "status", "created_at")
    list_filter = ("status", "side")
    search_fields = ("symbol", "order_link_id")
    readonly_fields = ("order_link_id", "created_at")

@admin.register(ReplicationAuditLog)
class ReplicationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "timestamp")
    readonly_fields = ("timestamp", "event_type", "details")

