"""언어 (한국어·영어): 응답 번역 미들웨어, 카탈로그, 영어 설계 설명, 영어 인증 메일."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.testclient import TestClient

from app import i18n
from app.config import BACKEND_DIR
from app.domain import Cage
from app.i18n import HANGUL, Catalog
from app.llm.anthropic_client import AnthropicInterpreter
from app.llm.base import HabitatInfo, InterpretRequest
from app.llm.mock import MockInterpreter
from app.llm.prompts import SYSTEM_PROMPT, build_user_message
from app.mailer import MemoryMailer
from app.main import create_app
from app.models import UsageEvent
from app.rules.loader import load_rules
from tests.api_helpers import PW, create_habitat, make_settings
from tests.api_helpers import member_settings as settings

SMALL = {
    "입력값을 확인해 주세요.": "Check your input.",
    "은신처": "Hideout",
    "터널": "Tunnel",
    "{0} #{1}": "{0} #{1}",
    "{0}: 높이 {1}mm 가 케이지 높이 {2}mm 보다 높습니다.": "{0}: height {1} mm exceeds the cage height of {2} mm.",
}
NESTED = {"summary_ko": "은신처", "title": "은신처", "items": [{"label_ko": "터널"}, {"label_ko": "모르는 문구"}],
          "notes_ko": ["입력값을 확인해 주세요.", "은신처, 터널"], "display_name": "터널"}


@pytest.fixture
def small_catalog(monkeypatch):
    """다른 카탈로그 파일에 기대지 않게 작은 카탈로그로 바꾼다 (catalog() 는 lru_cache 라 함수째 바꾼다)."""
    cat = Catalog(SMALL)
    monkeypatch.setattr(i18n, "catalog", lambda: cat)
    return cat


@pytest.fixture
def client(tmp_path, small_catalog):
    app = create_app(make_settings(tmp_path))
    app.add_api_route("/__t/json", lambda: JSONResponse(NESTED))
    app.add_api_route("/__t/text", lambda: PlainTextResponse('{"summary_ko": "은신처"}'))
    with TestClient(app) as c:
        yield c


# ── 미들웨어 ────────────────────────────────────────────────


def test_english_header_translates_server_strings(client):
    r = client.get("/__t/json", headers={"X-Lang": "en"})
    assert r.status_code == 200 and "X-Lang" in r.headers["vary"]
    assert int(r.headers["content-length"]) == len(r.content)
    assert r.json() == {"summary_ko": "Hideout", "title": "은신처",  # _ko 열쇠만 바꾸고 다른 열쇠(회원 글 등)는 그대로
                        "items": [{"label_ko": "Tunnel"}, {"label_ko": "모르는 문구"}],
                        "notes_ko": ["Check your input.", "Hideout, Tunnel"], "display_name": "Tunnel"}


def test_korean_request_is_unchanged(client):
    for headers in ({}, {"X-Lang": "ko"}, {"X-Lang": "fr"}):
        assert client.get("/__t/json", headers=headers).json() == NESTED


def test_lang_cookie_and_header_priority(client):
    client.cookies.set("lang", "en")
    assert client.get("/__t/json").json()["summary_ko"] == "Hideout"
    assert client.get("/__t/json", headers={"X-Lang": "ko"}).json() == NESTED  # 헤더가 쿠키보다 먼저
    client.cookies.clear()
    assert client.get("/__t/json").json() == NESTED


def test_error_responses_are_translated(client):
    r = client.post("/habitats", json={"species": 1}, headers={"X-Lang": "en"})
    assert r.status_code == 422 and r.json()["detail"]["message_ko"] == "Check your input."
    r = client.post("/habitats", json={"species": 1})
    assert r.json()["detail"]["message_ko"] == "입력값을 확인해 주세요."


def test_non_json_responses_are_untouched(client):
    r = client.get("/__t/text", headers={"X-Lang": "en"})
    assert r.headers["content-type"].startswith("text/plain") and r.text == '{"summary_ko": "은신처"}'


# ── 카탈로그 ────────────────────────────────────────────────


def test_catalog_translate():
    cat = Catalog(SMALL)
    assert cat.translate("입력값을 확인해 주세요.") == "Check your input."
    assert cat.translate("  입력값을 확인해 주세요.") == "  Check your input."  # 앞뒤 공백 유지
    # 자리표시: 값은 그대로 옮기고, 한국어 값(구조물 이름)은 다시 바꾼다
    assert cat.translate("은신처 #1: 높이 320mm 가 케이지 높이 300mm 보다 높습니다.") == \
        "Hideout #1: height 320 mm exceeds the cage height of 300 mm."
    assert cat.translate("은신처, 터널") == "Hideout, Tunnel"
    assert cat.translate("은신처 · 모르는 문구") == "Hideout · 모르는 문구"
    assert cat.translate("모르는 문구") == "모르는 문구"
    assert cat.translate("English stays") == "English stays" and cat.translate("") == ""


def test_catalog_files_are_valid_and_cover_llm_strings():
    cat = i18n.catalog()
    for f in (BACKEND_DIR / "app" / "i18n" / "en").glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()), f
    assert cat.translate("요청이 많아 AI 설계가 잠시 지연되고 있어요. 잠시 후 다시 시도해 주세요.") == \
        "AI design is busy right now. Please try again in a moment."
    assert cat.translate("[개발용 모의 해석기] 요구사항을 키워드로 해석해 은신처, 터널을(를) 설계했습니다.") == \
        "[Dev mock interpreter] Read your request by keywords and designed: Hideout, Tunnel."


# ── 설계 설명 언어 ──────────────────────────────────────────


@pytest.fixture(scope="module")
def req() -> InterpretRequest:
    rules = load_rules(BACKEND_DIR / "rules")
    return InterpretRequest(
        prompt="A hideout on the left", habitat=HabitatInfo("hamster", "햄스터", "syrian", 1, Cage(600, 400, 300)),
        size_rules=rules.size_rules("hamster", "syrian"), min_wall_mm=rules.min_wall_for("hamster", "syrian"),
    )


def _mock(req, prompt, language="en", previous=None):
    r = InterpretRequest(prompt=prompt, habitat=req.habitat, size_rules=req.size_rules, min_wall_mm=req.min_wall_mm,
                         previous=previous, language=language)
    return MockInterpreter().interpret(r).spec


def _no_hangul(spec) -> bool:
    texts = [spec.summary_ko, *spec.notes_ko, *(it.reason_ko for it in spec.items)]
    return not any(HANGUL.search(t) for t in texts)


def test_mock_understands_english(req):
    spec = _mock(req, "Put a big hideout and a U-shaped tube together in the right corner")
    assert [it.template for it in spec.items] == ["hideout", "tunnel"]
    assert all(it.placement.zone == "back_right" and it.placement.group == "g1" for it in spec.items)
    assert spec.items[1].params.bend_angle_deg == 180
    assert spec.items[0].params.width_mm > _mock(req, "hideout").items[0].params.width_mm
    assert _no_hangul(spec) and "Golden (Syrian) hamster" in spec.items[0].reason_ko

    stairs = _mock(req, "Stairs with 5 steps at the front-left").items[0]
    assert stairs.template == "ramp" and stairs.params.steps == 5 and stairs.placement.zone == "front_left"
    assert _mock(req, "a ramp in the middle").items[0].params.steps == 0
    assert _mock(req, "sand bath at the back").items[0].template == "sand_bath"
    hide = _mock(req, "hideout with 10 vents and a 7 cm entrance").items[0].params
    assert hide.vent_count == 10 and hide.entrance_diameter_mm == 70
    assert _mock(req, "something nice").notes_ko == ["No specific structure was mentioned, so I designed one standard hideout."]


def test_mock_english_revision(req):
    v1 = _mock(req, "hideout and tunnel on the left")
    assert [it.template for it in _mock(req, "remove the tunnel", previous=v1).items] == ["hideout"]
    assert len(_mock(req, "add a sand bath", previous=v1).items) == 3
    v2 = _mock(req, "make it smaller", previous=v1)
    assert v2.items[0].params.width_mm < v1.items[0].params.width_mm and v2.items[0].placement.zone == "left"


def test_mock_korean_output_is_unchanged(req):
    spec = _mock(req, "은신처를 왼쪽에", language="ko")
    assert spec.summary_ko == "[개발용 모의 해석기] 요구사항을 키워드로 해석해 은신처을(를) 설계했습니다."
    assert spec.items[0].reason_ko.startswith("요구사항에서 '은신처'을(를) 찾아 햄스터 ")
    # 영어 페이지에서 한국어로 적어도 설명은 영어
    assert _no_hangul(_mock(req, "은신처를 왼쪽에", language="en"))


def test_english_instruction_goes_into_user_message(req):
    ko = build_user_message(req)
    en = build_user_message(InterpretRequest(**{**req.__dict__, "language": "en"}))
    assert "Output language" not in ko and "Output language" in en
    assert "summary_ko" in en and "Golden (Syrian) hamster" in en
    assert en.endswith("위 내용을 바탕으로 설계 JSON 을 출력하세요.")

    spec = {"summary_ko": "A hideout on the left.", "notes_ko": [], "items": [{
        "template": "hideout", "reason_ko": "Fits a Syrian.",
        "params": {"width_mm": 200, "depth_mm": 150, "height_mm": 120, "entrance_diameter_mm": 75,
                   "vent_count": 6, "vent_diameter_mm": 5, "wall_thickness_mm": 3},
        "placement": {"zone": "left", "group": None, "rotation": None}}]}
    calls: list[dict] = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(spec))])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    AnthropicInterpreter(client, "m").interpret(InterpretRequest(**{**req.__dict__, "language": "en"}))
    assert calls[0]["system"] == SYSTEM_PROMPT  # 시스템 프롬프트는 언어와 상관없이 같다 (캐시)
    assert "Output language" in calls[0]["messages"][0]["content"]


def test_english_request_creates_english_design(client):
    hid = create_habitat(client)
    r = client.post("/designs", json={"habitat_id": hid, "prompt": "A hideout on the left and a tunnel"},
                    headers={"X-Lang": "en"})
    assert r.status_code == 201, r.text
    cur = r.json()["current"]
    assert [it["template"] for it in cur["items"]] == ["hideout", "tunnel"]
    for text in (cur["summary_ko"], *cur["notes_ko"], *(it["reason_ko"] for it in cur["items"])):
        assert not HANGUL.search(text), text

    r = client.post("/designs", json={"habitat_id": hid, "prompt": "은신처를 왼쪽에"})
    assert r.json()["current"]["summary_ko"].startswith("[개발용 모의 해석기]")


# ── 인증 메일 언어 ──────────────────────────────────────────

EMAIL_ON = {"email_provider": "file", "email_from": "NestForge <no-reply@nestforge.test>",
            "app_base_url": "https://nestforge.test"}


def _signup(c: TestClient, username: str, email: str, headers: dict | None = None) -> None:
    c.cookies.clear()
    r = c.post("/auth/signup", json={"username": username, "nickname": f"{username}님", "password": PW, "email": email},
               headers=headers or {})
    assert r.status_code == 201, r.text
    assert r.json()["verification_email_sent"] is True


def test_verification_email_follows_request_language(tmp_path):
    mailer = MemoryMailer()
    with TestClient(create_app(settings(tmp_path, **EMAIL_ON), mailer=mailer)) as c:
        _signup(c, "kong_01", "kong@example.com")
        ko = mailer.sent[-1]
        assert ko.subject == "[NestForge] 이메일 주소를 인증해 주세요"
        assert re.search(r"https://nestforge\.test/verify-email\?token=", ko.text) and "환영해요" in ko.text

        _signup(c, "bori_02", "bori@example.com", headers={"X-Lang": "en"})
        en = mailer.sent[-1]
        assert en.to == "bori@example.com" and en.subject == "[NestForge] Verify your email address"
        m = re.search(r"https://nestforge\.test/en/verify-email\?token=([A-Za-z0-9_\-]+)", en.text)
        assert m and m.group(0) in en.html.replace("&amp;", "&")
        assert "welcome to NestForge" in en.text and "Verify email" in en.html
        assert not HANGUL.search(en.text.replace("bori_02님", "")) and not HANGUL.search(en.html.replace("bori_02님", ""))

        # 영어 링크의 토큰도 같은 API 로 인증된다
        c.cookies.clear()
        r = c.post("/auth/verify-email", json={"token": m.group(1)})
        assert r.status_code == 200 and r.json()["ok"] is True

        # 다시 보내기도 요청 언어 (쿠키)
        _signup(c, "dubu_03", "dubu@example.com")
        c.cookies.set("lang", "en")
        sent = len(mailer.sent)
        db = c.app.state.session_factory()
        for e in db.query(UsageEvent).all():  # 1분 간격을 지나가게 한다
            e.created_at = e.created_at - timedelta(seconds=120)
        db.commit()
        db.close()
        r = c.post("/auth/verify-email/resend")
        assert r.status_code == 200, r.text
        assert len(mailer.sent) == sent + 1 and "/en/verify-email?token=" in mailer.sent[-1].text


def test_english_catalog_covers_every_korean_string():
    """코드·규칙 파일에 새 한국어 문구를 넣으면 app/i18n/en/*.json 에도 영어를 넣어야 한다."""
    from app.i18n.extract import missing

    assert missing() == {}


def test_english_catalog_entries_keep_placeholders():
    import json
    import re
    from pathlib import Path

    ph = re.compile(r"\{\d+\}")
    hangul = re.compile(r"[가-힣]")
    for f in sorted((Path(__file__).parents[1] / "app" / "i18n" / "en").glob("*.json")):
        for ko, en in json.loads(f.read_text(encoding="utf-8")).items():
            assert sorted(ph.findall(ko)) == sorted(ph.findall(en)), (f.name, ko, en)
            assert not hangul.search(en) or "가-힣" in ko, (f.name, ko, en)
