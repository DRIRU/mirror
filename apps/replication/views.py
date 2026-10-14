from django.shortcuts import render
from .models import MasterAccount, FollowerAccount, ReplicationOrder, ReplicationAuditLog

def replication_overview_view(request):
    masters = MasterAccount.objects.prefetch_related("followers").all()
    recent_orders = ReplicationOrder.objects.select_related("follower")[:30]
    audit_logs = ReplicationAuditLog.objects.all()[:20]

    context = {
        "masters": masters,
        "recent_orders": recent_orders,
        "audit_logs": audit_logs,
    }
    return render(request, "replication/overview.html", context)

