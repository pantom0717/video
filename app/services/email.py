"""Lead notification email.

폼 신청이 들어오면 운영자(우리) 메일로 내용을 보낸다.
provider 로 무료 경로를 고를 수 있다:
  - console : 발송 안 하고 로그만 (기본 — 키 없이도 안 죽음)
  - smtp    : Gmail 앱 비밀번호 등 SMTP (무료)
  - resend  : Resend API (무료 티어)

발송 실패는 본 작업(리드 저장)을 막지 않는다 — 경고로만 남긴다.
"""
from __future__ import annotations

import sys

from app.config import settings
from app.models import LeadRecord


def _safe_log(message: str) -> None:
    """콘솔 인코딩(cp949 등)에 막혀도 절대 예외를 던지지 않는다."""
    try:
        sys.stdout.write(message + "\n")
    except Exception:  # noqa: BLE001
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write((message + "\n").encode(enc, errors="replace"))


def _subject(lead: LeadRecord) -> str:
    return f"[kiwi 신청] {lead.brand_name} — {lead.email}"


def _body(lead: LeadRecord) -> str:
    return "\n".join(
        [
            "새 무료 샘플 신청이 들어왔어요.",
            "",
            f"브랜드명   : {lead.brand_name}",
            f"인스타그램 : {lead.instagram_url}",
            f"레퍼런스   : {lead.reference_url or '(없음 — kiwi가 찾아드림)'}",
            f"이메일     : {lead.email}",
            f"제품명     : {lead.product_name or '(미입력)'}",
            f"타깃 고객  : {lead.target_customer or '(미입력)'}",
            f"핵심 소구점: {lead.main_benefit or '(미입력)'}",
            f"비고       : {lead.notes or '-'}",
            "",
            f"lead_id    : {lead.lead_id}",
            f"접수 시각  : {lead.created_at.isoformat()}",
        ]
    )


def send_lead_notification(lead: LeadRecord) -> tuple[bool, str]:
    """(성공여부, 메시지) 반환. 절대 예외를 던지지 않는다."""
    provider = (settings.email_provider or "console").lower().strip()
    to_addr = settings.notify_email.strip()

    if provider == "console" or not to_addr:
        # 수신 메일 미설정이면 콘솔로만 (MVP — 나중에 notify_email 채우면 실제 발송)
        _safe_log(f"[email:console] would notify {to_addr or '<NOTIFY_EMAIL unset>'}\n{_subject(lead)}\n{_body(lead)}")
        reason = "console_only" if provider == "console" else "no_notify_email"
        return False, reason

    try:
        if provider == "smtp":
            return _send_smtp(to_addr, _subject(lead), _body(lead))
        if provider == "resend":
            return _send_resend(to_addr, _subject(lead), _body(lead))
        return False, f"unknown_provider:{provider}"
    except Exception as exc:  # noqa: BLE001 - 비치명적: 발송 실패가 리드 저장을 막지 않음
        return False, f"email_send_failed:{exc}"


def _send_smtp(to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    import smtplib
    from email.mime.text import MIMEText

    if not (settings.smtp_user and settings.smtp_password):
        return False, "smtp_credentials_missing"

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = to_addr

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(msg["From"], [to_addr], msg.as_string())
    return True, "sent_smtp"


def _send_resend(to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    import json
    import urllib.request

    if not settings.resend_api_key:
        return False, "resend_api_key_missing"

    payload = json.dumps(
        {
            "from": settings.email_from,
            "to": [to_addr],
            "subject": subject,
            "text": body,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - 고정 호스트
        if 200 <= resp.status < 300:
            return True, "sent_resend"
        return False, f"resend_http_{resp.status}"
