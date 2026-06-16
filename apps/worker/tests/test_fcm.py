"""FCM message-envelope tests — the pure builder. Sends/IO are not exercised
here (they need the Cloud Run metadata server + real tokens)."""

from __future__ import annotations

from tessera_worker.notify.fcm import build_message


def test_build_message_basic():
    m = build_message("tok123", "Warren rebalanced", "new book")["message"]
    assert m["token"] == "tok123"
    assert m["notification"] == {"title": "Warren rebalanced", "body": "new book"}
    assert "webpush" not in m  # no link → no webpush block


def test_build_message_with_link():
    m = build_message("tok123", "t", "b", link="/dashboard")["message"]
    assert m["webpush"]["fcm_options"]["link"] == "/dashboard"
