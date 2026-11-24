"""DSL 부품의 정적 검사 S01–S08 과 L01–L12 묶음, 그리고 정적 검사 + 검증기(§7.2)를 잇는 verify_draft (설계 §7.2, §8).

`python -m app.library check` 가 쓰는 static_checks 는 형상 커널 없이 1초 안에 끝난다: 스키마(schema)·식(expr)·
정적 검사(lint)·색인(index)만 쓰고 build123d·OCP·trimesh·numpy 를 불러오지 않는다 (tests/test_library_cli.py 가 확인).
verify_draft 는 정적 검사가 깨끗할 때만 템플릿을 만들어 run.verify(P·G·C·T·R 검사)를 돌린다 (무거움, 늦게 불러온다).

| id  | 검사 |
|-----|------|
| S01 | 스키마 (§5.2), 엄격 |
| S02 | 모든 식이 컴파일된다: 이름이 그 자리 범위에 있고, 형이 맞고, 선택 문자열이 선택지에 있다 (lint L01 을 여기로 모은다) |
| S03 | 참조: 제약 필드, height_field, size_fields, level_field, door_fields, fields.*, opens.set 의 열쇠, attach_order, 구멍 단계 |
| S04 | 역할 규칙 (§5.6, 연결 지점 종류는 L07), 출입구 모양 ⊆ {round_arch, pointed_arch, box, house}, 출입구 폭 필드 범위 ⊆ [12, 130], 출입구 벽 필드 최솟값 ≥ 2.3, envelope |
| S05 | 이름: family 가 코드 부품 key·assembly 가 아니다, part_id 가 다른 활성 부품·모의 해석기의 부품 id 와 겹치지 않는다 |
| S06 | 문구: ko 마다 한글 없는 en, 까닭·메시지의 {0}·{1} 이 ko·en 에서 같다, 파라미터 설명 첫 문장(_desc)이 ko·en 짝을 이룬다 |
| S07 | 한도: 파일 ≤ 64 KB, 파라미터 ≤ 12, 단계 ≤ 48, 반복을 펼친 고체 ≤ 512 (정수 필드 최댓값에서), 연결 지점 ≤ 12 |
| S08 | wall_thickness_mm 이 있고 숫자이며 최솟값 ≥ 1.0, 최댓값 ≤ 8 |

메시지와 고치는 방법(hint)은 다른 DSL 오류처럼 영어다 (개발자 에이전트가 읽는다).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.library import index
from app.library.errors import DslError, DslErrors, pointer
from app.library.verify.report import CheckResult, failed, passed

STATIC_CHECKS: tuple[str, ...] = ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08")
LINT_CHECKS: tuple[str, ...] = tuple(f"L{n:02d}" for n in range(2, 13))  # L01 은 S02 로 모은다

FILE_MAX_BYTES = 64 * 1024
PARAMS_MAX = 12
STEPS_MAX = 48
SOLIDS_MAX = 512
ANCHORS_MAX = 12
DOOR_PROFILES = frozenset({"round_arch", "pointed_arch", "box", "house"})
DOOR_WIDTH_RANGE = (12.0, 130.0)  # 터널 안지름 범위 (tunnel.inner_diameter_mm)
PLUG_DOOR_WALL_MIN_MM = 2.3  # app.modules.compose.PLUG_DOOR_WALL_MIN_MM (커널을 불러오지 않으려고 값을 둔다; 시험이 같은지 확인)
WALL_MIN_RANGE = (1.0, 8.0)
RESERVED_FAMILIES = frozenset({"assembly"})

# 한글 자모·음절 (영어 카탈로그 추출기가 한글 상수로 보지 않게 chr 로 만든다)
_HANGUL = re.compile("[" + chr(0x3131) + "-" + chr(0x318E) + chr(0xAC00) + "-" + chr(0xD7A3) + "]")
_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_RULE_IN_GEOMETRY = re.compile(r"^(rule|ctx)\.")


# ── 도움 ──

def _fail(cid: str, path: str, message: str, hint: str = "", **kw: Any) -> CheckResult:
    return failed(cid, kw.pop("variant", None), message, path=path, hint=hint, **kw)


def _from_error(cid: str, e: DslError) -> CheckResult:
    where = f" (col {e.col})" if e.col is not None else ""
    return _fail(cid, e.path, f"{e.code}{where}: {e.message}", e.hint)


def _errors(err: DslError) -> list[DslError]:
    return list(err.errors) if isinstance(err, DslErrors) and err.errors else [err]


def code_template_keys() -> tuple[str, ...]:
    from app.templates.keys import TEMPLATE_MODULES  # 가벼운 모듈 (키 목록)

    return tuple(TEMPLATE_MODULES)


def mock_part_ids() -> frozenset[str]:
    """모의 해석기(app/llm/mock.py)의 PART_IDS 값. 모듈은 레지스트리(형상 커널)를 불러오므로 import 하지 않고
    소스의 dict 상수만 읽는다."""
    spec = importlib.util.find_spec("app.llm.mock")
    if spec is None or spec.origin is None:
        return frozenset()
    try:
        tree = ast.parse(open(spec.origin, encoding="utf-8").read())  # noqa: SIM115 - 짧게 읽고 닫는다
    except (OSError, SyntaxError):
        return frozenset()
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(
            node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == "PART_IDS" for t in targets) and node.value is not None:
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return frozenset()
            if isinstance(value, dict):
                return frozenset(str(v) for v in value.values())
    return frozenset()


def _alias(part: Any, src: object) -> str | None:
    """식이 파라미터 하나(또는 그 파라미터만 가리키는 let)면 그 파라미터 이름."""
    lets = {x.name: x.expr for x in part.let}
    name = src
    for _ in range(len(lets) + 1):
        if not isinstance(name, str):
            return None
        name = name.strip()
        if name in part.params:
            return name
        if name in lets:
            name = lets[name]
            continue
        return None
    return None


def _expr_params(part: Any, compiled: Any, ptr: str) -> set[str]:
    """식 하나가 (let 을 거쳐) 읽는 파라미터 이름."""
    e = compiled.get(ptr) if compiled is not None else None
    if e is None:
        return set()
    lets = {name: le for name, le in compiled.lets}
    out: set[str] = set()
    todo = list(e.names)
    seen: set[str] = set()
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        if n in part.params:
            out.add(n)
        elif n in lets:
            todo.extend(lets[n].names)
    return out


# ── S03 참조 ──

def _s03(part: Any, compiled: Any) -> list[CheckResult]:
    out: list[CheckResult] = []
    kinds = {k: v.type for k, v in part.params.items()}

    def need(ptr: str, name: str | None, want: str, what: str) -> None:
        if name is None:
            return
        if name not in kinds:
            out.append(_fail("S03", ptr, f"{what} {name!r} is not a param", "params: " + ", ".join(kinds)))
        elif want == "number" and kinds[name] not in ("number", "integer"):
            out.append(_fail("S03", ptr, f"{what} {name!r} must be a number param, not {kinds[name]}"))
        elif want == "choice" and kinds[name] != "choice":
            out.append(_fail("S03", ptr, f"{what} {name!r} must be a choice param, not {kinds[name]}"))

    for i, c in enumerate(part.constraints):
        need(f"/constraints/{i}/field", c.field, "number", "constraint field")
    need("/height_field", part.height_field, "number", "height_field")
    need("/level_field", part.level_field, "number", "level_field")
    for i, f in enumerate(part.size_fields):
        need(f"/size_fields/{i}", f, "number", "size field")
    for i, f in enumerate(part.door_fields):
        need(f"/door_fields/{i}", f, "any", "door field")
    if part.door_fields and part.role != "room_host":
        out.append(_fail("S03", "/door_fields", "door_fields is only for room_host parts"))

    # 크기 맞춤 필드는 출입구 폭이 아니고, 출입구 높이로 아래를 막은 높이가 아니다
    door_widths: set[str] = set()
    for name, a in part.anchors.items():
        if a.door is not None:
            w = _alias(part, a.door.width) or (a.fields.port if a.fields else None)
            if w:
                door_widths.add(w)
        if a.fields is not None:
            base = pointer("anchors", name, "fields")
            for slot in ("width", "height", "wall", "port"):
                need(f"{base}/{slot}", getattr(a.fields, slot), "number", f"fields.{slot}")
            need(f"{base}/profile", a.fields.profile, "choice", "fields.profile")
    door_heights = {c.field for c in part.constraints if c.min is not None and "port_height(" in str(c.min)}
    for i, f in enumerate(part.size_fields):
        if f in door_widths:
            out.append(_fail("S03", f"/size_fields/{i}", f"size field {f!r} is a door width; shrink-to-fit must not "
                                                         "change door widths", "remove it from size_fields"))
        elif f in door_heights:
            out.append(_fail("S03", f"/size_fields/{i}", f"size field {f!r} has a lower bound from the door height; "
                                                         "shrinking it fights that bound",
                             "remove it from size_fields"))

    # 문 구조 필드: 어느 문이 있는지·모양을 바꾸는 파라미터는 모두 door_fields 에 (조립이 고정한다)
    if part.role == "room_host" and compiled is not None:
        need_fields: dict[str, str] = {}
        for name, a in part.anchors.items():
            if a.door is None:
                continue
            for slot in ("when", "profile"):
                ptr = pointer("anchors", name, "door", slot)
                for prm in sorted(_expr_params(part, compiled, ptr)):
                    need_fields.setdefault(prm, ptr)
        for prm, ptr in need_fields.items():
            if prm not in part.door_fields:
                out.append(_fail("S03", "/door_fields", f"param {prm!r} changes which doors exist or their shape "
                                                        f"({ptr}) but is not in door_fields",
                                 f"add {prm!r} to door_fields so compositions pin it"))

    # opens: 연결 지점과 set 의 열쇠
    for i, o in enumerate(part.opens):
        base = f"/opens/{i}"
        a = part.anchors.get(o.anchor)
        if a is None:
            out.append(_fail("S03", f"{base}/anchor", f"unknown anchor {o.anchor!r}",
                             "anchors: " + ", ".join(sorted(part.anchors))))
        elif a.door is None:
            out.append(_fail("S03", f"{base}/anchor", f"anchor {o.anchor!r} has no door to open"))
        for k in o.set:
            if k not in kinds:
                out.append(_fail("S03", f"{base}/set/{pointer(k)[1:]}", f"opens.set key {k!r} is not a param"))

    # attach_order 의 이름
    names = set(part.anchors) | {"bottom"}
    for kind in ("slide", "passage"):
        for i, n in enumerate(getattr(part.attach_order, kind) or ()):
            if n not in names:
                out.append(_fail("S03", f"/attach_order/{kind}/{i}", f"unknown anchor {n!r}",
                                 "anchors: " + ", ".join(sorted(names))))

    # 구멍(환기구·창)이 가리키는 단계: 있는 id, 자르는 상자·원기둥·통로
    step_ids = {s.id: (i, s) for i, s in enumerate(part.body) if s.id is not None}
    for i, o in enumerate(part.features.openings or ()):
        if getattr(o, "kind", None) not in ("vent", "window"):
            continue
        ptr = f"/features/openings/{i}"
        hit = step_ids.get(o.step)
        if hit is None:
            out.append(_fail("S03", f"{ptr}/step", f"unknown step id {o.step!r}",
                             "give the cut step an id and use it here"))
            continue
        _, step = hit
        if step.mode != "cut" or step.op == "prism":
            out.append(_fail("S03", f"{ptr}/step", f"step {o.step!r} must be a box, cylinder or passage cut"))
        elif step.op == "box" and o.axis is None:
            out.append(_fail("S03", f"{ptr}/axis", "a box vent needs its axis (the direction of the hole)"))
    return out


# ── S04 역할·출입구 ──

def _s04(part: Any, compiled: Any) -> list[CheckResult]:
    out: list[CheckResult] = []
    if part.role != "none" and part.envelope is None:
        out.append(_fail("S04", "/envelope", "envelope is required unless role is 'none'",
                         "write the analytic outer size [x, y, z] in the use pose"))
    if part.role == "room_host" and not any(a.door is not None for a in part.anchors.values()):
        out.append(_fail("S04", "/anchors", "a room_host needs at least one door anchor"))
    if part.role in ("host", "accessory", "none"):
        for name, a in part.anchors.items():
            if a.door is not None:
                out.append(_fail("S04", pointer("anchors", name, "door"), f"a {part.role} part has no doors"))
    for name, a in part.anchors.items():
        base = pointer("anchors", name)
        if a.openable and not any(o.anchor == name for o in part.opens):
            out.append(_fail("S04", f"{base}/openable", f"openable anchor {name!r} has no opens entry"))
        if a.door is None:
            continue
        # 출입구 모양: 선택 파라미터의 선택지 또는 문자열 상수
        ptr = f"{base}/door/profile"
        e = compiled.get(ptr) if compiled is not None else None
        shapes = set(e.type.values) if e is not None and e.type.kind == "choice" else set()
        bad = sorted(shapes - DOOR_PROFILES)
        if bad:
            out.append(_fail("S04", ptr, f"door profile can be {', '.join(bad)}; v1 doors are "
                                         f"{', '.join(sorted(DOOR_PROFILES))}",
                             "'tube' is a raised circle and cannot be a door; remove it from the choices"))
        # 출입구 폭: 필드 범위가 터널 안지름 범위 안
        w = (a.fields.port if a.fields and a.fields.port else None) or _alias(part, a.door.width)
        spec = part.params.get(w) if w else None
        if spec is not None and spec.type in ("number", "integer"):
            lo, hi = DOOR_WIDTH_RANGE
            if float(spec.min) < lo or float(spec.max) > hi:
                out.append(_fail("S04", pointer("params", w), f"door width {w!r} bounds [{spec.min:g}, {spec.max:g}] "
                                                              f"must lie inside the tunnel range [{lo:g}, {hi:g}]",
                                 "narrow min/max so a joined tunnel can always take the same width"))
        # 출입구 벽: 끼워 잇기 최소 두께
        wf = (a.fields.wall if a.fields and a.fields.wall else None) or _alias(part, a.wall)
        wspec = part.params.get(wf) if wf else None
        if wspec is None:
            out.append(_fail("S04", f"{base}/wall", f"door anchor {name!r} needs a wall param (fields.wall)",
                             "write \"wall\": \"wall_thickness_mm\" or a let that is that param"))
        elif wspec.type in ("number", "integer") and float(wspec.min) < PLUG_DOOR_WALL_MIN_MM - 1e-9:
            out.append(_fail("S04", pointer("params", wf, "min"), f"door wall {wf!r} min {wspec.min:g} is below "
                                                                   f"{PLUG_DOOR_WALL_MIN_MM:g} mm",
                             f"tunnels plug into doors; raise the min to {PLUG_DOOR_WALL_MIN_MM:g}",
                             value=float(wspec.min), limit=PLUG_DOOR_WALL_MIN_MM))
    return out


# ── S05 이름 ──

def _s05(part: Any) -> list[CheckResult]:
    out: list[CheckResult] = []
    if part.family in code_template_keys() or part.family in RESERVED_FAMILIES:
        out.append(_fail("S05", "/family", f"family {part.family!r} is a code part key or reserved",
                         "choose a new family name"))
    taken: dict[str, str] = {}
    try:
        for key, e in index.entries().items():
            if e.status == "active" and e.family != part.family:
                taken[index.read_part(key)["part_id"]] = key
    except index.LibraryError as err:
        out.append(_fail("S05", "/part_id", f"cannot read the library index: {err}"))
    owner = taken.get(part.part_id)
    if owner is not None:
        out.append(_fail("S05", "/part_id", f"part_id {part.part_id!r} is used by {owner}",
                         "choose a short id no other active part uses"))
    elif part.part_id in mock_part_ids():
        out.append(_fail("S05", "/part_id", f"part_id {part.part_id!r} is used by a code part in the mock",
                         "choose a short id no code part uses"))
    return out


# ── S06 문구 ──

def _texts(part: Mapping[str, Any]) -> Iterable[tuple[str, dict, bool]]:
    """(경로, {ko, en}, 자리표시 확인 여부)."""
    def text(ptr: str, t: object, ph: bool = False):
        if isinstance(t, dict):
            yield ptr, t, ph

    yield from text("/name", part.get("name"))
    yield from text("/description", part.get("description"))
    for name, spec in (part.get("params") or {}).items():
        yield from text(f"/params/{name}/desc", spec.get("desc"))
        for v, label in (spec.get("choice_labels") or {}).items():
            yield from text(f"/params/{name}/choice_labels/{v}", label)
    for i, c in enumerate(part.get("constraints") or []):
        yield from text(f"/constraints/{i}/reason", c.get("reason"), True)
    for i, c in enumerate(part.get("checks") or []):
        yield from text(f"/checks/{i}/message", c.get("message"), True)
    for i, pp in enumerate(part.get("print") or []):
        yield from text(f"/print/{i}/name", pp.get("name"))
    for i, o in enumerate((part.get("features") or {}).get("openings") or []):
        yield from text(f"/features/openings/{i}/label", o.get("label"))


def _s06(data: Mapping[str, Any]) -> list[CheckResult]:
    out: list[CheckResult] = []
    for ptr, t, ph in _texts(data):
        ko, en = str(t.get("ko") or ""), str(t.get("en") or "")
        if not ko.strip():
            out.append(_fail("S06", f"{ptr}/ko", "the Korean text is empty"))
        if not en.strip():
            out.append(_fail("S06", f"{ptr}/en", "the English text is empty", "write the English translation"))
        elif _HANGUL.search(en):
            out.append(_fail("S06", f"{ptr}/en", f"the English text contains Hangul: {en!r}",
                             "translate it fully into English"))
        if ph or _PLACEHOLDER.search(ko) or _PLACEHOLDER.search(en):
            pk, pe = sorted(_PLACEHOLDER.findall(ko)), sorted(_PLACEHOLDER.findall(en))
            if pk != pe:
                out.append(_fail("S06", f"{ptr}/en", f"placeholders differ: ko has {pk or 'none'}, en has "
                                                     f"{pe or 'none'}",
                                 "{0} is the bound and {1} the size name; use the same ones in both texts"))
        if ptr.endswith("/desc"):
            hk, he = index.desc_head(ko).strip(), index.desc_head(en).strip()
            if ko.strip() and en.strip() and (not hk or not he):
                out.append(_fail("S06", f"{ptr}/en", "the first sentences of desc ko and en do not form a pair",
                                 "both texts start with the param's short name, then a period"))
    return out


# ── S07 한도 ──

def _s07(part: Any, compiled: Any, raw_size: int | None) -> list[CheckResult]:
    out: list[CheckResult] = []
    if raw_size is not None and raw_size > FILE_MAX_BYTES:
        out.append(_fail("S07", "", f"the file has {raw_size} bytes", value=float(raw_size),
                         limit=float(FILE_MAX_BYTES)))
    for what, n, limit, ptr in (("params", len(part.params), PARAMS_MAX, "/params"),
                                ("body steps", len(part.body), STEPS_MAX, "/body"),
                                ("anchors", len(part.anchors), ANCHORS_MAX, "/anchors")):
        if n > limit:
            out.append(_fail("S07", ptr, f"{n} {what}; the limit is {limit}", value=float(n), limit=float(limit)))
    if compiled is None:
        return out
    # 반복을 펼친 고체 수: 정수 필드는 최댓값, 나머지는 기본값에서
    values: dict[str, object] = {}
    for name, spec in part.params.items():
        values[name] = spec.max if spec.type == "integer" else spec.default
    try:
        env = compiled.geometry_env(values)
    except DslError:
        return out  # 계산 오류는 검증기 P4 가 다룬다
    total = 0
    for i, step in enumerate(part.body):
        n = 1
        for var in (step.repeat or {}):
            e = compiled.get(f"/body/{i}/repeat/{var}")
            try:
                n *= max(0, round(float(e.evaluate(env)))) if e is not None else 1  # type: ignore[arg-type]
            except (DslError, TypeError, ValueError):
                n *= 1
        total += n
    if total > SOLIDS_MAX:
        out.append(_fail("S07", "/body", f"{total} solids after repeat expansion at the integer maxima",
                         "use fewer repeats or lower integer field maxima", value=float(total),
                         limit=float(SOLIDS_MAX)))
    return out


# ── S08 벽 두께 ──

def _s08(part: Any) -> list[CheckResult]:
    spec = part.params.get("wall_thickness_mm")
    ptr = "/params/wall_thickness_mm"
    if spec is None:
        return [_fail("S08", ptr, "a number param 'wall_thickness_mm' is required",
                      "every part declares its wall thickness (min >= 1.0, max <= 8)")]
    if spec.type != "number":
        return [_fail("S08", f"{ptr}/type", f"wall_thickness_mm must be a number, not {spec.type}")]
    out = []
    lo, hi = WALL_MIN_RANGE
    if float(spec.min) < lo:
        out.append(_fail("S08", f"{ptr}/min", f"wall_thickness_mm min {spec.min:g} is below {lo:g}",
                         value=float(spec.min), limit=lo))
    if float(spec.max) > hi:
        out.append(_fail("S08", f"{ptr}/max", f"wall_thickness_mm max {spec.max:g} is above {hi:g}",
                         value=float(spec.max), limit=hi))
    return out


# ── 묶음 ──

def static_checks(data: Mapping[str, Any], *, stem: str | None = None, raw_size: int | None = None,
                  rules: Any | None = None) -> list[CheckResult]:
    """초안(또는 게시 파일) dict 하나의 S01–S08 과 L02–L12 결과 (통과한 검사도 하나씩 넣는다).
    stem: 파일 이름에서 .json 을 뺀 것 (L10). raw_size: 파일 바이트 수 (S07). S01 이 실패하면 그 결과만 낸다."""
    from app.library.lint import lint
    from app.library.schema import parse_part

    data = {k: v for k, v in dict(data).items() if not str(k).startswith("_")}  # 시험 파일의 "_expect" 등
    try:
        part = parse_part(data, published=data.get("key") is not None, stem=stem if data.get("key") else None)
    except DslError as err:
        return [_from_error("S01", e) for e in _errors(err)]
    results: list[CheckResult] = [passed("S01", None)]

    rep = lint(part, stem=stem, rules=rules)
    compiled = None
    compile_errors: list[CheckResult] = []
    try:
        from app.library.expr import compile_part

        compiled = compile_part(part)
    except DslError as err:
        for e in _errors(err):
            if e.code == "DSL004" and _RULE_IN_GEOMETRY.match(e.message):
                continue  # L02 가 알린다
            # 출입구 모양 자리에 쓸 수 없는 모양(tube 등)은 역할·출입구 규칙 S04
            cid = "S04" if e.code == "DSL003" and e.path.endswith("/door/profile") else "S02"
            compile_errors.append(_from_error(cid, e))
    results += compile_errors
    if not any(r.id == "S02" for r in compile_errors):
        results.append(passed("S02", None))

    groups: dict[str, list[CheckResult]] = {
        "S03": _s03(part, compiled),
        "S04": _s04(part, compiled),
        "S05": _s05(part),
        "S06": _s06(data),
        "S07": _s07(part, compiled, raw_size),
        "S08": _s08(part),
    }
    for cid, res in groups.items():
        if not res and any(r.id == cid for r in results):
            continue  # 이미 실패가 있다 (S04: 출입구 모양 컴파일 오류)
        results += res or [passed(cid, None)]

    by_lint: dict[str, list[CheckResult]] = {lid: [] for lid in LINT_CHECKS}
    for issue in rep.issues:
        if issue.id == "L01":
            continue  # 식 컴파일 오류: S02
        msg = f"{issue.code}: {issue.message}" if issue.code else issue.message
        by_lint.setdefault(issue.id, []).append(
            failed(issue.id, issue.variant, msg, path=issue.path, hint=issue.hint, value=issue.value,
                   limit=issue.limit))
    for lid, res in by_lint.items():
        results += res or [passed(lid, None)]
    return _dedupe(results)


def _dedupe(results: list[CheckResult]) -> list[CheckResult]:
    seen: set[tuple] = set()
    out = []
    for r in results:
        k = (r.id, r.ok, r.path, r.message, r.variant)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def static_summary(key: str, results: list[CheckResult]) -> Any:
    """정적 검사 결과만 담은 RunSummary (verify 가 정적 검사에서 멈출 때)."""
    from app.library.verify.report import RunSummary, now_iso

    return RunSummary(key=key, profile="static", results=list(results), started_at=now_iso())


def read_draft(path: Any) -> tuple[dict, int]:
    """초안 파일 → (dict, 바이트 수). JSON 문법 오류는 DslErrors (S01 로 알린다)."""
    from pathlib import Path

    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise DslErrors.of([DslError("DSL010", "", f"invalid JSON: {e}")]) from None
    if not isinstance(data, dict):
        raise DslErrors.of([DslError("DSL013", "", "a part file is a JSON object")])
    return data, len(raw)


# ── 정적 검사 + 검증기 ──

def verify_draft(data: Mapping[str, Any], *, key: str | None = None, stem: str | None = None,
                 raw_size: int | None = None, rules: Any | None = None, profile: str = "full",
                 species: str | None = None, jobs: int | None = None, subprocess: bool = True,
                 trials: bool = True, checks: Iterable[str] | None = None) -> Any:
    """초안 하나를 검증한다 (§7.2): 정적 검사(S·L)가 실패하면 거기서 멈추고, 깨끗하면 템플릿을 만들어 run.verify 로
    P·G·C·T·R 검사를 돌린다. key: 이 초안이 받을 key (None: 라이브러리의 다음 버전). 결과는 RunSummary."""
    data = {k: v for k, v in dict(data).items() if not str(k).startswith("_")}
    family = str(data.get("family") or "draft")
    static = static_checks(data, stem=stem, raw_size=raw_size, rules=rules)
    if any(not r.ok for r in static):
        return static_summary(key or f"{family}@v?", static)
    from app.library.template import make_template, next_key
    from app.library.verify.run import verify

    key = key or data.get("key") or next_key(family)
    t = make_template(data, key=key)
    run = verify(t, rules=rules, profile=profile, species=species, jobs=jobs,  # type: ignore[arg-type]
                 draft=data, subprocess=subprocess, trials=trials, checks=checks)
    run.results = static + run.results
    return run
