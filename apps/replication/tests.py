from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from .models import MasterAccount, FollowerAccount, ReplicationOrder, ReplicationAuditLog
from .services.sizing import calculate_follower_qty
from .security import (
    encrypt_secret,
    decrypt_secret,
    mask_api_key,
    mask_api_secret,
    inspect_secret_format,
    validate_follower_input,
    ENCRYPTION_PREFIX,
)


class ReplicationSafetyAndSizingTests(TestCase):
    def test_proportional_sizing(self):
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
            api_key="test_master_key_12345",
            api_secret="test_master_secret_12345",
            is_active=True,
        )
        follower = FollowerAccount.objects.create(
            master=master,
            name="Test Follower",
            api_key="test_follower_key_12345",
            api_secret="test_follower_secret_12345",
            equity_balance=Decimal("2500.00"),
            allocation_ratio=Decimal("1.00"),
            is_active=True,
        )
        self.assertEqual(follower.equity_balance, Decimal("2500.00"))
        self.assertEqual(master.followers.count(), 1)
        # Verify secret was encrypted at rest automatically
        self.assertTrue(follower.api_secret.startswith(ENCRYPTION_PREFIX))
        self.assertEqual(follower.get_decrypted_secret(), "test_follower_secret_12345")


class SecurityAndCryptographyTests(TestCase):
    def test_encrypt_and_decrypt(self):
        raw_secret = "858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7"
        encrypted = encrypt_secret(raw_secret)
        self.assertTrue(encrypted.startswith(ENCRYPTION_PREFIX))
        self.assertNotEqual(encrypted, raw_secret)
        
        decrypted = decrypt_secret(encrypted)
        self.assertEqual(decrypted, raw_secret)

    def test_idempotent_encryption(self):
        raw_secret = "super_secret_token_1234567890"
        encrypted_once = encrypt_secret(raw_secret)
        encrypted_twice = encrypt_secret(encrypted_once)
        self.assertEqual(encrypted_once, encrypted_twice)

    def test_masking_credentials(self):
        key = "7506788c175c0601b39e24ef7173ba529529253f8591bb0b47826bd2c2a5b8fd"
        masked_k = mask_api_key(key)
        self.assertTrue(masked_k.startswith("750678"))
        self.assertTrue(masked_k.endswith("b8fd"))
        self.assertIn("••••••••", masked_k)

        raw_secret = "858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7"
        encrypted_sec = encrypt_secret(raw_secret)
        masked_s = mask_api_secret(encrypted_sec)
        self.assertTrue(masked_s.startswith("••••••••••••••••"))
        self.assertTrue(masked_s.endswith("afd7"))

    def test_secret_syntax_inspector(self):
        # 64-char Hex (Ed25519)
        hex_secret = "858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7"
        info = inspect_secret_format(hex_secret)
        self.assertTrue(info["valid"])
        self.assertEqual(info["type"], "Ed25519 Hex")
        self.assertEqual(info["strength"], "High")

        # Weak secret
        weak_info = inspect_secret_format("12345")
        self.assertFalse(weak_info["valid"])
        self.assertEqual(weak_info["type"], "Weak")

    def test_validation_rejects_placeholders_and_short_inputs(self):
        errors = validate_follower_input(
            name="A",
            api_key="123",
            api_secret="short",
        )
        self.assertGreater(len(errors), 0)


class FriendAccountsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.master = MasterAccount.objects.create(
            label="Master Test Desk",
            api_key="csp_live_master_test_key_001",
            api_secret="858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7",
            base_currency="USDT",
            is_active=True,
        )

    def test_accounts_list_view(self):
        response = self.client.get(reverse("follower_accounts_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credential Security Architecture")
        self.assertContains(response, "Link Friend Account")

    def test_create_follower_account_with_encryption(self):
        response = self.client.post(
            reverse("follower_account_create"),
            data={
                "name": "Friend Alex",
                "master_id": self.master.id,
                "api_key": "csp_live_friend_alex_key_9988",
                "api_secret": "858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7",
                "equity_balance": "2500.00",
                "allocation_ratio": "1.25",
                "max_contract_qty": "5.00",
                "max_drawdown_limit": "400.00",
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        
        follower = FollowerAccount.objects.filter(name="Friend Alex").first()
        self.assertIsNotNone(follower)
        self.assertEqual(follower.equity_balance, Decimal("2500.00"))
        self.assertEqual(follower.allocation_ratio, Decimal("1.25"))
        
        # Verify secret encrypted at rest
        self.assertTrue(follower.api_secret.startswith(ENCRYPTION_PREFIX))
        self.assertEqual(
            follower.get_decrypted_secret(),
            "858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7"
        )

        # Verify audit log was recorded with ZERO secret disclosure
        audit = ReplicationAuditLog.objects.filter(event_type="FOLLOWER_REGISTERED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details["name"], "Friend Alex")
        self.assertNotIn("858bcdbc", str(audit.details))

    def test_toggle_follower_account(self):
        follower = FollowerAccount.objects.create(
            master=self.master,
            name="Toggle Friend",
            api_key="toggle_key_12345678",
            api_secret="toggle_secret_1234567890abcdef",
            equity_balance=Decimal("1000.00"),
            is_active=True,
        )
        # Toggle to False
        response = self.client.post(
            reverse("follower_account_toggle", args=[follower.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        follower.refresh_from_db()
        self.assertFalse(follower.is_active)
        self.assertContains(response, "PAUSED")

    def test_edit_follower_account_preserves_secret_when_blank(self):
        original_secret = "858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7"
        follower = FollowerAccount.objects.create(
            master=self.master,
            name="Edit Friend",
            api_key="edit_key_12345678",
            api_secret=original_secret,
            equity_balance=Decimal("1000.00"),
        )
        # Edit equity, leaving api_secret blank
        response = self.client.post(
            reverse("follower_account_edit", args=[follower.id]),
            data={
                "name": "Edit Friend Renamed",
                "api_key": "edit_key_12345678",
                "api_secret": "",  # Blank: preserve existing
                "equity_balance": "3500.00",
                "allocation_ratio": "0.75",
                "max_contract_qty": "8.00",
                "max_drawdown_limit": "600.00",
                "is_active": "on",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        follower.refresh_from_db()
        self.assertEqual(follower.name, "Edit Friend Renamed")
        self.assertEqual(follower.equity_balance, Decimal("3500.00"))
        self.assertEqual(follower.get_decrypted_secret(), original_secret)

    def test_delete_follower_account(self):
        follower = FollowerAccount.objects.create(
            master=self.master,
            name="Delete Friend",
            api_key="delete_key_12345678",
            api_secret="delete_secret_1234567890abcdef",
            equity_balance=Decimal("1000.00"),
        )
        follower_id = follower.id
        response = self.client.post(
            reverse("follower_account_delete", args=[follower_id]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FollowerAccount.objects.filter(id=follower_id).exists())

    def test_validate_credentials_syntax_ajax(self):
        response = self.client.post(
            reverse("validate_credentials_syntax"),
            data={"api_secret": "858bcdbc747482bc01f11255f8546c9a32c7799ae1aaf731539864b061b8afd7"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ed25519 Hex")
