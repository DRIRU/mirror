from decimal import Decimal
from django.test import TestCase
from .models import MasterAccount, FollowerAccount, ReplicationOrder
from .services.sizing import calculate_follower_qty


class ReplicationSafetyAndSizingTests(TestCase):
    def test_proportional_sizing(self):
        # Master Equity: 10,000 USDT, Follower Equity: 5,000 USDT (50%)
        # Master Order: 1.0 BTC, Allocation Ratio: 1.0x -> Follower Order: 0.50 BTC
        qty, msg = calculate_follower_qty(
            master_qty=Decimal("1.0"),
            master_equity=Decimal("10000.0"),
            follower_equity=Decimal("5000.0"),
            allocation_ratio=Decimal("1.0"),
            qty_step=Decimal("0.01"),
            min_order_qty=Decimal("0.01"),
            max_contract_cap=Decimal("10.0"),
        )
        self.assertEqual(qty, Decimal("0.50"))
        self.assertEqual(msg, "OK")

    def test_qty_step_rounding(self):
        # 0.33333 -> should round down to 0.33 based on 0.01 step
        qty, msg = calculate_follower_qty(
            master_qty=Decimal("1.0"),
            master_equity=Decimal("3000.0"),
            follower_equity=Decimal("1000.0"),
            allocation_ratio=Decimal("1.0"),
            qty_step=Decimal("0.01"),
            min_order_qty=Decimal("0.01"),
            max_contract_cap=Decimal("10.0"),
        )
        self.assertEqual(qty, Decimal("0.33"))
        self.assertEqual(msg, "OK")

    def test_max_contract_cap(self):
        # Proportional size 2.0 exceeds cap 1.5 -> clamped to 1.5
        qty, msg = calculate_follower_qty(
            master_qty=Decimal("1.0"),
            master_equity=Decimal("5000.0"),
            follower_equity=Decimal("10000.0"),
            allocation_ratio=Decimal("1.0"),
            qty_step=Decimal("0.01"),
            min_order_qty=Decimal("0.01"),
            max_contract_cap=Decimal("1.5"),
        )
        self.assertEqual(qty, Decimal("1.5"))
        self.assertEqual(msg, "OK")

    def test_model_creation_safety(self):
        master = MasterAccount.objects.create(
            label="Test Master",
            api_key="test_key",
            api_secret="test_secret",
            is_active=True,
        )
        follower = FollowerAccount.objects.create(
            master=master,
            name="Test Follower",
            api_key="f_key",
            api_secret="f_secret",
            equity_balance=Decimal("2500.00"),
            allocation_ratio=Decimal("1.00"),
            is_active=True,
        )
        self.assertEqual(follower.equity_balance, Decimal("2500.00"))
        self.assertEqual(master.followers.count(), 1)

