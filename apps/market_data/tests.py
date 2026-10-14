from django.test import TestCase, Client
from django.urls import reverse


class MobileOptionsChainTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_options_chain_view_mobile_elements(self):
        """Test that options chain dashboard loads with all Stitch mobile components."""
        response = self.client.get(reverse("options_chain"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # 1. Responsive Viewport Meta
        self.assertIn("viewport-fit=cover", content)

        # 2. Mobile Ticker & Metrics Sub-Header
        self.assertIn("BTC Index", content)
        self.assertIn("PCR:", content)

        # 3. Mobile Segmented View Control [Calls | Both | Puts]
        self.assertIn("mobileMode = 'calls'", content)
        self.assertIn("mobileMode = 'both'", content)
        self.assertIn("mobileMode = 'puts'", content)

        # 4. Mobile Fixed Bottom Navigation Bar
        self.assertIn("md:hidden fixed bottom-0", content)
        self.assertIn("Chain", content)
        self.assertIn("Mirror", content)

        # 5. Mobile Slide-Up Drawer Sheet & Backdrop
        self.assertIn("mobile-sheet-enter", content)
        self.assertIn("Selected Strike:", content)
        self.assertIn("bg-gray-600 rounded-full", content)  # Mobile drag handle

    def test_chain_table_partial_mobile_matrix(self):
        """Test that chain table partial returns both Desktop and Mobile matrices."""
        response = self.client.get(reverse("chain_table"), {"expiry": "23OCT26"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # 1. Desktop Matrix container
        self.assertIn("hidden lg:block", content)
        self.assertIn("CALLS (Long Volatility / Bullish)", content)

        # 2. Mobile Matrix container
        self.assertIn("block lg:hidden", content)
        self.assertIn("mobileMode === 'both'", content)
        self.assertIn("mobileMode === 'calls'", content)
        self.assertIn("mobileMode === 'puts'", content)

        # 3. Mobile Table headers
        self.assertIn("C. BID", content)
        self.assertIn("C. ASK", content)
        self.assertIn("P. BID", content)
        self.assertIn("P. ASK", content)

    def test_contract_drawer_partial_call_side(self):
        """Test that contract drawer when touching Call side loads Call-only focused view."""
        response = self.client.get(reverse("contract_drawer"), {
            "call": "BTC-23OCT26-98000-C-USDT",
            "put": "BTC-23OCT26-98000-P-USDT",
            "strike": "98,000",
            "side": "call",
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # 1. Strike header & Call badge
        self.assertIn("98,000", content)
        self.assertIn("CALL", content)
        self.assertIn("BTC-23OCT26-98000-C-USDT", content)

        # 2. Quick switch to Put
        self.assertIn("View <strong>PUT</strong> Details", content)

        # 3. Un-cluttered Pricing & Greeks Bento Grid
        self.assertIn("Best Bid", content)
        self.assertIn("Best Ask", content)
        self.assertIn("Delta (Δ)", content)
        self.assertIn("Gamma (Γ)", content)
        self.assertIn("Theta (θ)", content)
        self.assertIn("Vega (ν)", content)

        # 4. Trade Mirror Simulation
        self.assertIn("Trade Mirror Simulation", content)
        self.assertIn("Unwired", content)

    def test_contract_drawer_partial_put_side(self):
        """Test that contract drawer when touching Put side loads Put-only focused view."""
        response = self.client.get(reverse("contract_drawer"), {
            "call": "BTC-23OCT26-98000-C-USDT",
            "put": "BTC-23OCT26-98000-P-USDT",
            "strike": "98,000",
            "side": "put",
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")

        # 1. Strike header & Put badge
        self.assertIn("98,000", content)
        self.assertIn("PUT", content)
        self.assertIn("BTC-23OCT26-98000-P-USDT", content)

        # 2. Quick switch to Call
        self.assertIn("View <strong>CALL</strong> Details", content)

        # 3. Pricing & Greeks
        self.assertIn("Best Bid", content)
        self.assertIn("Best Ask", content)
        self.assertIn("Delta (Δ)", content)

    def test_trade_mirror_replication_overview(self):
        """Test that trade mirror replication overview is operational."""
        response = self.client.get(reverse("replication_overview"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Safety Status: Execution Routes Unwired", content)
        self.assertIn("Capital-Aware Replication Formula", content)

