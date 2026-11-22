#!/usr/bin/env python3
"""Compile the offline teaching lab with the same rules used for evidence review."""
import argparse
import json
from pathlib import Path
import re
import sys

from rules import detect

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "training" / "index.template.html"
LESSONS = ROOT / "training" / "lessons.json"
PLACEHOLDER = "__TRAINING_PAYLOAD__"
LIVE_POINTER = re.compile(
    r"(?:https?://|tg://|walletconnect:|tonconnect:|\bt\.me/|@[A-Za-z0-9_]{4,})",
    re.IGNORECASE,
)
CATEGORIES = {"bot", "link", "payment", "approval"}


def detector_findings(rows):
    count = len(rows)
    # Normalized regions index the rows of the fictional evidence board, not image pixels.
    positions = [(index + 0.15) / count for index in range(count)]
    lines = [
        {"text": row["text"], "box": [0.035, y, 0.93, 0.68 / count], "confidence": 1.0}
        for row, y in zip(rows, positions)
    ]
    clues = []
    for result in detect(lines):
        box = result["box"]
        row = min(count - 1, int(box[1] * count)) if box is not None else None
        clues.append({
            "rule": result["rule"], "category": result["category"], "title": result["title"],
            "summary": result["summary"], "status": result["status"], "grade": result["grade"],
            "row": row, "method": "detector",
        })
    return clues


def enrich_step(step):
    rows = step["evidence"]
    if not rows:
        raise ValueError(f"{step['id']} has no teaching evidence")
    if any(not isinstance(row["text"], str) or not row["text"].strip() for row in rows):
        raise ValueError(f"{step['id']} has an empty evidence row")
    choices = step["choices"]
    if len(choices) < 2 or sum(choice["correct"] is True for choice in choices) != 1:
        raise ValueError(f"{step['id']} needs exactly one correct choice")
    if len({choice["id"] for choice in choices}) != len(choices):
        raise ValueError(f"{step['id']} has duplicate choice IDs")
    clues = detector_findings(rows)
    if not clues:
        raise ValueError(f"{step['id']} has no current detector match")
    for gap in step["missing"]:
        if gap["category"] not in CATEGORIES:
            raise ValueError(f"{step['id']} has an unknown evidence category")
        clues.append({**gap, "grade": "E0", "status": "pending", "row": None, "method": "gap"})
    return {**step, "findings": clues}


def lesson_payload(raw):
    if LIVE_POINTER.search(raw):
        raise ValueError("The public teaching data must not contain live links or account handles")
    data = json.loads(raw)
    seen = set()
    routes = []
    for lesson in data["lessons"]:
        if lesson["id"] in seen or not lesson["steps"]:
            raise ValueError("Lesson IDs must be unique and each lesson needs stages")
        seen.add(lesson["id"])
        steps = [enrich_step(step) for step in lesson["steps"]]
        if len({step["id"] for step in steps}) != len(steps):
            raise ValueError(f"{lesson['id']} has duplicate stage IDs")
        routes.append({**lesson, "steps": steps})
    if not routes:
        raise ValueError("No teaching routes found")
    return {**data, "lessons": routes}


def compiled_html():
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError("The template must contain exactly one payload placeholder")
    data = lesson_payload(LESSONS.read_text(encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", r"\u003c")
    return template.replace(PLACEHOLDER, payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "training.html")
    parser.add_argument("--check", action="store_true", help="核对已生成的文件，不写入")
    args = parser.parse_args()

    try:
        expected = compiled_html()
        if args.check:
            if not args.output.is_file() or args.output.read_text(encoding="utf-8") != expected:
                print(f"需要重新生成：{args.output}", file=sys.stderr)
                return 1
            print(f"生成物与案例、检测规则一致：{args.output}")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(expected, encoding="utf-8")
            print(f"用浏览器打开：{args.output}")
    except (OSError, KeyError, ValueError, TypeError) as exc:
        print(f"教学构建失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
