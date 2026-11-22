"""Offline OCR cue classification.

Only fixed evidence labels leave this module; OCR lines and destinations are
never included in findings. A visible status is evidence about a screen, not
about a bot identity, token allowance, or the result of a transfer.
"""

from dataclasses import dataclass
import re
import unicodedata
from typing import Optional
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Rule:
    key: str
    category: str
    title: str
    summary: str
    chinese: tuple[str, ...]
    english: Optional[re.Pattern]
    status: str = "observed"


def rule(key, category, title, summary, chinese=(), english=None, status="observed"):
    pattern = re.compile(english) if english else None
    return Rule(key, category, title, summary, chinese, pattern, status)


RULES = (
    rule(
        "bot_label", "bot", "机器人字样",
        "画面出现机器人字样。对应的机器人账户和历史归属仍需核对。",
        ("机器人", "機器人"),
        r"(?:^bot$|\btelegram\s+bot\b|\bstore\s+bot\b)",
    ),
    rule(
        "inline_attribution", "bot", "内联署名线索",
        "画面出现「通过」或 via 署名样式。应核对原生消息字段才能确认内容生成方。",
        ("通过@", "透過@", "通过:@", "透過:@", "经由@", "經由@"),
        r"(?:^via$|\bvia\s*:?\s*@)",
    ),
    rule(
        "forward_origin", "bot", "转发来源线索",
        "画面出现转发来源字样。来源账号要以 Telegram 原生转发字段核对。",
        ("转发自", "轉發自", "转发来源", "轉發來源", "轉寄自"),
        r"\bforwarded\s+from\b",
    ),
    rule(
        "support_label", "bot", "客服角色字样",
        "画面将某个入口标为客服。客服身份与商铺机器人本体分别核对。",
        ("钱包客服", "錢包客服", "专属客服", "專屬客服", "联系客服", "聯繫客服", "聯絡客服"),
        r"\b(?:wallet|customer)\s+support\b",
    ),
    rule(
        "external_link_prompt", "link", "打开链接提示",
        "画面出现打开外部链接的提示。仅凭提示无法判定目标域名或最终跳转。",
        ("打开链接", "打開鏈接", "打開連結", "打开此链接", "打開此連結", "外部链接", "外部連結"),
        r"\b(?:open\s+(?:(?:an?|the|this|external)\s+)*link|external\s+link)\b",
    ),
    rule(
        "order_pending", "payment", "订单显示待支付",
        "画面显示订单待支付或未付款。相应的账户账单和交易状态仍待核对。",
        ("待支付", "待付款", "未付款", "尚未支付"),
        r"\b(?:awaiting\s+payment|payment\s+pending|pending\s+payment|unpaid)\b",
    ),
    rule(
        "checkout_page", "payment", "收银台界面",
        "画面出现收银台或结账界面。实际支付机构与资金状态待核。",
        ("支付中心", "收银台", "收銀台", "收款台", "收款頁", "结账", "結帳"),
        r"\b(?:pay(?:ment)?\s+cent(?:er|re)|check\s*out|cashier)\b",
    ),
    rule(
        "payment_request", "payment", "付款请求",
        "画面请求付款或提示打开钱包付款。没有据此确认已经扣款。",
        ("立即支付", "立即付款", "确认支付", "確認支付", "前往支付", "钱包app支付",
         "錢包app支付", "打开钱包支付", "打開錢包支付"),
        r"\b(?:pay\s+now|confirm\s+(?:the\s+)?payment|open\s+(?:your\s+)?wallet\s+to\s+pay)\b",
    ),
    rule(
        "withdrawal_prompt", "payment", "提现界面线索",
        "画面出现提现金额或提现请求。是否到账要与独立流水对照。",
        ("提现金额", "提現金額", "提现的金额", "提現的金額", "申请提现", "申請提現",
         "提现到钱包", "提現到錢包"),
        r"\b(?:withdraw(?:al)?\s+amount|amount\s+to\s+withdraw)\b",
    ),
    rule(
        "network_label", "payment", "区块链网络字样",
        "画面出现区块链网络或代币标准字样。交易所属网络要看独立回执。",
        ("波场", "波場"),
        r"\b(?:tron|trc[\s-]*20|erc[\s-]*20)\b",
    ),
    rule(
        "token_amount", "payment", "画面出现代币金额",
        "画面列出代币金额。可能是余额、订单金额或支付请求，需要核对对应记录。",
        (),
        r"(?<![\w.])\d+(?:[.,]\d+)*\s*(?:usdt|usdc|trx|eth|btc)\b|"
        r"\b(?:usdt|usdc|trx|eth|btc)\s*[:=]?\s*\d+(?:[.,]\d+)*",
    ),
    rule(
        "payment_success_claim", "payment", "画面自称付款或领取成功",
        "只能确认画面上的成功提示。实际转出或到账仍待独立回执核对。",
        ("支付成功", "付款成功", "领取成功", "領取成功", "到账成功", "到賬成功",
         "交易成功", "支付完成", "已支付", "已付款"),
        r"(?:^paid$|\bpayment\s+(?:successful|succeeded|completed)\b"
        r"|\breceived\s+successfully\b)",
        status="pending",
    ),
    rule(
        "transaction_identifier_label", "payment", "交易编号或回执字样",
        "画面出现交易编号或回执字样。对应日期、金额、网络及成功状态需要另查。",
        ("交易哈希", "交易雜湊", "链上回执", "鏈上回執"),
        r"\b(?:txid|transaction\s+(?:hash|receipt))\b",
        status="pending",
    ),
    rule(
        "wallet_binding", "approval", "钱包绑定或连接提示",
        "画面邀请绑定或连接钱包。钱包连接和代币额度是不同动作，实际签名内容待核。",
        ("绑定钱包", "綁定錢包", "钱包绑定", "錢包綁定", "连接钱包", "連接錢包",
         "鏈接錢包", "链接钱包", "点击前往绑定", "點擊前往綁定", "前往绑定", "前往綁定"),
        r"\b(?:connect|bind|link)\s+(?:a\s+|your\s+)?wallet\b",
        status="pending",
    ),
    rule(
        "authorization_text", "approval", "授权或额度字样",
        "画面提到授权或额度。需要钱包待签详情或正确网络上的实际权限记录核对。",
        ("代币授权", "代幣授權", "授权额度", "授權額度", "授权成功", "授權成功",
         "发起授权", "發起授權", "钱包授权", "錢包授權", "签名授权", "簽名授權",
         "无限授权", "無限授權", "批准额度", "批准額度", "授权金额", "授權金額"),
        r"(?:^approval$|\b(?:token\s+approval|spending\s+(?:limit|cap)"
        r"|approve\s+(?:(?:token\s+)?spending|(?:the\s+)?allowance)"
        r"|approval\s+(?:succeeded|successful|confirmed))\b)",
        status="pending",
    ),
)

URL_PATTERN = re.compile(
    r'(?<![\w@])(?:https?://|www\.|t\.me/)[^ \t\n<>"“”\'，。！？；、（）【】]{2,}'
)
DOMAIN_PATTERN = re.compile(
    r"(?:域名|网站地址|網址|网址|domain|website)\s*:\s*([\w-]+(?:\.[\w-]+)+)(?=\b|$)"
)


def _normalized_text(value):
    normalized = unicodedata.normalize("NFKC", value).casefold()
    no_format = "".join(char for char in normalized if unicodedata.category(char) != "Cf")
    return " ".join(no_format.split())


def _valid_box(value):
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None
    if any(type(coord) not in (int, float) or not -0.01 <= coord <= 1.01 for coord in value):
        return None
    x, y, width, height = value
    # Permit tiny edge drift from OCR, then clip to the displayed image.
    if width <= 0 or height <= 0 or x < -0.01 or y < -0.01:
        return None
    if x + width > 1.01 or y + height > 1.01 or x >= 1 or y >= 1:
        return None
    if 0 <= x and 0 <= y and x + width <= 1 and y + height <= 1:
        return list(value)
    left = max(0.0, x)
    top = max(0.0, y)
    return [left, top, min(1.0, x + width) - left, min(1.0, y + height) - top]


def _match(rule_item, spaced, compact):
    if rule_item.key == "authorization_text" and compact in {"授权", "授權", "已授权", "已授權"}:
        return True
    if rule_item.key == "payment_success_claim" and compact.startswith(("未支付", "未付款", "未成功")):
        return False
    if rule_item.english is not None and rule_item.english.search(spaced):
        return True
    return any(text in compact for text in rule_item.chinese)


def _visible_address(spaced):
    """Check the text shape locally without disclosing or opening its target."""
    found = False
    unusual_host = False
    candidates = (match.group(0) for match in URL_PATTERN.finditer(spaced))
    for candidate in candidates:
        url = candidate if "://" in candidate else "https://" + candidate
        try:
            parsed = urlsplit(url)
            host = parsed.hostname
        except ValueError:
            continue
        if not host or parsed.scheme not in {"http", "https"}:
            continue
        found = True
        if "@" in parsed.netloc or "xn--" in host or not host.isascii():
            unusual_host = True
    explicit_domain = DOMAIN_PATTERN.search(spaced)
    if explicit_domain:
        found = True
        host = explicit_domain.group(1)
        unusual_host = unusual_host or "xn--" in host or not host.isascii()
    return found, unusual_host


def detect(lines: list[dict]) -> list[dict]:
    """Return one E1 finding per matching rule in a single source frame."""
    best: dict[str, tuple[tuple[bool, float], dict]] = {}

    def add(key, category, title, summary, status, box, confidence):
        ranking = (box is not None, confidence)
        if key in best and ranking <= best[key][0]:
            return
        best[key] = (ranking, {
            "rule": key,
            "category": category,
            "title": title,
            "summary": summary,
            "status": status,
            "grade": "E1",
            "box": box,
        })

    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get("text"), str):
            continue
        spaced = _normalized_text(line["text"])
        if not spaced:
            continue
        box = _valid_box(line.get("box"))
        confidence = line.get("confidence", 0.0)
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            confidence = 0.0
        label_text = URL_PATTERN.sub(" ", spaced).strip()
        compact = "".join(label_text.split())
        for item in RULES:
            if _match(item, label_text, compact):
                add(item.key, item.category, item.title, item.summary, item.status, box, confidence)
        found, unusual_host = _visible_address(spaced)
        if found:
            add(
                "visible_address", "link", "画面出现网址或域名",
                "只做本地文字识别。地址已省略，归属、授权收银关系和最终跳转仍待核对。",
                "observed", box, confidence,
            )
        if unusual_host:
            add(
                "address_format_review", "link", "地址结构需要人工核对",
                "网址出现用户信息段或国际化主机名。请对照原图与已知官方域名核对，此格式也可能用于正常网站。",
                "pending", box, confidence,
            )
    return [finding for _, finding in best.values()]

