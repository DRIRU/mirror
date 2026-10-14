"""
Capital-Aware Position Sizing for Master-to-Follower Trade Replication.
"""

from decimal import Decimal, ROUND_DOWN
from typing import Tuple

def calculate_follower_qty(
    master_qty: Decimal,
    master_equity: Decimal,
    follower_equity: Decimal,
    allocation_ratio: Decimal = Decimal("1.0"),
    qty_step: Decimal = Decimal("0.01"),
    min_order_qty: Decimal = Decimal("0.01"),
    max_contract_cap: Decimal = Decimal("10.0")
) -> Tuple[Decimal, str]:
    """
    Computes follower quantity based on capital proportion:
        raw_qty = master_qty * (follower_equity / master_equity) * allocation_ratio
    Rounds down to the instrument's allowed step size (qty_step).
    Enforces min_order_qty and max_contract_cap.
    """
    if master_equity <= 0:
        return Decimal("0"), "Invalid master equity"
    if follower_equity <= 0:
        return Decimal("0"), "Follower has zero equity"

    equity_ratio = follower_equity / master_equity
    raw_qty = master_qty * equity_ratio * allocation_ratio

    # Round down to qty_step
    steps = (raw_qty / qty_step).quantize(Decimal("1"), rounding=ROUND_DOWN)
    scaled_qty = steps * qty_step

    if scaled_qty < min_order_qty:
        return Decimal("0"), f"Calculated quantity {scaled_qty} is below instrument minimum {min_order_qty}"

    final_qty = min(scaled_qty, max_contract_cap)
    return final_qty, "OK"

