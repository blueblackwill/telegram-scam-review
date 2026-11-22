"""Guard the public teaching data and keep the downloadable page reproducible."""
import json
import unittest
from unittest.mock import Mock

from build_training import (
    LESSONS, ROOT, browser_payload, checked_channel, compiled_html, lesson_payload, screenshot_image,
)


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

    def test_browser_recomputes_visible_cues_and_has_no_private_history_by_default(self):
        payload = browser_payload(lesson_payload(self.raw), None)
        self.assertFalse(payload["hasLocalHistory"])
        self.assertNotIn("telegramChannel", payload)
        self.assertTrue(payload["detector"]["rules"])
        for route in payload["lessons"]:
            for stage in route["steps"]:
                self.assertNotIn("findings", stage)
                self.assertNotIn("image", stage["history"])
                self.assertNotIn("telegram", stage)

    def test_screenshot_embedding_validates_image_type(self):
        self.assertTrue(screenshot_image(ROOT / "demo.png").startswith("data:image/png;base64,"))
        with self.assertRaisesRegex(ValueError, "PNG 或 JPEG"):
            screenshot_image(ROOT / "demo.json")

    def test_teaching_screenshots_keep_their_own_reference_and_history(self):
        stages = [step["id"] for route in self.lessons for step in route["steps"]]
        history = Mock()
        history.parent = ROOT
        history.read_text.return_value = json.dumps(dict.fromkeys(stages, "demo.png"))
        telegram = Mock()
        telegram.parent = ROOT
        telegram.read_text.return_value = json.dumps({
            stage: {"file": "demo.png", "reference": f"模拟演练 {index + 1:02d}"}
            for index, stage in enumerate(stages)
        })
        channel = "https://" + "t.me/ExampleTeachingFixture"
        payload = browser_payload(lesson_payload(self.raw), history, telegram, channel)
        self.assertEqual(payload["telegramChannel"], channel)
        for index, step in enumerate(step for route in payload["lessons"] for step in route["steps"]):
            self.assertIn("image", step["history"])
            self.assertEqual(step["telegram"]["reference"], f"模拟演练 {index + 1:02d}")
            self.assertEqual(step["telegram"]["image"], step["history"]["image"])
            self.assertNotIn("file", step["telegram"])
        telegram.read_text.return_value = "{}"
        with self.assertRaisesRegex(ValueError, "每一关"):
            browser_payload(lesson_payload(self.raw), None, telegram)

    def test_channel_only_accepts_plain_public_profile_url(self):
        base = "https://" + "t.me/"
        for invalid in (
            base + "+InviteToken", base + "joinchat", base + "proxy",
            base + "ExampleTeachingFixture/12", base + "ExampleTeachingFixture?start=payload",
            "https://t.me.example.invalid/ExampleTeachingFixture",
            "http://" + "t.me/ExampleTeachingFixture",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "公开演练频道链接"):
                    checked_channel(invalid)

    def test_downloadable_page_matches_source(self):
        published = (ROOT / "training.html").read_text(encoding="utf-8")
        self.assertEqual(published, compiled_html())


if __name__ == "__main__":
    unittest.main()
