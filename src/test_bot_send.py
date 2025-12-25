"""更强健的 Telegram bot 测试脚本。

功能:
 - 支持从 `.env`（根目录）或系统环境读取 `TG_TOKEN` / `TG_CHAT_ID`。
 - 可通过命令行参数覆盖 token/chat_id。
 - 使用 `rich` 打印彩色输出并返回合适的退出码。
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time
from typing import Optional

import requests
from dotenv import load_dotenv
from rich import print


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_env() -> None:
    # 优先加载根目录 .env
    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # 若无 .env，则尝试 .env.example（方便测试）
        example = ROOT / ".env.example"
        if example.exists():
            load_dotenv(example)


def send_telegram_message(token: str, chat_id: str, text: str, parse_mode: Optional[str] = "Markdown") -> requests.Response:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    resp = requests.post(url, json=payload, timeout=15)
    return resp


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(description="发送测试消息以验证 Telegram bot 可用性")
    parser.add_argument("message", nargs="?", default=None, help="要发送的消息（可选）")
    parser.add_argument("--token", help="Telegram bot token（覆盖环境变量）")
    parser.add_argument("--chat-id", help="Telegram chat id（覆盖环境变量）")
    args = parser.parse_args()

    token = args.token or os.getenv("TG_TOKEN")
    chat_id = args.chat_id or os.getenv("TG_CHAT_ID")

    if not token or not chat_id:
        print("[red]错误：未提供 TG_TOKEN 或 TG_CHAT_ID。请设置环境变量或使用 --token/--chat-id。[/red]")
        return 2

    text = args.message or f"Bot 可用性测试 — {time.strftime('%Y-%m-%d %H:%M:%S')}"

    print(f"[yellow]发送到 chat_id:[/yellow] [cyan]{chat_id}[/cyan]")

    try:
        resp = send_telegram_message(token, chat_id, text)
    except Exception as e:
        print(f"[red]请求失败:[/red] {e}")
        return 3

    try:
        j = resp.json()
    except Exception:
        print(f"[red]响应不是 JSON，HTTP {resp.status_code}:[/red] {resp.text}")
        return 4

    if resp.ok and j.get("ok"):
        print("[green]发送成功[/green]")
        return 0
    else:
        print(f"[red]发送失败，HTTP {resp.status_code}：[/red] {j}")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
