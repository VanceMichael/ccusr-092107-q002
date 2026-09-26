import unittest
from datetime import datetime
from pathlib import Path

from src.catalog import load_role_contract
from src.signoff import SignoffBook

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class SignoffBookTest(unittest.TestCase):
    def setUp(self):
        roles = load_role_contract(FIXTURES / "role-contract.json")
        self.book = SignoffBook(roles)

    def sign(self, role, round_no, conclusion="结论"):
        return self.book.sign(
            "item-001", role, round_no, conclusion, f"{role}-demo-1", datetime(2026, 9, 10, 9)
        )

    def test_each_role_signs_its_own_conclusion(self):
        self.sign("product", 1, "产品结论")
        self.assertFalse(self.book.is_complete("item-001", 1))
        self.sign("legal", 1, "法务结论")
        self.sign("engineering", 1, "研发结论")
        self.assertTrue(self.book.is_complete("item-001", 1))
        conclusions = {record.role: record.conclusion for record in self.book.history("item-001")}
        self.assertEqual(
            conclusions,
            {"product": "产品结论", "legal": "法务结论", "engineering": "研发结论"},
        )

    def test_same_role_same_round_cannot_overwrite(self):
        self.sign("product", 1, "原始结论")
        with self.assertRaises(ValueError):
            self.sign("product", 1, "改写结论")
        self.assertEqual(self.book.history("item-001")[0].conclusion, "原始结论")

    def test_retest_failure_opens_new_round_without_erasing_old(self):
        for role in ("product", "legal", "engineering"):
            self.sign(role, 1, "第一轮结论")
        # 复测失败后开启第二轮,第一轮结论完整保留
        self.sign("product", 2, "第二轮结论")
        self.assertFalse(self.book.is_complete("item-001", 2))
        self.assertTrue(self.book.is_complete("item-001", 1))
        self.assertEqual(len(self.book.history("item-001")), 4)

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            self.sign("marketing", 1)


if __name__ == "__main__":
    unittest.main()
