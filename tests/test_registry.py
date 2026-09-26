import unittest
from datetime import datetime

from src.registry import VersionRegistry, VersionSlot


def slot(app_id="app-x", version="1.0.0", channel="android_market", stage="full", online_from="2026-08-01T10:00:00"):
    return VersionSlot(
        app_id=app_id,
        version=version,
        channel=channel,
        stage=stage,
        online_from=datetime.fromisoformat(online_from),
    )


class VersionRegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = VersionRegistry()
        self.registry.publish(slot(version="1.0.0", online_from="2026-08-01T10:00:00"))
        self.registry.publish(slot(version="2.0.0", online_from="2026-09-01T10:00:00"))
        self.registry.publish(slot(version="2.1.0", stage="gray", online_from="2026-09-10T10:00:00"))

    def versions_at(self, when):
        return {s.version for s in self.registry.online_at("app-x", datetime.fromisoformat(when))}

    def test_multiple_versions_online_simultaneously(self):
        self.assertEqual(self.versions_at("2026-09-05T00:00:00"), {"1.0.0", "2.0.0"})
        # 灰度版与全量版、旧版同时在线
        self.assertEqual(self.versions_at("2026-09-11T00:00:00"), {"1.0.0", "2.0.0", "2.1.0"})

    def test_retire_does_not_rewrite_history(self):
        self.registry.retire("app-x", "1.0.0", "android_market", datetime(2026, 9, 15, 10))
        self.assertEqual(self.versions_at("2026-09-16T00:00:00"), {"2.0.0", "2.1.0"})
        # 下架前的历史时刻仍能看到旧版在线
        self.assertEqual(self.versions_at("2026-09-05T00:00:00"), {"1.0.0", "2.0.0"})
        self.assertEqual(len(self.registry.slots()), 3)

    def test_retire_requires_online_version(self):
        with self.assertRaises(ValueError):
            self.registry.retire("app-x", "9.9.9", "android_market", datetime(2026, 9, 15))
        # 已下架的版本不能再次下架
        self.registry.retire("app-x", "1.0.0", "android_market", datetime(2026, 9, 15, 10))
        with self.assertRaises(ValueError):
            self.registry.retire("app-x", "1.0.0", "android_market", datetime(2026, 9, 16, 10))

    def test_duplicate_publish_rejected(self):
        with self.assertRaises(ValueError):
            self.registry.publish(slot(version="1.0.0", online_from="2026-08-01T10:00:00"))

    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError):
            self.registry.publish(slot(version="3.0.0", stage="beta"))


if __name__ == "__main__":
    unittest.main()
