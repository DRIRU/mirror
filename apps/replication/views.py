from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST, require_http_methods
from .models import MasterAccount, FollowerAccount, ReplicationOrder, ReplicationAuditLog
from .security import (
    validate_follower_input,
    inspect_secret_format,
    encrypt_secret,
    mask_api_key,
    mask_api_secret,
)


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


def follower_accounts_list_view(request):
    """
    Dedicated management page for Friend / Follower Accounts.
    Displays accounts, security status, and form to add friends.
    """
    masters = MasterAccount.objects.all()
    if not masters.exists():
        # Ensure at least one master account exists for replication
        MasterAccount.objects.create(
            label="Primary Master Account",
            api_key="csp_live_master_demo_key_001",
            api_secret="858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7",
            base_currency="USDT",
            is_active=True,
        )
        masters = MasterAccount.objects.all()

    followers = FollowerAccount.objects.select_related("master").order_by("-created_at")
    
    total_followers = followers.count()
    active_followers = followers.filter(is_active=True).count()
    total_equity = sum(f.equity_balance for f in followers)

    recent_security_logs = ReplicationAuditLog.objects.filter(
        event_type__in=[
            "FOLLOWER_REGISTERED",
            "FOLLOWER_UPDATED",
            "FOLLOWER_TOGGLED",
            "FOLLOWER_DELETED",
        ]
    )[:10]

    context = {
        "masters": masters,
        "followers": followers,
        "total_followers": total_followers,
        "active_followers": active_followers,
        "total_equity": total_equity,
        "recent_security_logs": recent_security_logs,
    }
    return render(request, "replication/accounts.html", context)


@require_POST
def follower_account_create_view(request):
    """
    Handles secure submission of a new friend / follower account.
    Validates input, encrypts secret at rest, and logs audit trail.
    """
    name = request.POST.get("name", "").strip()
    master_id = request.POST.get("master_id")
    api_key = request.POST.get("api_key", "").strip()
    api_secret = request.POST.get("api_secret", "").strip()
    
    raw_equity = request.POST.get("equity_balance", "1000.00").strip()
    raw_ratio = request.POST.get("allocation_ratio", "1.00").strip()
    raw_max_qty = request.POST.get("max_contract_qty", "10.00").strip()
    raw_drawdown = request.POST.get("max_drawdown_limit", "500.00").strip()
    is_active = request.POST.get("is_active") in ["on", "true", "1", "True"]

    errors = validate_follower_input(name, api_key, api_secret, is_edit=False)

    try:
        equity_balance = Decimal(raw_equity)
        if equity_balance <= Decimal("0"):
            errors.append("Equity balance must be greater than 0.")
    except (InvalidOperation, ValueError):
        errors.append("Invalid equity balance format.")

    try:
        allocation_ratio = Decimal(raw_ratio)
        if allocation_ratio <= Decimal("0") or allocation_ratio > Decimal("10.0"):
            errors.append("Allocation ratio must be between 0.01x and 10.00x.")
    except (InvalidOperation, ValueError):
        errors.append("Invalid allocation ratio format.")

    try:
        max_contract_qty = Decimal(raw_max_qty)
        if max_contract_qty <= Decimal("0"):
            errors.append("Max contract quantity must be greater than 0.")
    except (InvalidOperation, ValueError):
        errors.append("Invalid max contract quantity format.")

    try:
        max_drawdown_limit = Decimal(raw_drawdown)
        if max_drawdown_limit <= Decimal("0"):
            errors.append("Max drawdown limit must be greater than 0.")
    except (InvalidOperation, ValueError):
        errors.append("Invalid drawdown limit format.")

    # Find master account
    master = None
    if master_id:
        master = MasterAccount.objects.filter(id=master_id).first()
    if not master:
        master = MasterAccount.objects.first()

    if not master:
        errors.append("No Master Account available to link with this follower.")

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect("follower_accounts_list")

    # Create account (api_secret is encrypted at rest in model save hook)
    follower = FollowerAccount.objects.create(
        master=master,
        name=name,
        api_key=api_key,
        api_secret=api_secret,
        equity_balance=equity_balance,
        allocation_ratio=allocation_ratio,
        max_contract_qty=max_contract_qty,
        max_drawdown_limit=max_drawdown_limit,
        is_active=is_active,
    )

    # Cryptographic Audit Log (No secrets recorded)
    ReplicationAuditLog.objects.create(
        event_type="FOLLOWER_REGISTERED",
        details={
            "account_id": follower.id,
            "name": follower.name,
            "master": master.label,
            "masked_key": follower.masked_api_key,
            "equity": str(follower.equity_balance),
            "ratio": str(follower.allocation_ratio),
            "max_cap": str(follower.max_contract_qty),
            "encryption_standard": "AES-256-Fernet",
        }
    )

    messages.success(
        request,
        f"Friend account '{follower.name}' securely registered and encrypted (AES-256/Fernet)."
    )
    return redirect("follower_accounts_list")


@require_http_methods(["GET", "POST"])
def follower_account_edit_view(request, account_id):
    """
    Allows editing account risk & allocation parameters.
    Secret is write-only: left blank maintains existing encrypted secret.
    """
    follower = get_object_or_404(FollowerAccount, id=account_id)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        api_key = request.POST.get("api_key", "").strip()
        new_secret = request.POST.get("api_secret", "").strip()
        
        raw_equity = request.POST.get("equity_balance", "").strip()
        raw_ratio = request.POST.get("allocation_ratio", "").strip()
        raw_max_qty = request.POST.get("max_contract_qty", "").strip()
        raw_drawdown = request.POST.get("max_drawdown_limit", "").strip()
        is_active = request.POST.get("is_active") in ["on", "true", "1", "True"]

        errors = validate_follower_input(name, api_key, new_secret, is_edit=True)

        try:
            equity_balance = Decimal(raw_equity)
            if equity_balance <= Decimal("0"):
                errors.append("Equity balance must be greater than 0.")
        except (InvalidOperation, ValueError):
            errors.append("Invalid equity balance format.")

        try:
            allocation_ratio = Decimal(raw_ratio)
            if allocation_ratio <= Decimal("0") or allocation_ratio > Decimal("10.0"):
                errors.append("Allocation ratio must be between 0.01x and 10.00x.")
        except (InvalidOperation, ValueError):
            errors.append("Invalid allocation ratio format.")

        try:
            max_contract_qty = Decimal(raw_max_qty)
            if max_contract_qty <= Decimal("0"):
                errors.append("Max contract quantity must be greater than 0.")
        except (InvalidOperation, ValueError):
            errors.append("Invalid max contract quantity format.")

        try:
            max_drawdown_limit = Decimal(raw_drawdown)
            if max_drawdown_limit <= Decimal("0"):
                errors.append("Max drawdown limit must be greater than 0.")
        except (InvalidOperation, ValueError):
            errors.append("Invalid drawdown limit format.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return redirect("follower_accounts_list")

        follower.name = name
        follower.api_key = api_key
        if new_secret:
            follower.api_secret = encrypt_secret(new_secret)
        follower.equity_balance = equity_balance
        follower.allocation_ratio = allocation_ratio
        follower.max_contract_qty = max_contract_qty
        follower.max_drawdown_limit = max_drawdown_limit
        follower.is_active = is_active
        follower.save()

        ReplicationAuditLog.objects.create(
            event_type="FOLLOWER_UPDATED",
            details={
                "account_id": follower.id,
                "name": follower.name,
                "secret_rotated": bool(new_secret),
                "equity": str(follower.equity_balance),
                "ratio": str(follower.allocation_ratio),
            }
        )

        messages.success(request, f"Updated settings for '{follower.name}'.")
        return redirect("follower_accounts_list")

    # GET request - return json for edit modal
    return JsonResponse({
        "id": follower.id,
        "name": follower.name,
        "api_key": follower.api_key,
        "masked_key": follower.masked_api_key,
        "masked_secret": follower.masked_secret,
        "equity_balance": str(follower.equity_balance),
        "allocation_ratio": str(follower.allocation_ratio),
        "max_contract_qty": str(follower.max_contract_qty),
        "max_drawdown_limit": str(follower.max_drawdown_limit),
        "is_active": follower.is_active,
        "master_id": follower.master.id,
    })


@require_POST
def follower_account_toggle_view(request, account_id):
    """
    Instantly toggles active/paused state for a follower account (HTMX friendly).
    """
    follower = get_object_or_404(FollowerAccount, id=account_id)
    follower.is_active = not follower.is_active
    follower.save(update_fields=["is_active", "updated_at"])

    ReplicationAuditLog.objects.create(
        event_type="FOLLOWER_TOGGLED",
        details={
            "account_id": follower.id,
            "name": follower.name,
            "is_active": follower.is_active,
        }
    )

    if request.headers.get("HX-Request"):
        return render(request, "replication/partials/status_badge.html", {"follower": follower})

    messages.info(
        request,
        f"Replication for '{follower.name}' is now {'ACTIVE' if follower.is_active else 'PAUSED'}."
    )
    return redirect("follower_accounts_list")


@require_POST
def follower_account_delete_view(request, account_id):
    """
    Safely removes a friend / follower account with audit log entry.
    """
    follower = get_object_or_404(FollowerAccount, id=account_id)
    name = follower.name
    follower_id = follower.id
    follower.delete()

    ReplicationAuditLog.objects.create(
        event_type="FOLLOWER_DELETED",
        details={
            "account_id": follower_id,
            "name": name,
        }
    )

    messages.warning(request, f"Account '{name}' has been deleted.")
    return redirect("follower_accounts_list")


@require_POST
def validate_credentials_syntax_view(request):
    """
    HTMX live validation endpoint to test API secret syntax without leaking credentials.
    """
    secret = request.POST.get("api_secret", "")
    info = inspect_secret_format(secret)
    return render(request, "replication/partials/secret_syntax_badge.html", {"info": info})
