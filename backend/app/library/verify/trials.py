"""시험 조립 (설계 §7.5): 검증하는 부품을 다른 부품과 이어 조립 해석기·자동 보정·규칙 검사가 통과하는지 본다.

초안은 registry.overlay({key: draft}) 안에서 돌린다 (run.verify 가 연다): compose.resolve(…, templates=…) 다음
ComposedTemplate(resolved, templates=…) 를 직접 만들고 (같은 key 의 다른 초안이 LRU composed_template 에서 섞이지 않게),
clamp_params(…, ASSEMBLY_MAX_PASSES) 와 rule_issues 를 부른다. derived_constraints 의 레지스트리 기본값(F6),
spec.connection_problems, 엔진도 overlay 가 덮는다.

연결 지점 자료가 그 결합을 허용하는 시험만 만든다 (슬라이드: compose.can_slide, 통로: 출입구이거나 open_port).
만든 시험은 모두 통과해야 한다 (T01): 해석 성공, 보정이 수렴, 충돌 없음, rule_issues == [].

| 역할 | 시험 |
|---|---|
| accessory | hideout 의 right·left·back·auto, 1층 house 의 right, sand_bath 의 back, 활성 라이브러리 host 의 연결판 면마다, hideout right 에 bowl_holder 와 나란히 |
| host | bowl_holder·bottle_stand·ramp 를 연결판 면마다 하나씩, 그다음 한 면에 ramp·다른 면에 bowl_holder |
| room_host | 출입구 면마다 tunnel 을 잇고 그 끝에 hideout, hideout·house 에서 나온 터널 끝에 부품(단면 맞추기), hideout → 부품 (터널을 끼워 넣음), 닫힌 연결판 면마다 bowl_holder, 출입구가 3개 이상이면 그물 (≤ 8 부품), 마릿수 2 시험 하나 |

역할 종류마다 통과한 시험 중 가장 큰 것 하나를 run_engine (넉넉한 케이지)으로 돌려 오류가 없어야 한다.
T02: rule_issues ≤ 10초 (부품 5개 이하) / 30초 (8개), 시험 하나 ≤ 30초.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.library.verify.report import CheckResult, failed, passed
from app.templates.base import Template

SIDES = ("front", "back", "left", "right")
ACCESSORY_PARENTS = (("hideout", ("right", "left", "back", "auto")), ("house", ("right",)), ("sand_bath", ("back",)))
HOST_CHILDREN = ("bowl_holder", "bottle_stand", "ramp")
RULE_ISSUES_BUDGET_S = {5: 10.0, 8: 30.0}
TRIAL_BUDGET_S = 30.0
PART_IDS = {"hideout": "hide", "house": "house", "sand_bath": "bath", "tunnel": "tube", "bowl_holder": "bowl",
            "bottle_stand": "bottle", "ramp": "ramp"}


@dataclass
class Trial:
    """시험 조립 하나: 부품 (id, key) 목록 (첫 부품이 기준), 연결 (part, to, at), 마릿수."""

    name: str
    parts: list[tuple[str, str]]
    connections: list[tuple[str, str, str]]
    count: int = 1
    kind: str = ""


@dataclass
class TrialResult:
    trial: Trial
    species: str
    size: str
    ok: bool
    message: str = ""
    joins: list[str] = field(default_factory=list)
    seconds: float = 0.0
    rule_seconds: float = 0.0
    request: Any = None
    params: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.trial.name, "size": self.size, "species": self.species, "ok": self.ok,
                             "joins": self.joins, "seconds": round(self.seconds, 1)}
        if self.trial.count != 1:
            d["count"] = self.trial.count
        if self.message:
            d["message"] = self.message
        return d


def part_id(t: Template) -> str:
    pf = getattr(t, "part_file", None)
    if pf is not None:
        return pf.part_id
    return PART_IDS.get(t.key, "part")


def _side_of(name: str, normal: tuple[float, float, float]) -> str:
    if name in SIDES:
        return name
    from app.modules.compose import nearest_side

    return nearest_side(np.asarray(normal, dtype=float))


def _mount_sides(t: Template, p: Any, child: Template | None = None) -> list[str]:
    """슬라이드 결합을 받는 옆면 (child 가 있으면 그 부품이 그 면에 붙을 수 있는지까지)."""
    from app.modules.compose import can_slide

    access = set(t.features(p).access_sides)
    out = []
    for name, a in t.anchors(p).items():
        if a.mount is None or abs(a.normal[2]) > 1e-6:
            continue
        if child is not None and not can_slide(a, child, access):
            continue
        side = _side_of(name, a.normal)
        if side not in out:
            out.append(side)
    return out


def _door_sides(t: Template, p: Any) -> list[str]:
    from app.modules.compose import is_door

    out = []
    for name, a in t.anchors(p).items():
        if is_door(a) and abs(a.normal[2]) < 1e-6:
            side = _side_of(name, a.normal)
            if side not in out:
                out.append(side)
    return out


class _Ids:
    """시험 안에서 겹치지 않는 부품 id (검증하는 부품의 id 는 미리 잡아 둔다: 코드 부품 hideout 을 검증할 때 'hide')."""

    def __init__(self, *taken: str) -> None:
        self.taken = set(taken) | {"tube"}

    def take(self, base: str) -> str:
        pid, k = base, 2
        while pid in self.taken:
            pid, k = f"{base}{k}", k + 1
        self.taken.add(pid)
        return pid

    def release(self, pid: str) -> None:
        self.taken.discard(pid)


def door_profiles(t: Template, p: Any) -> tuple[frozenset[str], bool]:
    """(출입구 단면 종류, 맞출 수 있는지). 맞출 수 있는 방은 face_fields 에 단면 파라미터가 있다 (갈림길)."""
    from app.modules.compose import is_door, literal_choices

    profiles: set[str] = set()
    adaptable = False
    for name, a in t.anchors(p).items():
        if not is_door(a) or a.profile is None:
            continue
        ff = t.face_fields(p, name).profile
        if ff is not None:
            adaptable = True
            profiles |= {str(c) for c in literal_choices(t.Params, ff)}
        else:
            profiles.add(a.profile)
    return frozenset(profiles), adaptable


def _compatible(a: Template, pa: Any, b: Template, ctx: Any) -> bool:
    """두 방을 터널 하나로 이을 수 있는 단면인지 (어느 한쪽이 맞출 수 있으면 공통 단면이 있으면 된다)."""
    sa, ada = door_profiles(a, pa)
    sb, adb = door_profiles(b, b.default_params(ctx))
    if ada or adb:
        return bool(sa & sb)
    return sa == sb and len(sa) == 1


def generate(key: str, t: Template, templates: dict[str, Template], ctx: Any, quick: bool = False) -> list[Trial]:
    """부품 역할에 맞는 시험 목록 (연결 지점 자료가 허용하는 것만). quick: 역할 종류마다 하나."""
    p = t.default_params(ctx)
    me = part_id(t)
    out: list[Trial] = []
    if t.role == "accessory":
        for parent, ats in ACCESSORY_PARENTS:
            pt = templates.get(parent)
            if pt is None:
                continue
            pp = pt.default_params(ctx)
            ok = set(_mount_sides(pt, pp, t))
            pid = PART_IDS[parent]
            for at in ats:
                if at == "auto" or at in ok:
                    out.append(Trial(f"{me}@{parent}.{at}", [(pid, parent), (me, key)], [(me, pid, at)], kind="slide"))
        for hk, ht in templates.items():
            if ht.role != "host" or getattr(ht, "part_file", None) is None or getattr(ht, "retired", False) or hk == key:
                continue
            for side in _mount_sides(ht, ht.default_params(ctx), t):
                hid = part_id(ht)
                out.append(Trial(f"{me}@{hk}.{side}", [(hid, hk), (me, key)], [(me, hid, side)], kind="slide"))
        hide = templates.get("hideout")
        bowl = templates.get("bowl_holder")
        if hide is not None and bowl is not None and key != "bowl_holder" \
                and "right" in _mount_sides(hide, hide.default_params(ctx), t):
            out.append(Trial(f"{me}+bowl@hideout.right", [("hide", "hideout"), (me, key), ("bowl", "bowl_holder")],
                             [(me, "hide", "right"), ("bowl", "hide", "right")], kind="slide"))
    elif t.role == "host":
        for ck in HOST_CHILDREN:
            ct = templates.get(ck)
            if ct is None:
                continue
            for side in _mount_sides(t, p, ct):
                cid = PART_IDS[ck]
                out.append(Trial(f"{ck}@{me}.{side}", [(me, key), (cid, ck)], [(cid, me, side)], kind="slide"))
        ramp, bowl = templates.get("ramp"), templates.get("bowl_holder")
        if ramp is not None and bowl is not None:
            rs, bs = _mount_sides(t, p, ramp), _mount_sides(t, p, bowl)
            pair = next(((r, b) for r in rs for b in bs if r != b), None)
            if pair:
                out.append(Trial(f"ramp@{me}.{pair[0]}+bowl@{me}.{pair[1]}", [(me, key), ("ramp", "ramp"),
                                                                             ("bowl", "bowl_holder")],
                                 [("ramp", me, pair[0]), ("bowl", me, pair[1])], kind="slide"))
    elif t.role == "room_host":
        doors = _door_sides(t, p)
        # 터널 반대쪽 방: 단면이 맞는 방만 (모양이 고정된 방끼리 단면이 다르면 해석기가 F4 로 막는다: port_adapter 몫)
        rooms = [r for r in ("hideout", "house") if r in templates and _compatible(t, p, templates[r], ctx)]
        far = rooms[0] if rooms else (key if _compatible(t, p, t, ctx) else None)
        ids = _Ids(me)
        if far is not None:
            for side in doors:
                fid = ids.take(PART_IDS.get(far, "room"))
                out.append(Trial(f"tunnel@{me}.{side}→{far}", [(me, key), ("tube", "tunnel"), (fid, far)],
                                 [("tube", me, side), (fid, "tube", "free_end")], kind="passage"))
                ids.release(fid)
        for room in rooms:
            if room == key:
                continue
            rid = ids.take(PART_IDS[room])
            out.append(Trial(f"{room}→tunnel→{me}", [(rid, room), ("tube", "tunnel"), (me, key)],
                             [("tube", rid, "front"), (me, "tube", "free_end")], kind="passage"))
            ids.release(rid)
        if rooms and rooms[0] != key:
            rid = ids.take(PART_IDS[rooms[0]])
            out.append(Trial(f"{rooms[0]}→{me} (tunnel inserted)", [(rid, rooms[0]), (me, key)],
                             [(me, rid, "front")], kind="passage"))
            ids.release(rid)
        bowl = templates.get("bowl_holder")
        if bowl is not None:
            for side in _mount_sides(t, p, bowl):
                out.append(Trial(f"bowl@{me}.{side}", [(me, key), ("bowl", "bowl_holder")], [("bowl", me, side)],
                                 kind="slide"))
        if len(doors) >= 3 and far is not None:
            first = ids.take(PART_IDS.get(far, "room"))
            parts = [(first, far), ("tube", "tunnel"), (me, key)]
            conns = [("tube", first, "front"), (me, "tube", "free_end")]
            # 터널 끝에 이은 출입구는 해석기가 첫 빈 출입구로 고른다: 그 밖의 출입구마다 터널 + 방
            for side in doors[1:]:
                if len(parts) + 2 > 8:
                    break
                tid, rid = ids.take("tube"), ids.take(PART_IDS.get(far, "room"))
                parts += [(tid, "tunnel"), (rid, far)]
                conns += [(tid, me, side), (rid, tid, "free_end")]
            out.append(Trial(f"network {far}→{me}→{len(doors) - 1} rooms", parts, conns, kind="network"))
        if doors and out and out[0].kind == "passage":
            first_trial = out[0]
            out.append(Trial(first_trial.name + " (count 2)", list(first_trial.parts), list(first_trial.connections),
                             count=2, kind="passage"))
    if quick and out:
        out = [out[0]]
    return out


def run_trial(trial: Trial, templates: dict[str, Template], rules: Any, species: str, size: str) -> TrialResult:
    from app.library.verify.variants import fit_ctx, rule_ctx
    from app.modules.compose import ASSEMBLY_MAX_PASSES, assembly_params, resolve
    from app.modules.composed import ComposedTemplate
    from app.modules.structure import AssemblyRequest
    from app.validation.autofix import clamp_params
    from app.validation.report import Issue

    t0 = time.perf_counter()
    fctx = fit_ctx(rules, species, size, trial.count)
    rctx = rule_ctx(rules, species, size, trial.count)
    res = TrialResult(trial, species, size, False)
    try:
        params = {pid: templates[k].default_params(fctx).model_dump(mode="json") for pid, k in trial.parts}
        req = AssemblyRequest.model_validate({
            "parts": [{"id": pid, "template": k, "params": params[pid]} for pid, k in trial.parts],
            "connections": [{"part": a, "to": b, "at": at} for a, b, at in trial.connections],
        })
        res.request, res.params = req, params
        out = resolve(req, None, fctx, templates=templates)
        if isinstance(out, Issue):
            res.message = f"resolve: {out.code} {out.message_ko}"
            return res
        resolved, part_params, _ = out
        res.joins = [f"{j.parent}>{j.child} {j.mount}" for j in resolved.joins]
        tmpl = ComposedTemplate(resolved, templates=templates)
        p = assembly_params(tmpl, part_params)
        p1, issues = clamp_params(tmpl, p, fctx, max_passes=ASSEMBLY_MAX_PASSES)
        conflict = [i for i in issues if i.code == "param_conflict"]
        if conflict:
            res.message = f"clamp: {conflict[0].message_ko}"
            return res
        p2, _ = clamp_params(tmpl, p1, fctx, max_passes=ASSEMBLY_MAX_PASSES)
        if p2 != p1:
            res.message = "clamp does not converge (a second clamp changes the values)"
            return res
        r0 = time.perf_counter()
        problems = tmpl.rule_issues(p1, rctx)
        res.rule_seconds = time.perf_counter() - r0
        res.params = {pid: v for pid, v in p1.model_dump(mode="json").items()}
        if problems:
            res.message = f"rule_issues: {problems[0]}"
            return res
        res.ok = True
        return res
    except Exception as e:  # noqa: BLE001 - 해석기·형상 예외도 시험 실패로 적는다
        res.message = f"{type(e).__name__}: {e}"
        return res
    finally:
        res.seconds = time.perf_counter() - t0


def trial_checks(results: list[TrialResult]) -> list[CheckResult]:
    out: list[CheckResult] = []
    for r in results:
        vid = f"{r.species}/{r.size}/trial:{r.trial.name}"
        out.append(passed("T01", vid) if r.ok else
                   failed("T01", vid, r.message, hint="the join must resolve, clamp without conflict and pass "
                                                      "rule_issues; check anchors, mounts and face fields"))
        n = len(r.joins) + 1 if r.joins else len(r.trial.parts)  # 해석기가 끼워 넣은 터널까지 센다
        budget = RULE_ISSUES_BUDGET_S[5] if n <= 5 else RULE_ISSUES_BUDGET_S[8]
        if r.rule_seconds > budget:
            out.append(failed("T02", vid, f"rule_issues took {r.rule_seconds:.1f} s", value=r.rule_seconds,
                              limit=budget))
        elif r.seconds > TRIAL_BUDGET_S:
            out.append(failed("T02", vid, f"the trial took {r.seconds:.1f} s", value=r.seconds, limit=TRIAL_BUDGET_S))
        else:
            out.append(passed("T02", vid, value=r.seconds, limit=TRIAL_BUDGET_S))
    return out


def engine_check(results: list[TrialResult], key: str, rules: Any) -> list[CheckResult]:
    """역할 종류(시험 kind)마다 통과한 가장 큰 시험 하나를 run_engine 으로 (오류 없음)."""
    from app.library.verify.variants import engine_context
    from app.services.engine import ItemSpec, run_engine
    from app.validation.report import Severity

    out: list[CheckResult] = []
    best: dict[str, TrialResult] = {}
    for r in results:
        if not r.ok:
            continue
        cur = best.get(r.trial.kind)
        if cur is None or len(r.trial.parts) > len(cur.trial.parts):
            best[r.trial.kind] = r
    for kind, r in sorted(best.items()):
        vid = f"{r.species}/{r.size}/trial:{r.trial.name}/engine"
        ctx = engine_context(rules, r.species, r.size, r.trial.count, (key,))
        try:
            spec = ItemSpec("assembly", {pid: p for pid, p in r.params.items()}, assembly=r.request)
            rep = run_engine([spec], ctx).report
        except Exception as e:  # noqa: BLE001
            out.append(failed("T01", vid, f"run_engine raised {type(e).__name__}: {e}"))
            continue
        errors = [i for i in rep.issues if i.severity == Severity.error]
        out.append(passed("T01", vid) if not errors else
                   failed("T01", vid, f"engine error {errors[0].code}: {errors[0].message_ko}"))
    return out
