"""
Replication Coordinator Service (Isolated from Web UI).
Handles idempotent multi-account replication logic and dry-run simulations.
"""

import uuid
from decimal import Decimal
from typing import Dict, Any, List
from django.utils import timezone
from ..models import MasterAccount, FollowerAccount, ReplicationOrder, ReplicationAuditLog
from .sizing import calculate_follower_qty


class ReplicationEngine:
    def __init__(self, master: MasterAccount, dry_run: bool = True):
        self.master = master
        self.dry_run = dry_run

    def replicate_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        master_qty: Decimal,
        master_price: Decimal = None,
        master_equity: Decimal = Decimal("10000.00"),
        qty_step: Decimal = Decimal("0.01"),
        min_order_qty: Decimal = Decimal("0.01"),
    ) -> List[Dict[str, Any]]:
        """
        Calculates and creates replicated order records for all active followers.
        In dry_run mode, orders are recorded with status SIMULATED without hitting POST endpoints.
        """
        active_followers = self.master.followers.filter(is_active=True)
        results = []

        ReplicationAuditLog.objects.create(
            event_type="REPLICATION_TRIGGERED",
            details={
                "master": self.master.label,
                "symbol": symbol,
                "side": side,
                "master_qty": str(master_qty),
                "follower_count": active_followers.count(),
                "dry_run": self.dry_run,
            }
        )

        for follower in active_followers:
            qty, reason = calculate_follower_qty(
                master_qty=master_qty,
                master_equity=master_equity,
                follower_equity=follower.equity_balance,
                allocation_ratio=follower.allocation_ratio,
                qty_step=qty_step,
                min_order_qty=min_order_qty,
                max_contract_cap=follower.max_contract_qty,
            )

            link_id = f"CS-REP-{uuid.uuid4().hex[:12].upper()}"

            if reason != "OK":
                rep_order = ReplicationOrder.objects.create(
                    order_link_id=link_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    master_qty=master_qty,
                    master_price=master_price,
                    follower=follower,
                    follower_qty=Decimal("0"),
                    follower_price=master_price,
                    status="SKIPPED",
                    error_message=reason,
                )
                results.append({"follower": follower.name, "status": "SKIPPED", "reason": reason})
                continue

            # Record simulated or prepared order
            rep_order = ReplicationOrder.objects.create(
                order_link_id=link_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                master_qty=master_qty,
                master_price=master_price,
                follower=follower,
                follower_qty=qty,
                follower_price=master_price,
                status="SIMULATED" if self.dry_run else "PENDING",
            )

            results.append({
                "follower": follower.name,
                "status": rep_order.status,
                "allocated_qty": str(qty),
                "order_link_id": link_id,
            })

        return results

