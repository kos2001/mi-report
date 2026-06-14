"""다이제스트 메일 발송 테스트.

렌더링은 네트워크 없이, 발송 엔드포인트는 SMTP 미설정(미리보기)·설정(발송 모킹)을 검증.
"""

from __future__ import annotations

from app import mailer, profiles

_DIGEST = {
    "issueNo": 47,
    "period": "2026.06.08 – 06.11",
    "items": [
        {
            "title": "HBM4 채택 공식화 <검토>",
            "summary": "양산 2027 상반기.",
            "slsiRelevance": "HBM 컨트롤러 IP.",
            "demandImpact": "패키징 캐파 경쟁.",
            "risk": "단일 출처 — 교차검증 필요.",
            "impact": "high",
            "tags": ["HBM", "AI가속기"],
        }
    ],
}


# ── 렌더링 ─────────────────────────────────────────────────────────────────
def test_render_digest_email():
    subject, text, html = mailer.render_digest_email(_DIGEST)
    assert "제47호" in subject
    assert "HBM4 채택 공식화" in text
    assert "[상]" in text  # impact high → 상
    assert "교차검증" in text
    assert "<div" in html
    # HTML 이스케이프(제목의 < > 가 그대로 들어가지 않음)
    assert "<검토>" not in html
    assert "&lt;검토&gt;" in html


def test_smtp_config_none_when_unset(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.setattr(profiles, "load_profile", lambda *a, **k: None)
    assert mailer.smtp_config() is None


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
def test_digest_send_dry_run(client, monkeypatch):
    monkeypatch.setattr(profiles, "load_profile", lambda *a, **k: None)
    r = client.post("/digest/send", json={**_DIGEST, "dryRun": True})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_sent"
    assert body["reason"] == "dryRun"
    assert "HBM4" in body["preview"]


def test_digest_send_not_configured(client, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.setattr(profiles, "load_profile", lambda *a, **k: None)
    r = client.post("/digest/send", json=_DIGEST)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not_sent"
    assert "SMTP 미설정" in body["reason"]
    assert "preview" in body


def test_digest_send_sent_when_configured(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "mi@example.com")
    monkeypatch.setenv("SMTP_TO", "team@example.com")
    monkeypatch.setattr(profiles, "load_profile", lambda *a, **k: None)
    sent = {}

    def fake_send(cfg, subject, text, html, to, **kw):
        sent["to"] = to
        sent["subject"] = subject

    monkeypatch.setattr(mailer, "send_email", fake_send)
    r = client.post("/digest/send", json=_DIGEST)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "sent"
    assert sent["to"] == ["team@example.com"]
    assert "제47호" in sent["subject"]


def test_digest_send_error_returns_preview(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.invalid")
    monkeypatch.setenv("SMTP_FROM", "mi@example.com")
    monkeypatch.setenv("SMTP_TO", "team@example.com")
    monkeypatch.setattr(profiles, "load_profile", lambda *a, **k: None)

    def boom(*a, **k):
        raise OSError("connection refused (사내망 미연동)")

    monkeypatch.setattr(mailer, "send_email", boom)
    r = client.post("/digest/send", json=_DIGEST)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "preview" in body
    assert "connection refused" in body["detail"]
