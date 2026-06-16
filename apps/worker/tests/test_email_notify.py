"""Email rebalance-alert builder tests (pure). Sending needs RESEND_API_KEY
+ network, not exercised here."""

from __future__ import annotations

from tessera_worker.notify.email import build_email


def test_build_email_subject_and_link():
    subject, html = build_email("warren")
    assert subject == "Warren rebalanced — new book on Tessera"
    assert "Warren just rebalanced." in html
    assert "https://tessera-ruby.vercel.app/dashboard" in html


def test_build_email_custom_path():
    _subject, html = build_email("cathie", "/dashboard?tab=portfolio")
    assert "Cathie" in html
    assert "/dashboard?tab=portfolio" in html
