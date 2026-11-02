"""이메일 인증: 인증 메일 보내기와 링크 확인.

- 링크의 토큰은 무작위 32바이트이고 DB 에는 SHA-256 해시만 둔다. 한 번 쓰면 끝, EMAIL_TOKEN_TTL_HOURS 뒤 만료.
- 토큰은 보낸 주소에 묶인다. 그 뒤 주소를 바꾸면 예전 링크로는 새 주소가 인증되지 않는다.
- 같은 주소(email_key)는 한 계정만 인증할 수 있다. 인증 전 주소는 겹쳐도 된다 (남의 주소를 먼저 적어 가입을 막지 못하게).
- 보내기 횟수: 회원마다 60초에 1통, 24시간에 5통, 서비스 전체 24시간 EMAIL_DAILY_LIMIT 통 (usage_events "email").
"""

from __future__ import annotations

import hashlib
import html
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError, ConflictError, ForbiddenError, QuotaExceededError
from app.mailer import Mail, Mailer, MailError
from app.models import EmailToken, User
from app.services import usage

log = logging.getLogger(__name__)

TOKEN_BYTES = 32
MAX_TOKEN_LEN = 128
RESEND_COOLDOWN = timedelta(seconds=60)
PER_USER_DAILY = 5
PER_IP_DAILY = 20          # 같은 IP(IPv6 /56)에서 24시간 (계정 여러 개로 서비스 전체 상한을 다 쓰지 못하게)
UNVERIFIED_LIFETIME = 10   # 한 계정이 받을 수 있는 인증 메일 수 (평생: 인증하지 않는 계정이 매일 한도를 다시 쓰지 못하게)
LIFETIME = timedelta(days=36500)


class InvalidTokenError(AppError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__("인증 링크가 올바르지 않거나 만료됐어요. 인증 메일을 다시 받아 주세요.", code="invalid_token")


class EmailUnverifiedError(ForbiddenError):
    def __init__(self) -> None:
        super().__init__("이메일 인증을 마치면 쓸 수 있어요. 받은 메일의 링크를 누르거나 인증 메일을 다시 받아 주세요.",
                         code="email_unverified")


class EmailUnavailableError(AppError):
    status_code = 503

    def __init__(self) -> None:
        super().__init__("지금은 회원가입을 할 수 없어요 (메일 설정 점검 중). 잠시 뒤 다시 시도해 주세요.",
                         code="email_unavailable")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite 는 시간대 없이 돌려주므로 UTC 로 본다."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def needs_verification(settings: Settings, user: User) -> bool:
    """이 회원이 인증 전이라 막아야 하는지. 관리자와 인증이 꺼진 환경은 막지 않는다.
    (메일 설정 오류(misconfigured)일 때도 기존 회원은 막지 않는다: 인증할 방법이 없으므로. 대신 신규 가입을 막는다)"""
    return settings.email_mode == "enabled" and not user.is_admin and user.email_verified_at is None


def verified_email_taken(db: Session, key: str, exclude_user_id: str | None = None) -> bool:
    q = select(User.id).where(User.email_key == key, User.email_verified_at.is_not(None))
    if exclude_user_id is not None:
        q = q.where(User.id != exclude_user_id)
    return db.scalar(q.limit(1)) is not None


def _mail(user: User, link: str, ttl_hours: float) -> Mail:
    hours = f"{ttl_hours:g}"
    text = (
        f"{user.nickname}님, NestForge 에 오신 것을 환영해요.\n\n"
        f"아래 링크를 눌러 이메일 주소를 인증해 주세요. 링크는 {hours}시간 동안 한 번만 쓸 수 있어요.\n\n"
        f"{link}\n\n"
        "직접 가입하거나 이메일을 바꾸지 않았다면 이 메일은 무시해 주세요.\n"
        "— NestForge"
    )
    nick, href = html.escape(user.nickname), html.escape(link, quote=True)
    body = (
        '<div style="font-family:sans-serif;line-height:1.6;color:#1f2937">'
        f"<p>{nick}님, NestForge 에 오신 것을 환영해요.</p>"
        f"<p>아래 버튼을 눌러 이메일 주소를 인증해 주세요. 링크는 {hours}시간 동안 한 번만 쓸 수 있어요.</p>"
        f'<p><a href="{href}" style="display:inline-block;padding:10px 18px;background:#b45309;color:#fff;'
        'border-radius:8px;text-decoration:none;font-weight:600">이메일 인증하기</a></p>'
        f'<p style="font-size:13px;color:#6b7280">버튼이 열리지 않으면 이 주소를 복사해 열어 주세요:<br>{href}</p>'
        '<p style="font-size:13px;color:#6b7280">직접 가입하거나 이메일을 바꾸지 않았다면 이 메일은 무시해 주세요.</p>'
        "</div>"
    )
    return Mail(to=user.email or "", subject="[NestForge] 이메일 주소를 인증해 주세요", text=text, html=body)


def send_verification(db: Session, settings: Settings, mailer: Mailer, user: User, ip_key: str | None = None) -> bool:
    """보내기 횟수를 확인·기록하고 새 링크를 만들어 보낸다.
    상한에 닿았으면 QuotaExceededError (기록·발송 안 함). 메일 서비스 오류면 False (다시 보내기를 안내)."""
    if not user.email:
        raise AppError("내 정보에서 이메일을 먼저 등록해 주세요.", code="email_required")
    if usage.count(db, "email", user_id=user.id, window=LIFETIME) >= UNVERIFIED_LIFETIME:
        raise QuotaExceededError("인증 메일을 너무 많이 보냈어요. 받은 편지함과 스팸함을 확인하거나 운영팀에 문의해 주세요.",
                                 code="too_many_emails")
    usage.reserve(
        db, "email", user, ip_key=ip_key,
        cooldown=(RESEND_COOLDOWN, usage.Cap(1, "인증 메일을 방금 보냈어요. 1분 뒤에 다시 보낼 수 있어요.", "email_cooldown")),
        per_user=usage.Cap(PER_USER_DAILY, "인증 메일은 24시간에 5번까지 보낼 수 있어요. 받은 편지함과 스팸함을 확인해 주세요.",
                           "too_many_emails"),
        per_ip=usage.Cap(PER_IP_DAILY, "이 네트워크에서 인증 메일 요청이 너무 많았어요. 잠시 뒤 다시 시도해 주세요.",
                         "too_many_emails"),
        global_=usage.Cap(settings.email_daily_limit, "오늘은 인증 메일을 더 보낼 수 없어요. 내일 다시 시도해 주세요.",
                          "too_many_emails"),
    )
    token = secrets.token_urlsafe(TOKEN_BYTES)
    db.add(EmailToken(token_hash=_hash(token), user_id=user.id, purpose="verify", email=user.email,
                      expires_at=_now() + timedelta(hours=settings.email_token_ttl_hours)))
    db.commit()  # 발송(네트워크) 동안 DB 연결을 쥐고 있지 않게 먼저 커밋한다
    link = f"{settings.email_base_url}/verify-email?token={token}"
    try:
        mailer.send(_mail(user, link, settings.email_token_ttl_hours))
    except MailError as e:
        log.error("인증 메일을 보내지 못했습니다 (user=%s): %s", user.id, e)
        return False
    return True


def forget_tokens(db: Session, user_id: str) -> None:
    """이 회원의 인증 링크를 모두 무효로 한다 (이메일을 바꿀 때). 커밋은 호출한 쪽에서."""
    db.execute(delete(EmailToken).where(EmailToken.user_id == user_id))


def verify(db: Session, token: str) -> None:
    """링크의 토큰으로 이메일을 인증한다 (이미 인증된 회원이면 그대로 성공).

    쓰기는 모두 조건부 UPDATE 로 한다: 동시에 이메일을 바꾸거나 같은 링크를 두 번 눌러도
    (1) 토큰은 한 번만 쓰이고 (2) 링크를 보낸 주소가 지금 주소일 때만 인증된다."""
    if not token or len(token) > MAX_TOKEN_LEN or not token.isascii():
        raise InvalidTokenError()
    h = _hash(token)
    row = db.get(EmailToken, h)
    now = _now()
    if row is None or row.purpose != "verify" or row.used_at is not None or _aware(row.expires_at) < now:
        raise InvalidTokenError()
    user_id, address = row.user_id, row.email
    try:
        used = db.execute(update(EmailToken).where(EmailToken.token_hash == h, EmailToken.used_at.is_(None))
                          .values(used_at=now))
        if used.rowcount != 1:  # 같은 링크를 동시에 눌렀다
            raise InvalidTokenError()
        current = db.execute(select(User.email, User.email_key, User.email_verified_at)
                             .where(User.id == user_id)).one_or_none()
        if current is None or current.email != address:  # 링크를 보낸 뒤 주소를 바꿨다
            raise InvalidTokenError()
        if current.email_verified_at is None:
            if verified_email_taken(db, current.email_key or "", exclude_user_id=user_id):
                raise ConflictError("이 이메일은 이미 다른 계정에서 인증했어요. 다른 이메일로 바꿔 주세요.",
                                    code="email_taken")
            done = db.execute(update(User).where(User.id == user_id, User.email == address,
                                                 User.email_verified_at.is_(None)).values(email_verified_at=now))
            if done.rowcount != 1:  # 그 사이 주소가 바뀌었거나 이미 인증됐다: 다시 확인
                again = db.execute(select(User.email, User.email_verified_at).where(User.id == user_id)).one_or_none()
                if again is None or again.email != address or again.email_verified_at is None:
                    raise InvalidTokenError()
        db.commit()
    except IntegrityError:  # 같은 주소를 두 계정이 동시에 인증 (ux_users_email_key_verified)
        db.rollback()
        raise ConflictError("이 이메일은 이미 다른 계정에서 인증했어요. 다른 이메일로 바꿔 주세요.",
                            code="email_taken") from None
    except BaseException:
        db.rollback()
        raise


def set_email(db: Session, user: User, address: str, key: str) -> None:
    """이메일을 바꾸고 인증 전으로 되돌린다 (조건 없는 UPDATE: 메모리의 user 가 오래됐어도 인증 표시를 반드시 지운다).
    이 회원의 예전 링크도 모두 지운다. 커밋은 호출한 쪽에서."""
    db.execute(update(User).where(User.id == user.id)
               .values(email=address, email_key=key, email_verified_at=None))
    forget_tokens(db, user.id)
    user.email, user.email_key, user.email_verified_at = address, key, None
