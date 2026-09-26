import unittest
from datetime import datetime

from src.evidence import EVIDENCE_CATEGORIES, Evidence, EvidenceLedger


def evidence(evidence_id, category, effective_from, summary="摘要"):
    return Evidence(
        evidence_id=evidence_id,
        item_id="item-001",
        app_id="app-001",
        version="2.3.0",
        channel="android_market",
        category=category,
        captured_at=datetime(2026, 9, 8, 10),
        effective_from=datetime.fromisoformat(effective_from),
        summary=summary,
        source="页面存档",
    )


class EvidenceLedgerTest(unittest.TestCase):
    def test_records_all_five_categories(self):
        ledger = EvidenceLedger()
        for index, category in enumerate(EVIDENCE_CATEGORIES):
            ledger.record(evidence(f"ev-{index:04d}", category, "2026-09-08T10:00:00"))
        self.assertEqual(len(ledger.for_item("item-001")), 5)

    def test_unknown_category_rejected(self):
        ledger = EvidenceLedger()
        with self.assertRaises(ValueError):
            ledger.record(evidence("ev-0001", "location_tracking", "2026-09-08T10:00:00"))

    def test_duplicate_id_rejected(self):
        ledger = EvidenceLedger()
        ledger.record(evidence("ev-0001", "data_purpose", "2026-09-08T10:00:00"))
        with self.assertRaises(ValueError):
            ledger.record(evidence("ev-0001", "data_purpose", "2026-09-09T10:00:00"))

    def test_disclosure_at_selects_text_effective_at_that_time(self):
        ledger = EvidenceLedger()
        ledger.record(evidence("ev-0001", "disclosure_text", "2026-08-20T10:00:00", "告知文本v1"))
        ledger.record(evidence("ev-0002", "disclosure_text", "2026-09-15T09:00:00", "告知文本v2"))
        # 09-10 用户看到的是 v1,09-20 看到的是 v2
        self.assertEqual(
            ledger.disclosure_at("app-001", "2.3.0", "android_market", datetime(2026, 9, 10)).summary,
            "告知文本v1",
        )
        self.assertEqual(
            ledger.disclosure_at("app-001", "2.3.0", "android_market", datetime(2026, 9, 20)).summary,
            "告知文本v2",
        )

    def test_disclosure_at_isolates_versions(self):
        ledger = EvidenceLedger()
        ledger.record(evidence("ev-0001", "disclosure_text", "2026-08-20T10:00:00", "告知文本v1"))
        self.assertIsNone(
            ledger.disclosure_at("app-001", "9.9.9", "android_market", datetime(2026, 9, 20))
        )


if __name__ == "__main__":
    unittest.main()
