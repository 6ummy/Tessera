"""FCM web push — notify a persona's followers when it rebalances.

Keyless by design (CS-9: fewer long-lived secrets). On Cloud Run the worker
SA's OAuth token comes straight from the metadata server; the only setup is
an IAM binding granting that SA `firebasecloudmessaging` on the Firebase
project (docs/runbooks/firebase-auth.md). No service-account key to store.

Gated on FEATURE_FCM_PUSH — off (and on any local box without the metadata
server) it logs "would notify N" and sends nothing, so it ships dark.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from tessera_worker.config import get_settings
from tessera_worker.logging import get_logger

log = get_logger(__name__)

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)
_FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"


def build_message(token: str, title: str, body: str, link: str | None = None) -> dict[str, Any]:
    """An FCM HTTP v1 message envelope for one device token. Pure — unit-tested."""
    msg: dict[str, Any] = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
        }
    }
    if link:
        msg["message"]["webpush"] = {"fcm_options": {"link": link}}
    return msg


def _access_token() -> str | None:
    """Worker SA OAuth token from the Cloud Run metadata server (cloud-platform
    scope, which covers FCM when IAM allows). None off-GCP (local/tests)."""
    try:
        resp = httpx.get(
            _METADATA_TOKEN_URL,
            headers={"Metadata-Flavor": "Google"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])
    except Exception as e:
        log.warning("fcm.metadata_token_failed", err=f"{type(e).__name__}: {e}")
        return None


def _followers_tokens(session: Session, persona: str) -> list[str]:
    rows = session.execute(text("""
        SELECT DISTINCT t.token
        FROM fcm_tokens t
        JOIN user_portfolios up ON up.user_id = t.user_id
        WHERE up.persona_id = :p
    """), {"p": persona}).all()
    return [r.token for r in rows]


def notify_persona_followers(
    session: Session, persona: str, *, title: str, body: str, link: str | None = None,
) -> dict[str, Any]:
    """Push a notification to everyone following `persona`. Best-effort: a
    send failure for one token never raises (a notification must never break
    the weekly batch). Returns a small summary for the batch log."""
    settings = get_settings()
    tokens = _followers_tokens(session, persona)
    if not tokens:
        return {"followers": 0, "sent": 0, "skipped_reason": "no_followers"}

    if not settings.feature_fcm_push:
        log.info("fcm.would_notify", persona=persona, followers=len(tokens),
                 reason="FEATURE_FCM_PUSH=false")
        return {"followers": len(tokens), "sent": 0, "skipped_reason": "flag_off"}

    access = _access_token()
    if not access:
        return {"followers": len(tokens), "sent": 0, "skipped_reason": "no_token"}

    url = _FCM_SEND_URL.format(project=settings.fcm_project_id)
    headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}
    sent = 0
    stale: list[str] = []
    for tok in tokens:
        try:
            r = httpx.post(
                url, headers=headers,
                json=build_message(tok, title, body, link), timeout=10.0,
            )
            if r.status_code == 200:
                sent += 1
            elif r.status_code in (404, 410):
                # UNREGISTERED / token gone — prune it.
                stale.append(tok)
            else:
                log.warning("fcm.send_non_200", persona=persona, status=r.status_code,
                            detail=r.text[:200])
        except Exception as e:
            log.warning("fcm.send_failed", persona=persona, err=f"{type(e).__name__}: {e}")

    if stale:
        session.execute(
            text("DELETE FROM fcm_tokens WHERE token = ANY(:t)"), {"t": stale}
        )
        log.info("fcm.pruned_stale", persona=persona, n=len(stale))

    log.info("fcm.notified", persona=persona, followers=len(tokens), sent=sent, pruned=len(stale))
    return {"followers": len(tokens), "sent": sent, "pruned": len(stale)}
