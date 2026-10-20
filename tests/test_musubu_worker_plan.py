"""Worker plan and companies page claim helpers."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import musubu_global_queue_fetch as queue
from scripts.musubu_collect import effective_worker_plan


class WorkerPlanTests(unittest.TestCase):
    def test_companies_priority_default_five_slots(self):
        with mock.patch(
            "scripts.musubu_collect.effective_api_parallel",
            return_value=7,
        ):
            with mock.patch(
                "scripts.musubu_collect.DEFAULT_OUT",
                Path("/nonexistent"),
            ):
                plan = effective_worker_plan()
        self.assertEqual(len(plan), 7)
        self.assertEqual(plan.count("companies"), 5)
        self.assertIn("key_people", plan)
        self.assertIn("recruits", plan)


class CompaniesPageTests(unittest.TestCase):
    def test_gap_fill_skips_excluded(self):
        saved = {70, 1834, 1836}
        self.assertEqual(queue.next_companies_page(saved, set()), 1835)
        self.assertEqual(queue.next_companies_page(saved, {1835}), 1837)


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_claim_reserves_distinct_pages(self):
        with mock.patch.object(queue, "DATA", self.root):
            with mock.patch.object(queue, "saved_pages", return_value={70}):
                with mock.patch.object(queue, "latest_total_pages", return_value=1840):
                    flag = self.root / "page70.flag"
                    flag.write_text("1")
                    with mock.patch.object(queue, "COMPANIES_PAGE70_PENDING", flag):
                        skip = set(range(1, 70)) | set(range(71, 1834))
                        p1 = queue.claim_next_page("companies", 1834, [], skip)
                        p2 = queue.claim_next_page("companies", 1834, [], skip)
        self.assertEqual({p1, p2}, {1834, 1835})


if __name__ == "__main__":
    unittest.main()
