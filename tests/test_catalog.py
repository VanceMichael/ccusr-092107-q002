import json
import tempfile
import unittest
from pathlib import Path

from src.catalog import load_catalog, load_roles


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(Path("fixtures/problem_catalog.json"))
        self.roles = load_roles(Path("fixtures/roles.json"))

    def test_fixture_covers_four_categories_and_five_evidence_kinds(self):
        self.assertEqual(len(self.catalog.categories), 4)
        self.assertEqual(len(self.catalog.evidence_kinds), 5)
        codes = {category.code for category in self.catalog.categories}
        self.assertEqual(
            codes,
            {
                "rules_undisclosed",
                "excessive_permission_requests",
                "incomplete_notice",
                "account_cancellation_unavailable",
            },
        )

    def test_category_declares_required_evidence(self):
        category = self.catalog.category("excessive_permission_requests")
        self.assertEqual(
            category.evidence_kinds, ("data_purpose", "permission_trigger")
        )
        with self.assertRaises(KeyError):
            self.catalog.category("not_a_category")

    def test_roles_cover_product_legal_engineering(self):
        self.assertEqual(self.roles.codes, ("product", "legal", "engineering"))
        self.assertEqual(self.roles.role("legal").name, "法务")
        with self.assertRaises(KeyError):
            self.roles.role("not_a_role")

    def test_category_referencing_unknown_evidence_kind_rejected(self):
        bad = {
            "version": 1,
            "evidence_kinds": [{"code": "notice_text", "name": "告知文本"}],
            "categories": [
                {
                    "code": "rules_undisclosed",
                    "name": "规则未公开",
                    "evidence_kinds": ["notice_text", "ghost_kind"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_catalog(path)

    def test_missing_fields_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roles.json"
            path.write_text(json.dumps({"version": 1}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_roles(path)


if __name__ == "__main__":
    unittest.main()
