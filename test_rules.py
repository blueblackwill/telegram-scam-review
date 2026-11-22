"""Synthetic regression checks for offline OCR cue classification."""

import json
import math
import unittest

from rules import detect


def line(text, box=None, confidence=0.8):
    return {"text": text, "box": box, "confidence": confidence}


def indexed(*lines):
    return {item["rule"]: item for item in detect(list(lines))}


class DetectorTests(unittest.TestCase):
    def test_checkout_and_paid_label_remain_separate(self):
        items = indexed(
            line("待 支 付 1.30 USDT"),
            line("支付中心"),
            line("請打開錢包 App 支付"),
            line("TRC - 20"),
            line("付款成功"),
        )
        self.assertEqual(items["order_pending"]["status"], "observed")
        self.assertEqual(items["checkout_page"]["status"], "observed")
        self.assertEqual(items["payment_request"]["status"], "observed")
        self.assertEqual(items["network_label"]["status"], "observed")
        self.assertEqual(items["token_amount"]["grade"], "E1")
        self.assertEqual(items["payment_success_claim"]["status"], "pending")
        self.assertEqual(items["payment_success_claim"]["grade"], "E1")
        self.assertNotIn("payment_success_claim", indexed(line("未支付成功")))

    def test_approval_and_wallet_connection_are_pending(self):
        items = indexed(
            line("點擊前往綁定"),
            line("金额核对后发起授\u200b权"),
            line("withdrawal  amount"),
        )
        self.assertEqual(items["wallet_binding"]["status"], "pending")
        self.assertEqual(items["authorization_text"]["status"], "pending")
        self.assertEqual(items["withdrawal_prompt"]["status"], "observed")
        self.assertIn("withdrawal_prompt", indexed(line("请回复要提现的金额")))
        self.assertNotIn("authorization_text", indexed(line("普通客服展示连接钱包")))

    def test_inline_and_forward_sources_are_separate(self):
        items = indexed(
            line("機器人"),
            line("via ＠synthetic_shop_bot"),
            line("Forwarded  from synthetic sender"),
            line("请联系您的专属客服：@synthetic_support"),
        )
        self.assertEqual(
            set(items),
            {"bot_label", "inline_attribution", "forward_origin", "support_label"},
        )
        self.assertTrue(all(item["category"] == "bot" for item in items.values()))

    def test_url_cues_are_static_and_report_contains_no_raw_values(self):
        raw = [
            line("打开此链接？"),
            line("https://merchant.example.org@fake.example.invalid/k=demo"),
            line("网址：https://專門.example.invalid"),
            line("via @synthetic_bot"),
            line("交易哈希：DEMO-SENSITIVE-FAKE-VALUE"),
        ]
        items = indexed(*raw)
        self.assertIn("external_link_prompt", items)
        self.assertIn("visible_address", items)
        self.assertEqual(items["address_format_review"]["status"], "pending")
        self.assertEqual(items["transaction_identifier_label"]["status"], "pending")
        serialized = json.dumps(items, ensure_ascii=False)
        for value in (
            "merchant.example.org", "fake.example.invalid", "k=demo",
            "synthetic_bot", "DEMO-SENSITIVE-FAKE-VALUE",
        ):
            self.assertNotIn(value, serialized)

    def test_url_path_not_treated_as_interface_cue(self):
        items = indexed(line("https://checkout.example.invalid/payment"))
        self.assertEqual(set(items), {"visible_address"})

    def test_normal_store_has_observed_cues_without_pending_findings(self):
        items = indexed(
            line("Telegram bot"),
            line("https://merchant.example.org/"),
            line("Checkout"),
            line("Pay now"),
        )
        self.assertEqual(
            set(items), {"bot_label", "visible_address", "checkout_page", "payment_request"}
        )
        self.assertTrue(all(item["status"] == "observed" for item in items.values()))

    def test_only_one_frame_finding_and_keep_stronger_locator(self):
        stronger = [0.1, 0.4, 0.6, 0.1]
        items = indexed(
            line("支付中心", confidence=1),
            line("支付中心", box=[0.3, 0.2, 0.3, 0.1], confidence=0.4),
            line("收銀台", box=stronger, confidence=0.9),
        )
        self.assertEqual(list(items), ["checkout_page"])
        self.assertEqual(items["checkout_page"]["box"], stronger)

    def test_invalid_box_and_malformed_url_are_isolated(self):
        items = indexed(
            None,
            {"text": False},
            line("https://[not-a-valid-host"),
            line("机器人", box=[0.1, 0.2, math.nan, 0.1]),
        )
        self.assertEqual(list(items), ["bot_label"])
        self.assertIsNone(items["bot_label"]["box"])


if __name__ == "__main__":
    unittest.main()

