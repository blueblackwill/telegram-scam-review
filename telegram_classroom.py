"""Render the anti-fraud lessons as Telegram messages and callback buttons."""

from copy import deepcopy

from build_training import LESSONS, lesson_payload


HEADER = "【模拟演练】纸舟课堂·防骗核证"
MENU = "lesson:menu:0"

SCENARIOS = {
    "gift-message": (
        "聊天里出现一张带领取提示的消息卡，底下写着一个金额。",
        "查看课堂红包卡片",
        "把消息卡上的字当成到账凭证，会把尚未证实的钱算进账户。",
    ),
    "gift-balance": (
        "聊天页显示一笔新增余额。你手里的支付账户还没有对应流水。",
        "查看页面余额记录",
        "如果把页面自报余额加到原钱包里，可能会按一笔未证实入账的钱作决定。",
    ),
    "gift-withdrawal": (
        "提现页先要求填写金额，随后出现一条绑定提示。",
        "查看课堂提现记录",
        "把绑定提示当成提现成功，会漏查页面下一步实际要你确认的操作。",
    ),
    "gift-allowance": (
        "课堂提示里出现一个额度。请核对它代表的权限和证据来源。",
        "查看课堂额度记录",
        "把额度算成已扣款，会漏查真实权限范围。假如额度后来被使用，款项才可能转出。",
    ),
    "shop-order": (
        "聊天里出现一张待支付订单。卡片和内联署名提供的线索并不相同。",
        "查看课堂订单卡片",
        "把卡片生成方当成卖家，可能会把一笔订单认到未经核实的商家名下。",
    ),
    "shop-link": (
        "在订单后方弹出打开链接提示，要求离开聊天页面。",
        "查看课堂跳转记录",
        "把弹窗当作官方背书，可能会把未经核实的外部页面当成商家的收银台。",
    ),
    "shop-payment": (
        "收银台列出应付金额和付款方式，手里没有独立账户回执。",
        "查看课堂收银记录",
        "把待付金额记成已扣款，可能在缺少付款凭证时误把订单认成已结清。",
    ),
    "shop-payment-or-allowance": (
        "一份材料显示付款请求。课堂另给出一条权限提示供你核对。",
        "查看课堂付款与权限记录",
        "把付款按钮当成授权凭证，会漏查钱包真正要你确认什么。误批额度时，给出的权限可能超出这一单。",
    ),
}


def button(text, target):
    return {"text": text, "callback_data": target}


def message(parts, buttons):
    return {
        "text": "\n\n".join((HEADER, *parts)),
        "reply_markup": {"inline_keyboard": [[item] for item in buttons]},
    }


def simulated_record(step):
    rows = [f"• {row['label']}：{row['value']}" for row in step["ledger"]]
    if step["id"] == "gift-message":
        rows.insert(0, "• 领取前页面余额：0 课堂点")
    if step["id"] == "shop-order":
        order = next(row["text"] for row in step["evidence"] if row["label"] == "当前订单")
        rows[0] = f"• 课堂订单卡：{order}"
    return "\n".join(rows)


class Classroom:
    """Build a finite catalog of defensive lesson screens, with no chat data or network access."""

    def __init__(self):
        lessons = lesson_payload(LESSONS.read_text(encoding="utf-8"))["lessons"]
        self._screens = {}
        lesson_bits = {lesson["id"]: 1 << index for index, lesson in enumerate(lessons)}
        all_passed = (1 << len(lessons)) - 1
        for passed in range(all_passed + 1):
            menu = f"lesson:menu:{passed}"
            buttons = []
            for lesson in lessons:
                route = lesson["id"]
                completed = bool(passed & lesson_bits[route])
                label = f"✅ {lesson['title']} · 再练一次" if completed else f"开始 · {lesson['title']}"
                buttons.append(button(label, f"lesson:{route}:{passed}:0"))
            parts = [
                "在两条案例路线中逐步查看卡片、订单和权限线索。点开每一步的记录，再作核验判断。",
                "这是防骗课堂。按钮只切换教学画面，课堂里没有真实钱款或授权操作。",
            ]
            if passed:
                parts.append(f"已通关 {bin(passed).count('1')} / {len(lessons)} 条路线。")
                buttons.append(button("重置本轮进度", MENU))
            self._screens[menu] = message(parts, buttons)
            for lesson in lessons:
                earned = passed | lesson_bits[lesson["id"]]
                for index in range(len(lesson["steps"])):
                    self._add_step(lesson, index, passed, earned, all_passed)

    def _add_step(self, lesson, index, passed, earned, all_passed):
        steps = lesson["steps"]
        step = steps[index]
        key = f"lesson:{lesson['id']}:{passed}:{index}"
        back = button("回路线入口", f"lesson:menu:{passed}")
        number = index + 1
        source = step["sourceNote"]
        title = f"{lesson['title']} · {number}/{len(steps)}｜{step['title']}"
        scene, inspect_label, consequence = SCENARIOS[step["id"]]
        inspect = f"{key}:inspect"
        self._screens[key] = message([title, scene], [button(inspect_label, inspect), back])

        detector = "\n".join(
            f"• {clue['grade']} {clue['title']}"
            for clue in step["findings"]
            if clue["method"] == "detector"
        )
        choices = [button(choice["label"], f"{key}:{choice['id']}") for choice in step["choices"]]
        self._screens[inspect] = message([
            title,
            f"课堂模拟记录\n{simulated_record(step)}",
            f"历史画面\n{source['observed']}",
            f"模拟记录的文字线索\n{detector}",
            step["question"],
        ], [*choices, back])

        pending = f"仍待核\n{source['unverified']}"
        for choice in step["choices"]:
            choice_key = f"{key}:{choice['id']}"
            if not choice["correct"]:
                self._screens[choice_key] = message([
                    title, "⚠️ 模拟受骗 · 请提高警惕", consequence, choice["feedback"], pending,
                ], [button("重试这一步", inspect), back])
            elif number < len(steps):
                next_key = f"lesson:{lesson['id']}:{passed}:{number}"
                self._screens[choice_key] = message([
                    title, "✅ 核对正确", choice["feedback"], pending,
                ], [button(f"下一步 · {steps[number]['title']}", next_key), back])
            else:
                completion = "两条路线均已通关。" if earned == all_passed else f"{len(steps)} 步核验均已完成。"
                recap = "\n".join(f"• {item['takeaway']}" for item in steps)
                self._screens[choice_key] = message([
                    f"✅ 通关 · {lesson['title']}", completion, choice["feedback"], pending, f"本路线复盘\n{recap}",
                ], [button("回路线入口与通关记录", f"lesson:menu:{earned}")])

    def screen(self, callback_data=None):
        """Return a new Telegram payload for a known callback, or None for invalid data."""
        if callback_data is None:
            callback_data = MENU
        if not isinstance(callback_data, str):
            return None
        return deepcopy(self._screens.get(callback_data))
