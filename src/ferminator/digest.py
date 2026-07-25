"""Idempotent digest composition and SMTP delivery."""

from __future__ import annotations

import hashlib
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape


@dataclass(frozen=True)
class Digest:
    subject: str
    text: str
    html: str
    idempotency_key: str


def compose_digest(display_name: str, matches: list[dict]) -> Digest:
    today = datetime.now(UTC).date().isoformat()
    top = matches[:5]
    identity = "|".join(
        [today, display_name, *(f"{item['company_name']}:{item['title']}" for item in top)]
    )
    key = hashlib.sha256(identity.encode()).hexdigest()
    subject = f"Ferminator briefing: {len(top)} opportunities for {display_name}"
    if top:
        lines = [
            f"{index}. {item['title']} — {item['company_name']} ({float(item['score']):.0f}% match)"
            for index, item in enumerate(top, 1)
        ]
        text = (
            f"Good morning, {display_name}.\n\n"
            "These opportunities deserve attention:\n\n"
            + "\n".join(lines)
            + "\n\nOpen Ferminator for evidence, concerns, and next actions."
        )
        cards = "".join(
            "<li style='margin:0 0 18px'>"
            f"<strong>{escape(item['title'])}</strong><br>"
            f"{escape(item['company_name'])} · {float(item['score']):.0f}% alignment<br>"
            f"<a href='{escape(str(item['job_url']))}'>View original listing</a>"
            "</li>"
            for item in top
        )
    else:
        text = (
            f"Good morning, {display_name}.\n\n"
            "No new high-confidence matches are ready today. Ferminator is still scanning."
        )
        cards = "<li>No new high-confidence matches are ready today.</li>"
    html = (
        "<div style='font-family:Inter,Arial,sans-serif;color:#16181D;max-width:620px'>"
        f"<h1 style='font-family:Georgia,serif'>Good morning, {escape(display_name)}.</h1>"
        "<p>Your private career radar found:</p><ol>"
        f"{cards}</ol><p style='color:#687386'>Every score is explainable in Ferminator.</p></div>"
    )
    return Digest(subject=subject, text=text, html=html, idempotency_key=key)


def send_smtp(
    digest: Digest,
    *,
    recipient: str,
    sender: str,
    host: str,
    port: int,
    username: str | None = None,
    password: str | None = None,
) -> None:
    message = EmailMessage()
    message["Subject"] = digest.subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(digest.text)
    message.add_alternative(digest.html, subtype="html")
    with smtplib.SMTP(host, port, timeout=20) as smtp:
        smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
