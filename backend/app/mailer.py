"""메일 보내기 (이메일 인증 링크).

공급자: smtp (표준 라이브러리 smtplib) · resend (Resend HTTP API) · file (로컬 개발·테스트: 한 통에 JSON 파일 하나).
비밀값(SMTP 비밀번호·API 키)은 로그에 남기지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import time
import uuid
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

SEND_TIMEOUT_S = 15.0


class MailError(RuntimeError):
    """메일을 보내지 못했다 (공급자 오류·네트워크). 사용자에게는 '다시 보내기'를 안내한다."""


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    def send(self, mail: Mail) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.host = settings.smtp_host.strip()
        self.port = settings.smtp_port
        self.username = settings.smtp_username.strip()
        self.password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
        self.security = settings.smtp_security
        self.sender = settings.email_from.strip()

    def send(self, mail: Mail) -> None:
        msg = EmailMessage()
        name, addr = parseaddr(self.sender)
        msg["From"] = formataddr((name, addr)) if name else addr
        msg["To"] = mail.to
        msg["Subject"] = mail.subject
        msg["Message-ID"] = make_msgid(domain=addr.rpartition("@")[2] or None)
        msg.set_content(mail.text)
        msg.add_alternative(mail.html, subtype="html")
        context = ssl.create_default_context()
        try:
            if self.security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=SEND_TIMEOUT_S, context=context)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=SEND_TIMEOUT_S)
            with server:
                if self.security == "starttls":
                    server.starttls(context=context)
                if self.username:
                    server.login(self.username, self.password)
                server.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            raise MailError(f"SMTP 발송 실패: {type(e).__name__}") from None


class ResendMailer:
    API_URL = "https://api.resend.com/emails"

    def __init__(self, settings: Settings):
        self.api_key = settings.resend_api_key.get_secret_value() if settings.resend_api_key else ""
        self.sender = settings.email_from.strip()

    def send(self, mail: Mail) -> None:
        try:
            r = httpx.post(
                self.API_URL, timeout=SEND_TIMEOUT_S,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"from": self.sender, "to": [mail.to], "subject": mail.subject, "text": mail.text,
                      "html": mail.html},
            )
        except httpx.HTTPError as e:
            raise MailError(f"Resend 연결 실패: {type(e).__name__}") from None
        if r.status_code >= 300:
            # 응답 본문에는 비밀값이 없다 (오류 이름·메시지). 길이만 줄여 남긴다
            raise MailError(f"Resend 발송 실패: HTTP {r.status_code} {r.text[:200]}")


class FileMailer:
    """로컬 개발·테스트용: 메일을 보내지 않고 EMAIL_OUTBOX_DIR 에 JSON 으로 저장한다."""

    def __init__(self, outbox: Path):
        self.outbox = Path(outbox)

    def send(self, mail: Mail) -> None:
        self.outbox.mkdir(parents=True, exist_ok=True)
        name = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}.json"
        tmp = self.outbox / f".{name}.tmp"
        tmp.write_text(json.dumps(asdict(mail), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.outbox / name)  # 읽는 쪽이 반쯤 쓴 파일을 보지 않게
        log.info("메일을 파일로 저장했습니다 (EMAIL_PROVIDER=file): %s", self.outbox / name)


class MemoryMailer:
    """테스트용: 보낸 메일을 목록에 쌓는다. fail=True 이면 MailError."""

    def __init__(self, fail: bool = False):
        self.sent: list[Mail] = []
        self.fail = fail

    def send(self, mail: Mail) -> None:
        if self.fail:
            raise MailError("테스트: 발송 실패")
        self.sent.append(mail)


def make_mailer(settings: Settings) -> Mailer | None:
    if settings.email_mode != "enabled":
        return None
    if settings.email_provider == "smtp":
        return SmtpMailer(settings)
    if settings.email_provider == "resend":
        return ResendMailer(settings)
    return FileMailer(settings.email_outbox_dir)
