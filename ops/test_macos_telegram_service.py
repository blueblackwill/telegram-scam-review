"""Exercise launch configuration without contacting Telegram or launchd."""

import io
from pathlib import Path
import plistlib
import unittest
from unittest.mock import patch

from ops import macos_telegram_service as daemon


class MacosServiceTests(unittest.TestCase):
    def test_plist_launches_standard_runner_using_only_private_file_path(self):
        data, plist = daemon.service_paths(Path("/sample/home"))
        project = Path("/sample/paper boat")
        config = plistlib.loads(daemon.plist_contents(Path("/sample/python3"), project, data))
        self.assertEqual(plist.name, f"{daemon.LABEL}.plist")
        self.assertEqual(config["ProgramArguments"], [
            "/sample/python3", "-B", "-u", "/sample/paper boat/telegram_service.py",
            "--token-file", str(data / "bot-token"),
        ])
        self.assertTrue(config["RunAtLoad"])
        self.assertTrue(config["KeepAlive"])
        self.assertNotIn("EnvironmentVariables", config)

    def test_noninteractive_configuration_stops_before_secret_input(self):
        data = Path("/sample/data")
        with patch.object(daemon.sys, "stdin", io.StringIO()), patch.object(daemon.getpass, "getpass") as secret:
            with self.assertRaisesRegex(ValueError, "交互式终端"):
                daemon.configure(data)
        secret.assert_not_called()

    def test_launchd_status_reports_only_recognized_process_state(self):
        with patch.object(daemon, "launchctl") as command, patch("sys.stdout", new_callable=io.StringIO) as output:
            command.return_value.returncode = 0
            command.return_value.stdout = "state metadata\n  state = running\n  unreported fields"
            self.assertEqual(daemon.status("gui/501/example"), 0)
            self.assertIn("running", output.getvalue())
            self.assertNotIn("unreported fields", output.getvalue())


if __name__ == "__main__":
    unittest.main()
