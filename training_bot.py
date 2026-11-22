#!/usr/bin/env python3
"""Run the fictional Paper Boat classroom bot in this terminal."""

import argparse

from build_training import LESSONS, lesson_payload


def select_route(routes):
    for number, route in enumerate(routes, start=1):
        print(f"  {number}. {route['title']}")
    options = {str(number): route for number, route in enumerate(routes, start=1)}
    while True:
        selection = input("选择路线编号，或输入 q 结束：").strip().lower()
        if selection == "q":
            return None
        if selection in options:
            return options[selection]
        print("请输入上面列出的路线编号。")


def run_route(route):
    steps = route["steps"]
    print(f"\n纸舟课堂｜{route['title']}｜课堂进度 0/{len(steps)} 点")
    for number, step in enumerate(steps, start=1):
        print(f"\n【模拟演练】{number}/{len(steps)} · {step['title']}")
        while True:
            command = input(f"按回车「{step['action']}」，或输入 q 结束：").strip().lower()
            if command == "q":
                return
            if not command:
                break
            print("演练只接受回车或 q。")
        print(f"课堂进度 +1 点（{number}/{len(steps)}）")
        for index, row in enumerate(step["evidence"], start=1):
            print(f"  [{index}] {row['label']}｜{row['text']}")
        for clue in step["findings"]:
            status = "待核" if clue["status"] == "pending" else "可见线索"
            location = "" if clue["row"] is None else f"｜材料 {clue['row'] + 1}"
            print(f"  [{status} {clue['grade']}{location}] {clue['title']}。{clue['summary']}")
    print("\n【模拟演练】本路线已走完。现在回看每一步：")
    for number, step in enumerate(steps, start=1):
        print(f"  {number}. {step['takeaway']}")


def main():
    routes = lesson_payload(LESSONS.read_text(encoding="utf-8"))["lessons"]
    by_id = {route["id"]: route for route in routes}
    parser = argparse.ArgumentParser(description="纸舟课堂｜本机防骗教学机器人")
    parser.add_argument("--route", choices=by_id, help="跳过路线选择")
    args = parser.parse_args()
    print("【模拟演练】纸舟课堂｜本机课堂机器人")
    print("课堂点数只记录进度。以下卡片、金额和操作都是合成材料。")
    try:
        route = by_id[args.route] if args.route else select_route(routes)
        if route:
            run_route(route)
    except (EOFError, KeyboardInterrupt):
        print("\n演练已结束。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
