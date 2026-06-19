"""Email notifications — rebalance alerts in parallel with FCM push.

Web push reaches desktop Chrome / Android well but skips iOS (no PWA) and
anyone who didn't enable it, so email is the reliable second channel for a
weekly, low-volume alert. Sent from the worker via Resend's HTTP API
(one secret, RESEND_API_KEY). Gated on FEATURE_EMAIL_NOTIFY — off → logs
"would email N" and sends nothing (ships dark).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.config import get_settings
from tessera_worker.logging import get_logger

log = get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_SITE_URL = "https://tessera-ruby.vercel.app"


def unsub_url(user_id: str, secret: str) -> str | None:
    """One-click unsubscribe link (HMAC-SHA256 over the user id). Must match
    the web verifier (apps/web/lib/unsubscribe.ts) — same secret, same hex
    digest. Blank secret → no link."""
    if not secret or not user_id:
        return None
    token = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return f"{_SITE_URL}/api/unsubscribe?u={user_id}&t={token}"


def build_email(
    persona: str, link_path: str = "/dashboard", unsubscribe_url: str | None = None,
) -> tuple[str, str]:
    """(subject, html) for a rebalance alert. Pure — unit-tested."""
    name = persona.title()
    url = f"{_SITE_URL}{link_path}"
    subject = f"{name} rebalanced — new book on Convt"
    opt_out = (
        f' <a href="{unsubscribe_url}" style="color:#7C7870">Unsubscribe</a>.'
        if unsubscribe_url else ""
    )
    html = (
        f'<div style="font-family:system-ui,sans-serif;max-width:520px">'
        f"<h2 style=\"font-weight:600\">{name} just rebalanced.</h2>"
        f"<p>{name} published a new weekly book. Your paper portfolio that "
        f"follows {name} is updating to match.</p>"
        f'<p><a href="{url}" style="display:inline-block;background:#1F1E1B;'
        f'color:#FAF9F5;padding:10px 18px;border-radius:9999px;'
        f'text-decoration:none">View your dashboard</a></p>'
        f'<p style="color:#7C7870;font-size:12px">Paper trading only — no real '
        f"money. You're receiving this because you follow {name} on Convt.{opt_out}</p>"
        f"</div>"
    )
    return subject, html


def _follower_rows(session: Session, persona: str) -> list[tuple[str, str]]:
    # Opt-out model: email unless the user set preferences.email_notify=false.
    # Returns (email, user_id) so each email can carry a per-user unsub link.
    rows = session.execute(text("""
        SELECT DISTINCT u.id, u.email
        FROM user_portfolios up
        JOIN users u ON u.id = up.user_id
        WHERE up.persona_id = :p
          AND u.email IS NOT NULL AND u.email <> ''
          AND (u.preferences ->> 'email_notify') IS DISTINCT FROM 'false'
    """), {"p": persona}).all()
    return [(r.email, str(r.id)) for r in rows]


def email_persona_followers(session: Session, persona: str) -> dict[str, Any]:
    """Email everyone following `persona`. Best-effort: one address failing
    never raises (a notification must not break the batch)."""
    settings = get_settings()
    recipients = _follower_rows(session, persona)
    if not recipients:
        return {"recipients": 0, "sent": 0, "skipped_reason": "no_followers"}
    if not settings.feature_email_notify or not settings.resend_api_key:
        log.info("email.would_email", persona=persona, recipients=len(recipients),
                 reason="flag_off_or_no_key")
        return {"recipients": len(recipients), "sent": 0, "skipped_reason": "disabled"}

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    secret = settings.unsubscribe_secret
    sent = 0
    for to, user_id in recipients:
        # Per-recipient one-click unsubscribe link (None when no secret set).
        subject, html = build_email(persona, unsubscribe_url=unsub_url(user_id, secret))
        try:
            r = httpx.post(_RESEND_URL, headers=headers, timeout=10.0, json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html,
            })
            if r.status_code in (200, 201):
                sent += 1
            else:
                log.warning("email.send_non_2xx", persona=persona,
                            status=r.status_code, detail=r.text[:200])
        except Exception as e:
            log.warning("email.send_failed", persona=persona,
                        err=f"{type(e).__name__}: {e}")
    log.info("email.notified", persona=persona, recipients=len(recipients), sent=sent)
    return {"recipients": len(recipients), "sent": sent}
