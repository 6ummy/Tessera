"""Email rebalance-alert builder tests (pure). Sending needs RESEND_API_KEY
+ network, not exercised here."""

import hashlib
import hmac

from tessera_worker.notify.email import build_email, unsub_url


def test_build_email_subject_and_link():
    subject, html = build_email("warren")
    assert subject == "Warren rebalanced — new book on Tessera"
    assert "Warren just rebalanced." in html
    assert "https://tessera-ruby.vercel.app/dashboard" in html


def test_build_email_custom_path():
    _subject, html = build_email("cathie", "/dashboard?tab=portfolio")
    assert "Cathie" in html
    assert "/dashboard?tab=portfolio" in html


def test_build_email_unsubscribe_link():
    # No link by default; included (with the word "Unsubscribe") when provided.
    _s, html_off = build_email("warren")
    assert "Unsubscribe" not in html_off
    _s, html_on = build_email("warren", unsubscribe_url="https://x/api/unsubscribe?u=1&t=abc")
    assert "Unsubscribe" in html_on
    assert "https://x/api/unsubscribe?u=1&t=abc" in html_on


def test_unsub_url_matches_hmac_and_handles_blank():
    uid, secret = "11111111-2222-3333-4444-555555555555", "s3cr3t"
    url = unsub_url(uid, secret)
    assert url is not None
    expected = hmac.new(secret.encode(), uid.encode(), hashlib.sha256).hexdigest()
    assert url == f"https://tessera-ruby.vercel.app/api/unsubscribe?u={uid}&t={expected}"
    # Blank secret or empty id → no link.
    assert unsub_url(uid, "") is None
    assert unsub_url("", secret) is None
