import unittest
from datetime import date

from src.workdays import add_workdays, is_workday, workdays_between


class WorkdaysTest(unittest.TestCase):
    def test_weekday_is_workday_and_weekend_is_not(self):
        self.assertTrue(is_workday(date(2026, 9, 25)))  # 周五
        self.assertFalse(is_workday(date(2026, 9, 26)))  # 周六
        self.assertFalse(is_workday(date(2026, 9, 27)))  # 周日

    def test_start_day_not_counted(self):
        self.assertEqual(add_workdays(date(2026, 9, 26), 0), date(2026, 9, 26))

    def test_skips_weekend(self):
        # 周五起算，次一工作日为下周一
        self.assertEqual(add_workdays(date(2026, 9, 25), 1), date(2026, 9, 28))

    def test_fifteen_workdays_match_rectification_deadline(self):
        # 2026-09-26（周六）起算十五个工作日，无节假日时落在 2026-10-16（周五）
        self.assertEqual(add_workdays(date(2026, 9, 26), 15), date(2026, 10, 16))

    def test_holidays_extend_deadline(self):
        holidays = {date(2026, 10, day) for day in range(1, 9)}
        self.assertEqual(
            add_workdays(date(2026, 9, 26), 15, holidays), date(2026, 10, 26)
        )

    def test_negative_count_rejected(self):
        with self.assertRaises(ValueError):
            add_workdays(date(2026, 9, 26), -1)

    def test_workdays_between(self):
        self.assertEqual(
            workdays_between(date(2026, 9, 26), date(2026, 10, 16)), 15
        )
        self.assertEqual(
            workdays_between(date(2026, 9, 26), date(2026, 9, 26)), 0
        )
        with self.assertRaises(ValueError):
            workdays_between(date(2026, 10, 16), date(2026, 9, 26))


if __name__ == "__main__":
    unittest.main()
