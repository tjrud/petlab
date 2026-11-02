"""CAPTCHA 확인 (Cloudflare Turnstile). 비밀 키는 로그에 남기지 않는다."""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from app.config import Settings
from app.errors import AppError

log = logging.getLogger(__name__)

MAX_TOKEN_LEN = 2048  # Turnstile 토큰은 최대 2048자
VERIFY_TIMEOUT_S = 8.0

# (token, remote_ip) → 통과 여부. 테스트에서 바꿔 끼울 수 있다 (create_app(captcha_verifier=...))
CaptchaVerifier = Callable[[str, str | None], bool]


class CaptchaFailedError(AppError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__("로봇이 아닌지 확인하지 못했어요. 확인 상자를 다시 눌러 주세요.", code="captcha_failed")


class CaptchaUnavailableError(AppError):
    status_code = 503

    def __init__(self) -> None:
        super().__init__("지금은 로봇 확인을 할 수 없어요. 잠시 뒤 다시 시도해 주세요.", code="captcha_unavailable")


def turnstile_verifier(settings: Settings) -> CaptchaVerifier:
    secret = settings.turnstile_secret_key.get_secret_value() if settings.turnstile_secret_key else ""
    url = settings.turnstile_verify_url

    def verify(token: str, remote_ip: str | None) -> bool:
        data = {"secret": secret, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip
        try:
            r = httpx.post(url, data=data, timeout=VERIFY_TIMEOUT_S)
            body = r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.error("Turnstile 확인 요청 실패: %s", type(e).__name__)
            raise CaptchaUnavailableError() from None
        if not body.get("success"):
            codes = body.get("error-codes") or []
            # 서버 설정 문제(잘못된 비밀 키 등)는 사용자 탓이 아니므로 따로 기록한다
            if any(c in ("missing-input-secret", "invalid-input-secret") for c in codes):
                log.error("Turnstile 비밀 키가 잘못됐습니다 (TURNSTILE_SECRET_KEY): %s", codes)
                raise CaptchaUnavailableError()
            return False
        return True

    return verify


def check_captcha(verifier: CaptchaVerifier | None, token: str | None, remote_ip: str | None) -> None:
    """CAPTCHA 가 켜져 있으면(verifier 가 있으면) 토큰을 확인한다. 실패하면 CaptchaFailedError."""
    if verifier is None:
        return
    if not token or len(token) > MAX_TOKEN_LEN or not token.isascii():
        raise CaptchaFailedError()
    if not verifier(token, remote_ip):
        raise CaptchaFailedError()
