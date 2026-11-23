"""Exercise Telegram transport and request handling without network access."""
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from traceback import format_exception
import unittest
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError, URLError

from telegram_service import (
    NoRedirects, POLL_SECONDS, TelegramAPI, TelegramError,
    dispatch, public_username, read_token, run,
)


FAKE_TOKEN = "1001:" + "x" * 36


def message(text="/start", chat_type="private"):
    return {
        "text": text,
        "chat": {"type": chat_type, "id": 10},
        "from": {"id": 10, "is_bot": False},
        "message_id": 17,
        "date": 1234,
    }


class SampleClassroom:
    def screen(self, data=None):
        if data not in (None, "lesson:gift"):
            return None
        return {
            "text": "课堂首页" if data is None else "红包线索",
            "reply_markup": {"inline_keyboard": [[{"text": "看线索", "callback_data": "lesson:gift"}]]},
        }


class TelegramServiceTests(unittest.TestCase):
    def test_api_uses_pinned_origin_bounded_poll_and_no_redirect(self):
        opener = Mock(return_value=io.BytesIO(b'{"ok":true,"result":[]}'))
        api = TelegramAPI(FAKE_TOKEN, opener)
        self.assertEqual(api.call("getUpdates", {"timeout": POLL_SECONDS}), [])
        (request,), options = opener.call_args
        self.assertEqual(request.host, "api.telegram.org")
        self.assertEqual(request.type, "https")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(options["timeout"], POLL_SECONDS + 10)
        self.assertEqual(json.loads(request.data), {"timeout": POLL_SECONDS})
        self.assertIsNone(NoRedirects().redirect_request(None, None, 302, "", {}, "https://example.invalid"))
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            api.call("sendInvoice")
        self.assertEqual(opener.call_count, 1)

    def test_api_errors_strip_url_and_response_description(self):
        response = {"ok": False, "description": f"during {FAKE_TOKEN}", "parameters": {"retry_after": 7}}
        error = HTTPError(f"https://api.telegram.org/bot{FAKE_TOKEN}/getUpdates", 429,
                          "Too Many Requests", None, io.BytesIO(json.dumps(response).encode()))
        with self.assertRaises(TelegramError) as caught:
            TelegramAPI(FAKE_TOKEN, Mock(side_effect=error)).call("getUpdates")
        self.assertEqual((caught.exception.status, caught.exception.retry_after), (429, 7))
        self.assertNotIn(FAKE_TOKEN, str(caught.exception))
        try:
            TelegramAPI(FAKE_TOKEN, Mock(side_effect=URLError(f"raw url {FAKE_TOKEN}"))).call("getUpdates")
        except TelegramError as error:
            self.assertNotIn(FAKE_TOKEN, "".join(format_exception(type(error), error, error.__traceback__)))
        else:
            self.fail("A transport error should be surfaced")

    def test_start_is_explicit_private_and_does_not_echo_user_content(self):
        api = Mock()
        classroom = SampleClassroom()
        stop, log = Mock(), Mock()
        for update in (
            {"message": message("/start --other")},
            {"message": message("freeform input")},
            {"message": message(chat_type="supergroup")},
            {"channel_post": message()},
            {"message": {**message(), "from": {"id": 11}}},
        ):
            dispatch(api, classroom, update, stop, log)
        api.call.assert_not_called()
        dispatch(api, classroom, {"message": message()}, stop, log)
        api.call.assert_called_once_with("sendMessage", {
            **classroom.screen(), "chat_id": 10, "link_preview_options": {"is_disabled": True},
        })

    def test_callbacks_are_acknowledged_before_edit_and_invalid_data_is_not_echoed(self):
        api = Mock()
        classroom = SampleClassroom()
        stop, log = Mock(), Mock()
        query = {"id": "fixture-query", "data": "lesson:gift", "from": {"id": 10}, "message": message()}
        dispatch(api, classroom, {"callback_query": query}, stop, log)
        self.assertEqual(api.call.call_args_list, [
            call("answerCallbackQuery", {"callback_query_id": "fixture-query"}),
            call("editMessageText", {
                **classroom.screen("lesson:gift"), "chat_id": 10, "message_id": 17,
                "link_preview_options": {"is_disabled": True},
            }),
        ])
        api.reset_mock()
        dispatch(api, classroom, {"callback_query": {**query, "data": "unknown callback"}}, stop, log)
        api.call.assert_called_once_with("answerCallbackQuery", {
            "callback_query_id": "fixture-query", "text": "此按钮已失效。发送 /start 可以返回课堂首页。",
        })
        api.reset_mock()
        dispatch(api, classroom, {"callback_query": {**query, "message": message(chat_type="group")}}, stop, log)
        api.call.assert_not_called()

    def test_failed_callback_acknowledgement_does_not_swallow_valid_edit(self):
        api = Mock()
        stop, log = Mock(), Mock()
        stop.wait.return_value = False
        query = {"id": "fixture-query", "data": "lesson:gift", "from": {"id": 10}, "message": message()}
        for status in (400, 429, None):
            with self.subTest(status=status):
                api.reset_mock()
                stop.reset_mock()
                log.reset_mock()
                error = TelegramError("answerCallbackQuery", status, retry_after=4 if status == 429 else 0)
                api.call.side_effect = [error, True]
                dispatch(api, SampleClassroom(), {"callback_query": query}, stop, log)
                self.assertEqual([entry.args[0] for entry in api.call.call_args_list],
                                 ["answerCallbackQuery", "editMessageText"])
                log.assert_called_once_with(f"Telegram 教学回执失败 · {error}")
                self.assertNotIn(query["id"], str(log.call_args_list))
                if status == 429:
                    stop.wait.assert_called_once_with(4)
                else:
                    stop.wait.assert_not_called()

    def test_failed_callback_acknowledgement_keeps_invalid_and_unavailable_states_closed(self):
        api = Mock()
        stop, log = Mock(), Mock()
        query = {"id": "fixture-query", "data": "unknown callback", "from": {"id": 10}, "message": message()}
        api.call.side_effect = TelegramError("answerCallbackQuery", 400)
        with self.assertRaises(TelegramError):
            dispatch(api, SampleClassroom(), {"callback_query": query}, stop, log)
        api.call.assert_called_once()
        log.assert_not_called()
        api.reset_mock()
        api.call.side_effect = TelegramError("answerCallbackQuery", 401)
        query["data"] = "lesson:gift"
        with self.assertRaises(TelegramError):
            dispatch(api, SampleClassroom(), {"callback_query": query}, stop, log)
        api.call.assert_called_once()
        log.assert_not_called()

    def test_poll_retries_and_acknowledges_callbacks_without_persisting_inputs(self):
        api = Mock()
        stop = Mock()
        stop.is_set.return_value = False
        log = Mock()
        calls = []

        def respond(method, options):
            if method == "sendMessage":
                return True
            calls.append(options)
            if len(calls) == 1:
                raise TelegramError("getUpdates", 429, retry_after=8)
            if len(calls) == 2:
                raise TelegramError("getUpdates")
            if len(calls) == 3:
                update = {"update_id": 100, "message": message()}
                return [update, update]
            if len(calls) == 4:
                return []
            stop.is_set.return_value = True
            return []

        api.call.side_effect = respond
        run(api, SampleClassroom(), stop, log)
        self.assertEqual(stop.wait.call_args_list, [call(8), call(2)])
        self.assertEqual([r.get("offset") for r in calls], [None, None, None, 101, None])
        self.assertEqual(sum(c.args[0] == "sendMessage" for c in api.call.call_args_list), 1)
        self.assertNotIn("fixture", str(log.call_args_list))

    def test_conflicting_poller_is_a_configuration_error(self):
        api = Mock()
        api.call.side_effect = TelegramError("getUpdates", 409)
        stop = Mock()
        stop.is_set.return_value = False
        with self.assertRaises(TelegramError) as caught:
            run(api, SampleClassroom(), stop, Mock())
        self.assertEqual(caught.exception.status, 409)
        stop.wait.assert_not_called()

    def test_failed_delivery_reports_only_approved_diagnostic_fields(self):
        api = Mock()
        stop, log = Mock(), Mock()
        stop.is_set.side_effect = [False, False, True]
        api.call.side_effect = [
            [{"update_id": 100, "message": message()}],
            TelegramError("sendMessage", 403),
        ]
        run(api, SampleClassroom(), stop, log)
        log.assert_called_once_with("Telegram 教学操作失败 · sendMessage · HTTP 403")
        self.assertNotIn("fixture", str(log.call_args_list))

    def test_only_public_username_returned_from_startup_check(self):
        api = Mock()
        api.call.return_value = {"username": "PaperBoatFixtureBot", "is_bot": True, "id": 10}
        self.assertEqual(public_username(api), "PaperBoatFixtureBot")
        api.call.assert_called_once_with("getMe")
        api.call.return_value = {"username": "PaperBoatFixtureBot / other output", "is_bot": True}
        with self.assertRaises(TelegramError):
            public_username(api)

    def test_runtime_file_requires_owner_only_regular_file(self):
        with TemporaryDirectory() as folder:
            fixture = Path(folder, "token.fixture")
            fixture.write_text(FAKE_TOKEN + "\n", encoding="ascii")
            fixture.chmod(0o600)
            self.assertEqual(read_token(fixture), FAKE_TOKEN)
            fixture.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "0600"):
                read_token(fixture)
            link = Path(folder, "alias")
            link.symlink_to(fixture)
            with self.assertRaisesRegex(ValueError, "无法读取"):
                read_token(link)
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": FAKE_TOKEN}):
            self.assertEqual(read_token(None), FAKE_TOKEN)


if __name__ == "__main__":
    unittest.main()
