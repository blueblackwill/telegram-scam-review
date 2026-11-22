#!/usr/bin/env python3
"""Configure the classroom bot as a per-user macOS background service."""

import argparse
import getpass
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import warnings


LABEL = "io.paperboat.telegram-classroom"
ROOT = Path(__file__).resolve().parents[1]
LAUNCHCTL = "/bin/launchctl"


def service_paths(home):
    data = home / "Library" / "Application Support" / "PaperBoatClassroom"
    plist = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    return data, plist


def service_args(python, project, token_path):
    return [str(python), "-B", "-u", str(project / "telegram_service.py"), "--token-file", str(token_path)]


def plist_contents(python, project, data):
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": service_args(python, project, data / "bot-token"),
        "WorkingDirectory": str(project),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 30,
        "ProcessType": "Background",
        "StandardOutPath": str(data / "service-out.log"),
        "StandardErrorPath": str(data / "service-error.log"),
    })


def secure_path(path, kind):
    info = path.lstat()
    if not kind(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("运行目录和凭据文件必须由当前用户独享。")


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    secure_path(path, stat.S_ISDIR)


def write_new(path, content, mode):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode), "wb") as stream:
        stream.write(content)


def configure(data):
    if not sys.stdin.isatty():
        raise ValueError("请在你自己的交互式终端录入令牌。")
    private_directory(data)
    key = data / "bot-token"
    if key.exists() or key.is_symlink():
        raise ValueError("本机已经有一份 Bot 凭据。")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        token = getpass.getpass("Telegram Bot 令牌（输入隐藏）: ").strip()
    if not re.fullmatch(r"[0-9]{1,24}:[A-Za-z0-9_-]{16,128}", token, re.ASCII):
        raise ValueError("请录入 BotFather 提供的一行令牌。")
    write_new(key, token.encode("utf-8") + b"\n", 0o600)
    print("已把 Bot 凭据保存在当前用户的专用目录。")


def launchctl(*arguments):
    return subprocess.run([LAUNCHCTL, *arguments], text=True, capture_output=True, timeout=15)


def ensure_plist(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_new(path, contents, 0o644)
    except FileExistsError:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or path.read_bytes() != contents:
            raise ValueError("检测到已有的不同服务配置，请检查当前 Python 和项目位置。") from None


def prepare_logs(data):
    for name in ("service-out.log", "service-error.log"):
        log = data / name
        try:
            write_new(log, b"", 0o600)
        except FileExistsError:
            secure_path(log, stat.S_ISREG)


def install(python, data, plist, domain):
    key = data / "bot-token"
    if not key.exists():
        raise ValueError("请先在你的终端执行 configure。")
    secure_path(data, stat.S_ISDIR)
    secure_path(key, stat.S_ISREG)
    probe = [*service_args(python, ROOT, key), "--check"]
    if subprocess.run(probe, timeout=40).returncode:
        raise ValueError("Bot API 验证未通过。")
    prepare_logs(data)
    ensure_plist(plist, plist_contents(python, ROOT, data))
    target = f"{domain}/{LABEL}"
    if launchctl("print", target).returncode != 0:
        if launchctl("bootstrap", domain, str(plist)).returncode != 0:
            raise ValueError("macOS 未能加载服务。请在此账号登录的桌面会话中运行 install。")
    return status(target)


def status(target):
    result = launchctl("print", target)
    if result.returncode:
        print("当前用户会话未加载纸舟课堂 Bot 服务。")
        return 1
    state = re.search(r"(?m)^\s*state = (running|waiting|spawn scheduled|exited)\s*$", result.stdout)
    print("纸舟课堂 Bot 服务已加载。进程状态：" + (state.group(1) if state else "由 macOS 管理"))
    return 0


def stop(target):
    if launchctl("print", target).returncode == 0 and launchctl("bootout", target).returncode:
        raise ValueError("macOS 未能停止纸舟课堂 Bot 服务。")
    print("纸舟课堂 Bot 服务已从当前会话卸载。下次登录时会重新加载。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "install", "status", "stop"))
    action = parser.parse_args(argv).action
    if sys.platform != "darwin":
        parser.exit(1, "此服务管理脚本仅适用于 macOS。\n")
    data, plist = service_paths(Path.home())
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    try:
        if action == "configure":
            configure(data)
            return 0
        if action == "install":
            return install(Path(sys.executable).resolve(), data, plist, domain)
        if action == "status":
            return status(target)
        return stop(target)
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    except (OSError, KeyboardInterrupt, EOFError, getpass.GetPassWarning, subprocess.TimeoutExpired):
        parser.exit(1, "本机服务操作未完成。请核对交互终端、目录权限和 macOS 登录状态。\n")


if __name__ == "__main__":
    raise SystemExit(main())
