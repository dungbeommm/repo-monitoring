#!/usr/bin/env python3
"""
=============================================================================
 repo-monitoring / monitor.py
 Workflow monitoring with Discord & Telegram notifications
=============================================================================
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "repo-common"))

from src.logger import setup_logger, get_logger
from src.retry_logic import retry_with_backoff
from src.file_utils import save_json, load_json, ensure_dir

logger = setup_logger("monitor", log_dir="output/logs")


class WorkflowMonitor:
    """Track workflow execution and send notifications."""

    def __init__(self, tracking_dir: str = "output/metadata"):
        self.tracking_dir = tracking_dir
        ensure_dir(tracking_dir)
        self.start_time = time.time()
        self.events: List[Dict] = []

    def track_event(
        self,
        event_type: str,
        message: str,
        data: Optional[Dict] = None,
    ):
        """Record a tracking event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.time() - self.start_time, 1),
            "type": event_type,
            "message": message,
            "data": data or {},
        }
        self.events.append(event)
        logger.info(f"[TRACK] {event_type}: {message}")

    def track_chapter_complete(self, chapter_number: int, duration: float, segments: int):
        self.track_event("chapter_complete", f"Chapter {chapter_number} done", {
            "chapter": chapter_number,
            "duration_seconds": duration,
            "segments": segments,
        })

    def track_batch_complete(self, batch_id: int, chapters: List[int]):
        self.track_event("batch_complete", f"Batch {batch_id} done", {
            "batch_id": batch_id,
            "chapters": chapters,
        })

    def track_error(self, component: str, error: str, chapter: Optional[int] = None):
        self.track_event("error", f"Error in {component}: {error}", {
            "component": component,
            "error": error,
            "chapter": chapter,
        })

    def get_summary(self) -> Dict[str, Any]:
        """Generate workflow summary."""
        total_time = time.time() - self.start_time
        errors = [e for e in self.events if e["type"] == "error"]
        chapters = [e for e in self.events if e["type"] == "chapter_complete"]

        return {
            "total_runtime_seconds": round(total_time, 1),
            "total_runtime_human": _format_duration(total_time),
            "total_events": len(self.events),
            "chapters_completed": len(chapters),
            "errors": len(errors),
            "error_details": errors,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def save_report(self, filename: str = "workflow_report.json"):
        """Save tracking report to file."""
        report = {
            "summary": self.get_summary(),
            "events": self.events,
        }
        filepath = os.path.join(self.tracking_dir, filename)
        save_json(report, filepath)
        logger.info(f"Tracking report saved: {filepath}")
        return filepath


# ──────────────────────────────────────────────────────────────────────────────
# Discord Webhook
# ──────────────────────────────────────────────────────────────────────────────
@retry_with_backoff(max_retries=2, base_delay=1.0, logger_name="monitor")
def send_discord_notification(
    webhook_url: str,
    title: str,
    message: str,
    color: int = 0x00FF00,  # Green
    fields: Optional[List[Dict]] = None,
):
    """
    Send a Discord webhook notification.

    Args:
        webhook_url: Discord webhook URL
        title: Embed title
        message: Embed description
        color: Embed color (hex)
        fields: Optional embed fields [{name, value, inline}]
    """
    if not webhook_url:
        logger.debug("Discord webhook URL not configured, skipping")
        return

    import requests

    embed = {
        "title": title,
        "description": message,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "Novel-to-Audio Pipeline"},
    }

    if fields:
        embed["fields"] = fields

    payload = {"embeds": [embed]}

    response = requests.post(
        webhook_url,
        json=payload,
        timeout=10,
    )

    if response.status_code in (200, 204):
        logger.info(f"Discord notification sent: {title}")
    else:
        logger.warning(f"Discord notification failed: {response.status_code}")


# ──────────────────────────────────────────────────────────────────────────────
# Telegram Webhook
# ──────────────────────────────────────────────────────────────────────────────
@retry_with_backoff(max_retries=2, base_delay=1.0, logger_name="monitor")
def send_telegram_notification(
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "HTML",
):
    """
    Send a Telegram bot notification.

    Args:
        bot_token: Telegram bot token
        chat_id: Target chat ID
        message: Message text (HTML or Markdown)
        parse_mode: 'HTML' or 'Markdown'
    """
    if not bot_token or not chat_id:
        logger.debug("Telegram not configured, skipping")
        return

    import requests

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }

    response = requests.post(url, json=payload, timeout=10)

    if response.status_code == 200:
        logger.info("Telegram notification sent")
    else:
        logger.warning(f"Telegram notification failed: {response.status_code}")


# ──────────────────────────────────────────────────────────────────────────────
# Notification Helpers
# ──────────────────────────────────────────────────────────────────────────────
def notify_pipeline_start(
    novel_title: str,
    chapter_start: int,
    chapter_end: int,
):
    """Send notification when pipeline starts."""
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")

    message = (
        f"🚀 **Pipeline Started**\n"
        f"📖 {novel_title}\n"
        f"📄 Chapters {chapter_start} - {chapter_end}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
    )

    if discord_url:
        send_discord_notification(
            discord_url, "🚀 Pipeline Started", message, color=0x3498DB
        )

    if tg_token:
        html_msg = (
            f"🚀 <b>Pipeline Started</b>\n"
            f"📖 {novel_title}\n"
            f"📄 Chapters {chapter_start} - {chapter_end}"
        )
        send_telegram_notification(tg_token, tg_chat, html_msg)


def notify_pipeline_complete(
    novel_title: str,
    chapter_start: int,
    chapter_end: int,
    duration_seconds: float,
    errors: int = 0,
    release_url: str = "",
):
    """Send notification when pipeline completes."""
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")

    status = "✅ Success" if errors == 0 else f"⚠️ Completed with {errors} errors"
    duration_human = _format_duration(duration_seconds)

    message = (
        f"{status}\n"
        f"📖 {novel_title}\n"
        f"📄 Chapters {chapter_start} - {chapter_end}\n"
        f"⏱ Duration: {duration_human}"
    )

    if release_url:
        message += f"\n🔗 [Release]({release_url})"

    color = 0x2ECC71 if errors == 0 else 0xE67E22

    if discord_url:
        send_discord_notification(
            discord_url, "Pipeline Complete", message, color=color,
            fields=[
                {"name": "Duration", "value": duration_human, "inline": True},
                {"name": "Errors", "value": str(errors), "inline": True},
            ]
        )

    if tg_token:
        html_msg = (
            f"{status}\n"
            f"📖 {novel_title}\n"
            f"📄 Chapters {chapter_start} - {chapter_end}\n"
            f"⏱ {duration_human}"
        )
        send_telegram_notification(tg_token, tg_chat, html_msg)


def notify_error(component: str, error: str, chapter: Optional[int] = None):
    """Send error notification."""
    discord_url = os.environ.get("DISCORD_WEBHOOK_URL")

    if discord_url:
        message = f"**Component**: {component}\n**Error**: {error}"
        if chapter:
            message += f"\n**Chapter**: {chapter}"

        send_discord_notification(
            discord_url, "❌ Pipeline Error", message, color=0xE74C3C
        )


def _format_duration(seconds: float) -> str:
    """Format seconds to human readable duration."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"
