"""Exercise the real Telegram message payloads with no network access."""

from collections import deque
import unittest

from build_training import LESSONS, lesson_payload
from telegram_classroom import Classroom, HEADER


def callbacks(screen):
    return [button for row in screen["reply_markup"]["inline_keyboard"] for button in row]


class ClassroomTests(unittest.TestCase):
    def setUp(self):
        self.classroom = Classroom()
        self.lessons = lesson_payload(LESSONS.read_text(encoding="utf-8"))["lessons"]

    def open(self, button):
        screen = self.classroom.screen(button["callback_data"])
        self.assertIsNotNone(screen)
        return screen

    def test_two_realistic_routes_gate_completion_on_correct_choices(self):
        menu = self.classroom.screen()
        for route_index, lesson in enumerate(self.lessons):
            screen = self.open(callbacks(menu)[route_index])
            for index, step in enumerate(lesson["steps"], 1):
                self.assertIn(f"{index}/{len(lesson['steps'])}", screen["text"])
                self.assertNotIn("✅ 通关", screen["text"])
                inspect, _ = callbacks(screen)
                self.assertTrue(inspect["text"].startswith("查看"))
                evidence = self.open(inspect)
                self.assertIn(step["sourceNote"]["observed"], evidence["text"])
                self.assertIn("E1", evidence["text"])

                correct = next(choice for choice in step["choices"] if choice["correct"])
                wrong = next(choice for choice in step["choices"] if not choice["correct"])
                choices = {button["text"]: button for button in callbacks(evidence)}
                warning = self.open(choices[wrong["label"]])
                self.assertIn("⚠️ 模拟受骗 · 请提高警惕", warning["text"])
                self.assertIn(step["sourceNote"]["unverified"], warning["text"])
                self.assertNotIn("✅ 通关", warning["text"])
                self.assertEqual([item["text"] for item in callbacks(warning)], ["重试这一步", "回路线入口"])
                self.assertEqual(self.open(callbacks(warning)[0]), evidence)

                result = self.open(choices[correct["label"]])
                self.assertIn(correct["feedback"], result["text"])
                if index < len(lesson["steps"]):
                    self.assertIn("✅ 核对正确", result["text"])
                    self.assertNotIn("✅ 通关", result["text"])
                    self.assertTrue(callbacks(result)[0]["text"].startswith("下一步"))
                    screen = self.open(callbacks(result)[0])
                else:
                    self.assertIn(f"✅ 通关 · {lesson['title']}", result["text"])
                    self.assertIn("本路线复盘", result["text"])
                    menu = self.open(callbacks(result)[0])
                    self.assertIn(f"已通关 {route_index + 1} / 2", menu["text"])
                    if route_index == 1:
                        self.assertIn("两条路线均已通关", result["text"])
        self.assertEqual(self.open(callbacks(menu)[-1]), self.classroom.screen())

    def test_all_accessible_views_keep_the_simulation_banner_and_inert_navigation(self):
        pending = deque([None])
        seen = set()
        while pending:
            target = pending.popleft()
            if target in seen:
                continue
            seen.add(target)
            scene = self.classroom.screen(target)
            self.assertIsNotNone(scene)
            self.assertTrue(scene["text"].startswith(HEADER))
            self.assertLess(len(scene["text"]), 4096)
            self.assertNotRegex(scene["text"], r"(?:https?://|tg://|@[\w]{4,})")
            for item in callbacks(scene):
                self.assertEqual(set(item), {"text", "callback_data"})
                self.assertLessEqual(len(item["callback_data"].encode()), 64)
                pending.append(item["callback_data"])
        self.assertGreater(len(seen), 60)

    def test_unknown_callbacks_and_caller_mutation_do_not_change_the_lesson(self):
        for unknown in ("start", "lesson:gift:0:-1", "lesson:gift:0:0:unknown", ["fake"], "a" * 65):
            with self.subTest(unknown=unknown):
                self.assertIsNone(self.classroom.screen(unknown))
        payload = self.classroom.screen()
        payload["reply_markup"]["inline_keyboard"].clear()
        self.assertEqual(len(callbacks(self.classroom.screen())), 2)

    def test_inspection_shows_toy_records_separately_from_history(self):
        expected = {
            "lesson:gift:0:0:inspect": ("余额：0 课堂点", "课堂红包：3 课堂点"),
            "lesson:gift:0:1:inspect": ("课堂页显示余额：3 课堂点",),
            "lesson:gift:0:2:inspect": ("3 课堂点 · 已暂停",),
            "lesson:gift:0:3:inspect": ("假设授权额度：20 课堂点",),
            "lesson:shop:0:0:inspect": ("ZZ-001 · 4 课堂点 · 待支付",),
            "lesson:shop:0:1:inspect": ("聊天 → 外部网页（模拟）",),
            "lesson:shop:0:2:inspect": ("课堂订单：ZZ-001", "模拟应付：4 课堂点 · 待支付"),
            "lesson:shop:0:3:inspect": ("ZZ-001 · 4 课堂点 · 待支付", "20 课堂点"),
        }
        for target, fragments in expected.items():
            with self.subTest(target=target):
                rendering = self.classroom.screen(target)["text"]
                toy, history = rendering.split("历史画面\n", 1)
                self.assertIn("课堂模拟记录", toy)
                self.assertTrue(history.startswith("#"))
                self.assertNotIn("orders.example.invalid", rendering)
                for fragment in fragments:
                    self.assertIn(fragment, toy)

if __name__ == "__main__":
    unittest.main()
