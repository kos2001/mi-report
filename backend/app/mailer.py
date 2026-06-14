"""다이제스트 이메일 — 렌더링 + SMTP 발송.

배선은 완성: SMTP 환경변수가 설정되면 실제 발송하고, 미설정/연결 불가(사내 메일
미연동 등)면 발송하지 않고 미리보기(dry-run)를 돌려준다. 새 의존성 없이 stdlib
smtplib/email 만 사용한다.

환경변수(프로파일 .env 자동 로드):
  SMTP_HOST, SMTP_PORT(기본 587), SMTP_USER, SMTP_PASSWORD,
  SMTP_FROM, SMTP_TO(쉼표구분), SMTP_STARTTLS(기본 true)
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

_IMPACT_LABEL = {"high": "상", "medium": "중", "low": "하"}


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_digest_email(
    digest: dict[str, Any], *, subject: str | None = None
) -> tuple[str, str, str]:
    """다이제스트 → (제목, 평문, HTML). 발송/미리보기 공용."""
    issue = digest.get("issueNo", "")
    period = digest.get("period", "") or ""
    items = digest.get("items", []) or []
    subj = subject or f"[MI 다이제스트] 제{issue}호 — {period}".strip(" —")

    # 평문
    tlines = [f"MI 뉴스 다이제스트 제{issue}호  {period}".strip(), ""]
    for i, it in enumerate(items, 1):
        imp = _IMPACT_LABEL.get(it.get("impact", ""), it.get("impact", ""))
        tlines.append(f"{i}. [{imp}] {it.get('title', '')}")
        if it.get("summary"):
            tlines.append(f"   요약: {it['summary']}")
        if it.get("slsiRelevance"):
            tlines.append(f"   S.LSI: {it['slsiRelevance']}")
        if it.get("demandImpact"):
            tlines.append(f"   수요: {it['demandImpact']}")
        if it.get("risk"):
            tlines.append(f"   리스크: {it['risk']}")
        if it.get("tags"):
            tlines.append(f"   태그: {', '.join(it['tags'])}")
        tlines.append("")
    text = "\n".join(tlines).strip() or "항목 없음"

    # HTML
    blocks = []
    for it in items:
        imp = _IMPACT_LABEL.get(it.get("impact", ""), it.get("impact", ""))
        tags = " ".join(
            f"<span style='background:#27272a;color:#a1a1aa;border-radius:4px;"
            f"padding:1px 6px;font-size:11px;margin-right:4px'>{_esc(t)}</span>"
            for t in (it.get("tags") or [])
        )
        blocks.append(
            f"<div style='border:1px solid #27272a;border-radius:8px;padding:12px 14px;margin:0 0 10px'>"
            f"<div style='font-weight:600;color:#18181b'>[{_esc(imp)}] {_esc(it.get('title',''))}</div>"
            f"<div style='color:#3f3f46;margin-top:6px'>{_esc(it.get('summary',''))}</div>"
            f"<div style='color:#52525b;font-size:13px;margin-top:6px'>"
            f"<b>S.LSI</b> {_esc(it.get('slsiRelevance',''))}<br>"
            f"<b>수요</b> {_esc(it.get('demandImpact',''))}<br>"
            f"<b>리스크</b> {_esc(it.get('risk',''))}</div>"
            f"<div style='margin-top:8px'>{tags}</div>"
            f"</div>"
        )
    html = (
        f"<div style='font-family:sans-serif;max-width:680px;margin:0 auto'>"
        f"<h2 style='color:#18181b'>MI 뉴스 다이제스트 제{_esc(issue)}호 "
        f"<span style='font-weight:400;color:#71717a;font-size:14px'>{_esc(period)}</span></h2>"
        + ("".join(blocks) or "<p>항목 없음</p>")
        + "<p style='color:#a1a1aa;font-size:12px;margin-top:16px'>MI Report Agent 자동 생성 — 발송 전 검토 요망</p>"
        + "</div>"
    )
    return subj, text, html


def smtp_config() -> dict[str, Any] | None:
    """SMTP 설정을 환경변수에서 읽는다. 필수값(HOST·FROM) 없으면 None(미설정)."""
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM")
    if not host or not sender:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "sender": sender,
        "starttls": os.environ.get("SMTP_STARTTLS", "true").lower() != "false",
    }


def default_recipients() -> list[str]:
    raw = os.environ.get("SMTP_TO", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


def send_email(
    cfg: dict[str, Any], subject: str, text: str, html: str, to: list[str], *, timeout: float = 15.0
) -> None:
    """SMTP 로 메일 발송. 실패 시 예외 전파(호출자가 처리)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=timeout) as server:
        if cfg["starttls"]:
            server.starttls()
        if cfg["user"]:
            server.login(cfg["user"], cfg["password"] or "")
        server.send_message(msg)
