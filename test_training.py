"""Guard the public teaching data and keep the downloadable page reproducible."""
import unittest

from build_training import LESSONS, ROOT, compiled_html, lesson_payload


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = LESSONS.read_text(encoding="utf-8")
        cls.lessons = lesson_payload(cls.raw)["lessons"]

    def test_every_stage_has_a_detected_cue_and_locatable_evidence(self):
        self.assertEqual([len(route["steps"]) for route in self.lessons], [4, 4])
        categories = set()
        for route in self.lessons:
            for step in route["steps"]:
                clues = [f for f in step["findings"] if f["method"] == "detector"]
                self.assertTrue(clues, step["id"])
                for clue in clues:
                    categories.add(clue["category"])
                    self.assertEqual(clue["grade"], "E1")
                    self.assertIsInstance(clue["row"], int)
                    self.assertIn(clue["row"], range(len(step["evidence"])))
        self.assertEqual(categories, {"bot", "link", "payment", "approval"})

    def test_missing_evidence_is_pending(self):
        gaps = [f for route in self.lessons for step in route["steps"]
                for f in step["findings"] if f["method"] == "gap"]
        self.assertTrue(gaps)
        self.assertTrue(all(f["status"] == "pending" and f["grade"] == "E0" for f in gaps))
        self.assertTrue(all(f["row"] is None for f in gaps))

    def test_public_teaching_data_rejects_live_pointers(self):
        with self.assertRaisesRegex(ValueError, "live links"):
            lesson_payload(self.raw.replace('\"title\":', '\"external\":\"https://example.invalid\",\"title\":', 1))

    def test_downloadable_page_matches_source(self):
        published = (ROOT / "training.html").read_text(encoding="utf-8")
        self.assertEqual(published, compiled_html())


if __name__ == "__main__":
    unittest.main()
