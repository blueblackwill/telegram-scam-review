from pathlib import Path
import subprocess
import sys
import unittest

from build_training import LESSONS, lesson_payload


class TrainingBotTests(unittest.TestCase):
    def run_bot(self, commands, *args):
        return subprocess.run(
            [sys.executable, "-B", str(Path(__file__).with_name("training_bot.py")), *args],
            input=commands, text=True, encoding="utf-8", capture_output=True, check=True,
        ).stdout

    def test_each_route_reports_the_same_findings_as_the_training_data(self):
        routes = lesson_payload(LESSONS.read_text(encoding="utf-8"))["lessons"]
        for route in routes:
            with self.subTest(route=route["id"]):
                output = self.run_bot("\n" * len(route["steps"]), "--route", route["id"])
                self.assertIn("【模拟演练】纸舟课堂", output)
                completion = output.index("本路线已走完")
                last_position = 0
                for number, step in enumerate(route["steps"], start=1):
                    header = output.index(f"【模拟演练】{number}/", last_position)
                    boundary = output.index("【模拟演练】", header + 1)
                    stage = output[header:boundary]
                    action = stage.index(step["action"])
                    point = stage.index(f"课堂进度 +1 点（{number}/", action)
                    for clue in step["findings"]:
                        status = "待核" if clue["status"] == "pending" else "可见线索"
                        row = clue["row"]
                        location = "" if row is None else f"｜材料 {row + 1}"
                        label = f"[{status} {clue['grade']}{location}] {clue['title']}"
                        self.assertIn(label, stage[point:])
                    last_position = boundary
                self.assertLess(last_position, completion)

    def test_menu_rejects_unrecognized_input_and_quit_has_no_findings(self):
        output = self.run_bot("?\n2\nq\n")
        self.assertIn("请输入上面列出的路线编号", output)
        self.assertIn("纸舟课堂｜商铺与订单", output)
        self.assertNotIn("课堂进度 +1", output)
        self.assertNotIn("本路线已走完", output)


if __name__ == "__main__":
    unittest.main()
