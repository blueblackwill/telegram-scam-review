#!/usr/bin/env python3
"""Compile the offline teaching lab with the same rules used for evidence review."""
import argparse
import base64
import json
from pathlib import Path
import re
import sys

from rules import DOMAIN_PATTERN, EXACT_LABELS, NEGATED_PREFIXES, RULES, detect

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "training" / "index.template.html"
DETECTOR = ROOT / "training" / "detector.js"
LESSONS = ROOT / "training" / "lessons.json"
PLACEHOLDER = "__TRAINING_PAYLOAD__"
DETECTOR_PLACEHOLDER = "/*__TRAINING_DETECTOR__*/"
MAX_SCREENSHOT_BYTES = 4 * 1024 * 1024
PUBLIC_CHANNEL = re.compile(r"https://t\.me/([A-Za-z][A-Za-z0-9_]{4,31})", re.ASCII)
TELEGRAM_ROUTES = {"addemoji", "addlist", "addstickers", "addtheme", "boost", "confirmphone",
                   "giftcode", "invoice", "joinchat", "login", "passport", "proxy",
                   "setlanguage", "share", "socks"}
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
    if not isinstance(step["action"], str) or not step["action"].strip():
        raise ValueError(f"{step['id']} has no simulation operation")
    history = step["history"]
    if set(history) != {"reference", "caption", "fallback"} or not all(
        isinstance(value, str) and value.strip() for value in history.values()
    ):
        raise ValueError(f"{step['id']} needs a source reference and a safe comparison")
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


def detector_spec():
    address = detector_findings([{"text": "域名: check.example.invalid"}])
    return {
        "rules": [{
            "rule": item.key,
            "category": item.category,
            "title": item.title,
            "summary": item.summary,
            "chinese": list(item.chinese),
            "english": item.english.pattern if item.english else None,
            "exact": sorted(EXACT_LABELS.get(item.key, ())),
            "rejectPrefixes": list(NEGATED_PREFIXES.get(item.key, ())),
            "status": item.status,
            "grade": "E1",
        } for item in RULES],
        "domainPattern": DOMAIN_PATTERN.pattern,
        "visibleAddress": next(clue for clue in address if clue["rule"] == "visible_address"),
    }


def screenshot_image(path):
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not path.is_file():
        raise ValueError("截图仅接受本地 PNG 或 JPEG")
    if path.stat().st_size > MAX_SCREENSHOT_BYTES:
        raise ValueError("单张截图超过 4 MiB")
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise ValueError("截图格式与文件内容不符")
    return "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")


def comparison_mapping(manifest, expected):
    if manifest is None:
        return {}
    mapping = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or set(mapping) != expected:
        raise ValueError("本机对照清单必须为每一关指定一张截图")
    return mapping


def checked_channel(channel):
    if channel is None:
        return None
    match = PUBLIC_CHANNEL.fullmatch(channel)
    if not match or match[1].lower() in TELEGRAM_ROUTES:
        raise ValueError("请提供 https://t.me/用户名 格式的公开演练频道链接")
    return channel


def browser_payload(data, history_manifest, telegram_manifest=None, channel=None):
    channel = checked_channel(channel)
    expected = {step["id"] for lesson in data["lessons"] for step in lesson["steps"]}
    history = comparison_mapping(history_manifest, expected)
    telegram = comparison_mapping(telegram_manifest, expected)
    for lesson in data["lessons"]:
        for step in lesson["steps"]:
            # The browser derives cues from the active card on every action.
            step.pop("findings")
            if history_manifest:
                local_path = (history_manifest.parent / history[step["id"]]).resolve(strict=True)
                step["history"]["image"] = screenshot_image(local_path)
            if telegram_manifest:
                entry = telegram[step["id"]]
                if not isinstance(entry, dict) or set(entry) != {"file", "reference"} or not all(
                    isinstance(value, str) and value.strip() for value in entry.values()
                ) or LIVE_POINTER.search(entry["reference"]):
                    raise ValueError(f"{step['id']} 的 Telegram 实测截图须提供文件及不含链接的引用")
                local_path = (telegram_manifest.parent / entry["file"]).resolve(strict=True)
                step["telegram"] = {"reference": entry["reference"], "image": screenshot_image(local_path)}
    payload = {**data, "detector": detector_spec(), "hasLocalHistory": bool(history_manifest)}
    if channel:
        payload["telegramChannel"] = channel
    return payload


def compiled_html(history_manifest=None, telegram_manifest=None, channel=None):
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1 or template.count(DETECTOR_PLACEHOLDER) != 1:
        raise ValueError("The template needs one payload and one detector slot")
    validated = lesson_payload(LESSONS.read_text(encoding="utf-8"))
    data = browser_payload(validated, history_manifest, telegram_manifest, channel)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", r"\u003c")
    code = DETECTOR.read_text(encoding="utf-8")
    return template.replace(PLACEHOLDER, payload).replace(DETECTOR_PLACEHOLDER, code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "training.html")
    parser.add_argument("--check", action="store_true", help="核对已生成的文件，不写入")
    parser.add_argument("--history", type=Path, help="仅本机使用的原始历史截图清单 JSON")
    parser.add_argument("--telegram", type=Path, help="仅本机使用的 Telegram 模拟演练截图清单 JSON")
    parser.add_argument("--channel", help="仅在本机文件显示的公开演练频道链接")
    args = parser.parse_args()

    try:
        if (args.history or args.telegram or args.channel) and args.output.resolve().is_relative_to(ROOT):
            raise ValueError("请用 --output 指定 Git 工作区之外的本机文件")
        expected = compiled_html(args.history, args.telegram, args.channel)
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
