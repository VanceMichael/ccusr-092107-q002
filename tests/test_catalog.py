import json
import tempfile
import unittest
from pathlib import Path

from src.catalog import load_problem_catalog, load_role_contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class CatalogTest(unittest.TestCase):
    def test_problem_catalog_lists_four_categories(self):
        catalog = load_problem_catalog(FIXTURES / "problem-catalog.json")
        self.assertEqual(
            {category.code for category in catalog},
            {
                "rules_not_published",
                "excessive_permission_requests",
                "incomplete_disclosure",
                "account_not_deletable",
            },
        )

    def test_role_contract_lists_three_roles(self):
        roles = load_role_contract(FIXTURES / "role-contract.json")
        self.assertEqual(
            {contract.role for contract in roles},
            {"product", "legal", "engineering"},
        )
        for contract in roles:
            self.assertGreaterEqual(len(contract.covers), 1)

    def test_duplicate_category_code_rejected(self):
        payload = {
            "categories": [
                {"code": "rules_not_published", "title": "规则未公开"},
                {"code": "rules_not_published", "title": "重复编码"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_problem_catalog(path)


if __name__ == "__main__":
    unittest.main()
