"""나중에 더한 기준(터널 최대 길이)과 그 전에 저장된 설계.

옛 규칙(최대 길이 없음)은 드워프 tunnel_max_length_mm 를 템플릿 상한 600 으로 둔 규칙 복사본으로 흉내 낸다.
이때 기본 길이는 min(200, 600) = 200, 최소 길이는 1.5×내경 그대로라 옛 코드와 같게 동작한다.

확인하는 것:
  - 옛 설계는 지금 규칙으로 열어도 보기·내려받기가 막히지 않고, 화면에 rule_changed 경고만 덧붙는다.
  - 형상 해시가 없는 옛 버전이 캐시 없이 다시 검증되어도(서버 재시작) 409 로 막히지 않는다.
  - 수정하면 새 기준(100mm)으로 맞춰진다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR
from app.main import create_app
from app.models import DesignVersion
from tests.api_helpers import create_habitat, member_settings, signup, use

DWARF_CAGE = {"width_mm": 900, "depth_mm": 500, "height_mm": 300}


def _rules_copy(tmp_path: Path, dwarf_max: float) -> Path:
    dst = tmp_path / "old_rules"
    shutil.copytree(BACKEND_DIR / "rules", dst)
    p = dst / "species.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["species"]["hamster"]["sizes"]["dwarf"]["tunnel_max_length_mm"] = dwarf_max
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return dst


def _client(tmp_path: Path, rules_dir: Path) -> TestClient:
    return TestClient(create_app(member_settings(tmp_path, rules_dir=rules_dir)))


def _old_design(tmp_path: Path) -> tuple[str, dict]:
    """옛 규칙 서버에서 드워프 설계(은신처 + 200mm 터널)를 만든다."""
    with _client(tmp_path, _rules_copy(tmp_path, 600)) as c:
        tok = signup(c, "olduser", "올드")
        hid = create_habitat(c, DWARF_CAGE, size="dwarf")
        r = c.post("/designs", json={"habitat_id": hid, "prompt": "은신처와 터널을 넣어 주세요"})
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["current"]["validation"]["passed"]
        tunnel = next(it for it in d["current"]["items"] if it["template"] == "tunnel")
        assert tunnel["params"]["length_mm"] == 200
        assert c.get(f"/designs/{d['id']}/export?format=stl").status_code == 200
    return tok, d


def _rule_changed(design_json: dict) -> list[dict]:
    return [i for i in design_json["current"]["validation"]["issues"] if i["code"] == "rule_changed"]


def test_old_design_viewable_with_warning(tmp_path):
    tok, d = _old_design(tmp_path)
    with _client(tmp_path, BACKEND_DIR / "rules") as c:
        use(c, tok)
        g = c.get(f"/designs/{d['id']}")
        assert g.status_code == 200
        cur = g.json()["current"]
        assert cur["validation"]["passed"] and cur["export_allowed"]
        notes = _rule_changed(g.json())
        assert len(notes) == 1 and notes[0]["severity"] == "warning"
        assert notes[0]["details"]["field"] == "length_mm" and notes[0]["details"]["max"] == 100
        assert "막지는 않" in notes[0]["message_ko"]
        assert cur["validation"]["summary"]["warnings"] >= 1 and cur["validation"]["summary"]["errors"] == 0
        assert c.get(f"/designs/{d['id']}/export?format=stl").status_code == 200
        assert c.get(f"/designs/{d['id']}/export?format=3mf").status_code == 200


def test_legacy_version_cold_cache_not_blocked(tmp_path):
    """형상 해시가 없는 옛 버전 + 빈 메시 캐시 → 다시 검증하지만, 나중에 더한 기준은 막지 않는다."""
    tok, d = _old_design(tmp_path)
    shutil.rmtree(tmp_path / "meshes", ignore_errors=True)
    with _client(tmp_path, BACKEND_DIR / "rules") as c:
        with c.app.state.session_factory() as db:
            for v in db.query(DesignVersion).all():
                v.geometry = None
            db.commit()
        use(c, tok)
        for it in d["current"]["items"]:
            assert c.get(it["mesh_url"].split("?")[0]).status_code == 200
        assert c.get(f"/designs/{d['id']}/export?format=stl").status_code == 200
        use(c, None)  # 공유되지 않은 설계는 남이 볼 수 없다 → 404 (409 가 아님)
        assert c.get(f"/designs/{d['id']}/export?format=stl").status_code in (403, 404)


def test_revise_applies_new_limit(tmp_path):
    tok, d = _old_design(tmp_path)
    with _client(tmp_path, BACKEND_DIR / "rules") as c:
        use(c, tok)
        r = c.post(f"/designs/{d['id']}/revise", json={"prompt": "은신처를 조금 더 크게", "base_version": 1})
        assert r.status_code == 201, r.text
        new = r.json()
        tunnel = next(it for it in new["current"]["items"] if it["template"] == "tunnel")
        assert tunnel["params"]["length_mm"] <= 100
        assert new["current"]["validation"]["passed"]
        assert not _rule_changed(new)
        # 옛 버전은 그대로 남고, 여전히 경고와 함께 볼 수 있다
        old = c.get(f"/designs/{d['id']}?version=1").json()
        assert old["current"]["version"] == 1 and _rule_changed(old)
