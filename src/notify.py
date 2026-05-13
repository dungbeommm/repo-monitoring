from __future__ import annotations

import argparse
import os
import requests


def send_discord(webhook: str, message: str) -> None:
    response = requests.post(webhook, json={"content": message}, timeout=30)
    response.raise_for_status()


def send_telegram(token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=30)
    response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--message", default="")
    args = parser.parse_args()
    text = f"[{args.status}] {args.workflow}\n{args.message}\n{args.run_url}".strip()
    discord = os.getenv("DISCORD_WEBHOOK_URL")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.getenv("TELEGRAM_CHAT_ID")
    if discord:
        send_discord(discord, text)
    if telegram_token and telegram_chat:
        send_telegram(telegram_token, telegram_chat, text)
    print(text)


if __name__ == "__main__":
    main()

