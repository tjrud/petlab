"""코드 부품의 계약 검사 (설계 §7.6): DSL 부품과 같은 검증기(app/library/verify)를 코드 부품에 돌린다.

조립 역할이 있는 모든 코드 부품(그리고 G 검사를 위해 물속 동굴)에 quick 프로필의 C01–C08, G02, G04–G08, G11, G12 를
돌린다. 통과하지 못하는 검사는 CODE_PART_WAIVERS 에 까닭을 적어 면제한다 (DSL 부품에는 면제가 없다, R6).
면제는 실제로 실패하는 검사에만 둔다 (쓰이지 않는 면제가 남으면 실패한다: 고친 부품은 면제를 지운다).

전체 프로필(min·max·무작위 변형, 모든 검사)은 `uv run pytest -m contract_full tests/test_part_contract.py` 로 돌린다
(기본 실행에서는 빠진다).
"""

from __future__ import annotations

import pytest

from app.library.verify import run as R
from app.library.verify.report import format_text
from app.templates.registry import code_keys, get_template

# key → {검사 id: 면제 까닭}. 까닭은 비울 수 없다 (apply_waivers 가 막는다)
CODE_PART_WAIVERS: dict[str, dict[str, str]] = {
    "house": {
        "C08": "no analytic envelope: the house falls back to the bbox of build (cached per params); "
               "the resolver only sizes faces from anchors, which are analytic",
        "G04": "a two-floor syrian house (229 mm wide) exceeds the 220 mm bed; the runtime warns with "
               "exceeds_build_volume and the user sizes the house",
        "G08": "two-floor internal ramp: the open space between the low end of the ramp and the side wall reads as a "
               "30–45 mm slot to horizontal rays, but it is open above (the animal stands on the ramp)",
    },
    "tunnel": {
        "G08": "tube shape: the round underside beside the narrow foot forms a tapering wedge with the cage floor; "
               "kept for stored designs (the DSL rejects tube doors, S04)",
    },
    "bottle_stand": {
        "G08": "the holder ring is sized to the bottle: in use the bottle fills the 42–62 mm ring gap",
    },
}

CONTRACT_KEYS = [k for k in code_keys() if get_template(k).role != "none" or k == "cave"]


def _checks(key: str) -> tuple[str, ...]:
    """역할 none(물속 동굴)은 연결 검사 대신 형상 검사만."""
    if get_template(key).role == "none":
        return tuple(c for c in R.CONTRACT_CHECKS if c.startswith("G"))
    return R.CONTRACT_CHECKS


def test_waivers_have_reasons_and_known_checks():
    for key, ws in CODE_PART_WAIVERS.items():
        assert key in code_keys(), key
        for cid, why in ws.items():
            assert cid in R.ALL_CHECKS, (key, cid)
            assert len(why.strip()) >= 20, (key, cid)


def test_every_composable_code_part_is_covered():
    assert set(CONTRACT_KEYS) == set(code_keys())


@pytest.mark.parametrize("key", CONTRACT_KEYS)
def test_code_part_contract(rules, key):
    t = get_template(key)
    run = R.verify(t, rules=rules, profile="quick", jobs=1, checks=_checks(key),
                   waivers=CODE_PART_WAIVERS.get(key), trials=False)
    assert run.ok, format_text(run)
    # 면제는 실제로 실패한 검사에만: 쓰이지 않은 면제는 지운다
    used = {r.id for r in run.results if r.waived}
    unused = set(CODE_PART_WAIVERS.get(key, {})) - used
    assert not unused, f"{key}: waivers no longer needed: {sorted(unused)}"


@pytest.mark.contract_full
@pytest.mark.parametrize("key", CONTRACT_KEYS)
def test_code_part_contract_full(rules, key):
    t = get_template(key)
    run = R.verify(t, rules=rules, profile="full", checks=_checks(key), waivers=CODE_PART_WAIVERS.get(key),
                   trials=False)
    assert run.ok, format_text(run)
