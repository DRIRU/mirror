"""
Database Models for Trade Mirror & Multi-Account Replication.
Stores Master accounts, Follower accounts, Sizing parameters, and Audit Logs.
"""

from django.db import models
from django.utils import timezone


class MasterAccount(models.Model):
    label = models.CharField(max_length=64, default="Master Trader")
    api_key = models.CharField(max_length=128, help_text="CoinSwitch PRO Master API Key")
    api_secret = models.CharField(max_length=128, help_text="Hex-encoded Ed25519 Secret Key")
    base_currency = models.CharField(max_length=16, default="USDT")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.label} ({self.api_key[:8]}...)"


class FollowerAccount(models.Model):
    master = models.ForeignKey(MasterAccount, on_delete=models.CASCADE, related_name="followers")
    name = models.CharField(max_length=64, help_text="Friend/Account Identifier")
    api_key = models.CharField(max_length=128, help_text="Follower API Key")
    api_secret = models.CharField(max_length=128, help_text="Follower Ed25519 Secret Key")
    
    # Capital Allocation & Sizing
    equity_balance = models.DecimalField(max_digits=12, decimal_places=2, default=1000.00, help_text="Allocated trading equity (USDT)")
    allocation_ratio = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, help_text="Multiplier ratio relative to equity (e.g. 1.0 = 100%)")
    max_contract_qty = models.DecimalField(max_digits=10, decimal_places=4, default=10.00, help_text="Hard maximum lot size per trade")
    max_drawdown_limit = models.DecimalField(max_digits=10, decimal_places=2, default=500.00, help_text="Stop replication if cumulative loss exceeds this")
    
    is_active = models.BooleanField(default=True, help_text="Enable/disable replication for this follower")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} [Eq: ${self.equity_balance}]"


class ReplicationOrder(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SIMULATED", "Simulated (Dry Run)"),
        ("PLACED", "Placed"),
        ("FILLED", "Filled"),
        ("FAILED", "Failed"),
        ("SKIPPED", "Skipped by Risk Rule"),
    ]

    order_link_id = models.CharField(max_length=64, unique=True)
    master_order_id = models.CharField(max_length=64, blank=True, null=True)
    symbol = models.CharField(max_length=64)
    side = models.CharField(max_length=8)  # Buy / Sell
    order_type = models.CharField(max_length=16, default="Limit")
    
    master_qty = models.DecimalField(max_digits=10, decimal_places=4)
    master_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    follower = models.ForeignKey(FollowerAccount, on_delete=models.CASCADE, related_name="replicated_orders")
    follower_qty = models.DecimalField(max_digits=10, decimal_places=4)
    follower_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING")
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.symbol} {self.side} {self.follower_qty} ({self.status}) for {self.follower.name}"


class ReplicationAuditLog(models.Model):
    event_type = models.CharField(max_length=64)
    details = models.JSONField(default=dict)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.event_type}"

