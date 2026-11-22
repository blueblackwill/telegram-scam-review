"""Run the Paper Boat defensive classroom in private Telegram bot chats."""
import argparse
from http.client import HTTPException
import json
import os
import re
import signal
import stat
import sys
from threading import Event
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from telegram_classroom import Classroom


API_ORIGIN = "https://api.telegram.org"
POLL_SECONDS = 25
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TOKEN_PATTERN = re.compile(r"[0-9]{1,24}:[A-Za-z0-9_-]{16,128}", re.ASCII)
USERNAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}", re.ASCII)
BOT_METHODS = frozenset({"getMe", "getUpdates", "sendMessage", "editMessageText", "answerCallbackQuery"})
CONFIGURATION_ERRORS = frozenset({401, 404, 409})


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


class TelegramError(Exception):
    """The request URL and untrusted Telegram error description are never logged."""

    def __init__(self, method, status=None, retry_after=0):
        self.status = status
        self.retry_after = retry_after
        detail = f"HTTP {status}" if status is not None else "连接或响应异常"
        super().__init__(f"{method} · {detail}")


class TelegramAPI:
    def __init__(self, token, open_request=None):
        self._token = token
        self._open = open_request if open_request is not None else build_opener(NoRedirects()).open

    def call(self, method, params=None):
        if method not in BOT_METHODS:
            raise ValueError("Unsupported Telegram method")
        request = Request(
            f"{API_ORIGIN}/bot{self._token}/{method}",
            data=json.dumps(params or {}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        status = 200
        try:
            try:
                with self._open(request, timeout=POLL_SECONDS + 10) as response:
                    payload = response.read(MAX_RESPONSE_BYTES + 1)
            except HTTPError as error:
                status = error.code
                with error:
                    payload = error.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, URLError, HTTPException, ValueError):
            raise TelegramError(method) from None
        try:
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ValueError("Oversized response")
            result = json.loads(payload)
        except (UnicodeError, ValueError):
            raise TelegramError(method, status if status != 200 else None) from None
        if not isinstance(result, dict):
            raise TelegramError(method, status if status != 200 else None)
        if status == 200 and result.get("ok") is True and "result" in result:
            return result["result"]
        error_code = result.get("error_code")
        parameters = result.get("parameters")
        retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
        raise TelegramError(
            method,
            status if status != 200 else error_code if type(error_code) is int else None,
            retry_after if type(retry_after) is int and 0 < retry_after <= 86400 else 0,
        )


def read_token(token_file):
    """Read the operator-provisioned value in the running process only."""
    if token_file is None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    else:
        try:
            descriptor = os.open(token_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                mode = os.fstat(stream.fileno())
                if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid() or mode.st_mode & 0o077:
                    raise ValueError("凭据文件须由当前用户持有且仅该用户可访问，建议权限 0600。")
                raw = stream.read(257)
                if len(raw) > 256:
                    raise ValueError("Bot 凭据文件内容格式不正确。")
                token = raw.decode("ascii").strip()
        except (OSError, UnicodeError):
            raise ValueError("无法读取 Bot 凭据文件。") from None
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("请配置 Bot 凭据文件或 TELEGRAM_BOT_TOKEN 环境变量。")
    return token


def public_username(api):
    account = api.call("getMe")
    if isinstance(account, dict) and account.get("is_bot") is True:
        username = account.get("username")
        if isinstance(username, str) and USERNAME_PATTERN.fullmatch(username):
            return username
    raise TelegramError("getMe")


def private_chat(message, sender):
    if not isinstance(message, dict) or not isinstance(sender, dict) or sender.get("is_bot") is True:
        return None
    chat = message.get("chat")
    sender_id = sender.get("id")
    if isinstance(chat, dict) and chat.get("type") == "private" and type(sender_id) is int and chat.get("id") == sender_id:
        return sender_id
    return None


def dispatch(api, classroom, update):
    message = update.get("message")
    if isinstance(message, dict) and message.get("text") == "/start":
        chat_id = private_chat(message, message.get("from"))
        if chat_id is not None:
            api.call("sendMessage", {
                **classroom.screen(),
                "chat_id": chat_id,
                "link_preview_options": {"is_disabled": True},
            })
        return

    query = update.get("callback_query")
    if not isinstance(query, dict):
        return
    callback_id = query.get("id")
    message = query.get("message")
    chat_id = private_chat(message, query.get("from"))
    if chat_id is None or not isinstance(callback_id, str) or not 1 <= len(callback_id) <= 128:
        return
    message_id = message.get("message_id")
    if type(message_id) is not int or message.get("date") == 0:
        return
    data = query.get("data")
    screen = classroom.screen(data) if isinstance(data, str) and 1 <= len(data.encode("utf-8", "replace")) <= 64 else None
    answer = {"callback_query_id": callback_id}
    if screen is None:
        answer["text"] = "此按钮已失效。发送 /start 可以返回课堂首页。"
    api.call("answerCallbackQuery", answer)
    if screen is not None:
        api.call("editMessageText", {
            **screen,
            "chat_id": chat_id,
            "message_id": message_id,
            "link_preview_options": {"is_disabled": True},
        })


def run(api, classroom, stop, log):
    offset = None
    backoff = 1
    while not stop.is_set():
        options = {"timeout": POLL_SECONDS, "limit": 25, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            options["offset"] = offset
        try:
            updates = api.call("getUpdates", options)
            if not isinstance(updates, list):
                raise TelegramError("getUpdates")
        except TelegramError as error:
            if error.status in CONFIGURATION_ERRORS:
                raise
            delay = max(backoff, error.retry_after)
            log(f"Telegram 暂时无法取回更新，{delay} 秒后重试。")
            stop.wait(delay)
            backoff = min(backoff * 2, 30)
            continue
        backoff = 1
        if not updates:
            # Telegram accepted the previous acknowledgement. Omit it on the
            # next poll because Telegram may reseed IDs after a week of inactivity.
            offset = None
        for update in updates:
            if stop.is_set():
                return
            update_id = update.get("update_id") if isinstance(update, dict) else None
            if type(update_id) is not int or (offset is not None and update_id < offset):
                continue
            offset = update_id + 1
            try:
                dispatch(api, classroom, update)
            except TelegramError as error:
                if error.status in CONFIGURATION_ERRORS:
                    raise
                if error.status == 429:
                    stop.wait(error.retry_after or 1)
                # A failed request may have been delivered. Do not risk duplicating it.


def main():
    parser = argparse.ArgumentParser(description="纸舟课堂 · Telegram 防骗核证教学")
    parser.add_argument("--token-file", help="由当前用户配置的权限为 0600 的 Bot 凭据文件")
    parser.add_argument("--check", action="store_true", help="只验证凭据并显示机器人的公开用户名")
    args = parser.parse_args()

    def log(message):
        print(message, file=sys.stderr, flush=True)

    try:
        token = read_token(args.token_file)
    except ValueError as error:
        log(str(error))
        return 2
    api = TelegramAPI(token)
    try:
        username = public_username(api)
        if args.check:
            print(f"@{username}")
            return 0
        classroom = Classroom()
        stop = Event()

        def stop_service(_signal, _frame):
            stop.set()

        signal.signal(signal.SIGTERM, stop_service)
        signal.signal(signal.SIGINT, stop_service)
        log(f"纸舟课堂已启动 · @{username}")
        run(api, classroom, stop, log)
    except TelegramError as error:
        log(f"纸舟课堂停止 · {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
