from pathlib import Path
import unittest
from client.green.aftersale52 import answer, facts, claim

ROOT = Path(__file__).resolve().parents[1]

class TestRelease(unittest.TestCase):
    def test_refunded_before_shipping(self):
        row = {"goods_name": "示例玫瑰", "order_status_str": "未发货",
               "after_sales_status_str": "退款成功"}
        self.assertEqual(facts(row), ("refunded", "unshipped"))
        reply = answer("我要退货", "verified", row)
        self.assertIn("已经退款", reply)
        self.assertNotIn("申请售后", reply)
        self.assertNotIn("拍照", reply)

    def test_pending_is_not_success(self):
        self.assertEqual(facts({"refund_status_str": "退款处理中"})[0], "pending")

    def test_hypothetical_is_not_a_damage_claim(self):
        self.assertFalse(claim("如果收到花枯了怎么办", []))
        self.assertTrue(claim("刚收到这盆花就蔫了", []))

    def test_web_entrypoints(self):
        for brand in ("green", "umbrella"):
            for page in (f"boss/{brand}/index.html", f"boss/{brand}/knowledge.html",
                         f"staff/{brand}/index.html"):
                self.assertIn("<title>", (ROOT/"web"/page).read_text(encoding="utf-8-sig").lower())
