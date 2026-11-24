"""Part DSL v1 파일 스키마 (app/library/schema.py, 설계 §5.2)."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from app.library.errors import DslError, DslErrors
from app.library.schema import PartFile, json_schema, load_part_json, parse_part

DATA = Path(__file__).parent / "data" / "library"
FIXTURES = ("tunnel_junction", "deck_platform", "litter_tray")


def load(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def published(name: str, version: int = 1) -> dict:
    d = load(name)
    out = {"dsl": d.pop("dsl"), "key": f"{name}@v{version}", "family": d.pop("family"), "version": version}
    out.update(d)
    return out


# ── JSON Schema 를 확인하는 작은 검사기 (draft 2020-12 중 스키마가 쓰는 키워드만) ──

SUPPORTED_KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "title", "description", "default", "type", "const", "enum", "pattern",
    "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems", "uniqueItems", "items", "required",
    "properties", "additionalProperties", "propertyNames", "minProperties", "maxProperties", "oneOf", "allOf",
    "not",
}


def _type_ok(v: object, t: str) -> bool:
    return {
        "object": isinstance(v, dict),
        "array": isinstance(v, list),
        "string": isinstance(v, str),
        "boolean": isinstance(v, bool),
        "null": v is None,
        "number": isinstance(v, (int, float)) and not isinstance(v, bool),
        "integer": (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer()),
    }[t]


def _validate(v: object, s: dict, root: dict, path: str = "") -> list[str]:
    if s is True or s == {}:
        return []
    errs: list[str] = []
    if "$ref" in s:
        target = root
        for part in s["$ref"].lstrip("#/").split("/"):
            target = target[part]
        errs += _validate(v, target, root, path)
    if "type" in s:
        ts = s["type"] if isinstance(s["type"], list) else [s["type"]]
        if not any(_type_ok(v, t) for t in ts):
            return errs + [f"{path}: type {ts}"]
    if "const" in s and not (v == s["const"] and type(v) is type(s["const"])):
        errs.append(f"{path}: const")
    if "enum" in s and v not in s["enum"]:
        errs.append(f"{path}: enum")
    if isinstance(v, str):
        if "pattern" in s and not re.search(s["pattern"], v):
            errs.append(f"{path}: pattern")
        if len(v) < s.get("minLength", 0) or len(v) > s.get("maxLength", 10**9):
            errs.append(f"{path}: length")
    if _type_ok(v, "number") and (v < s.get("minimum", -1e300) or v > s.get("maximum", 1e300)):
        errs.append(f"{path}: range")
    if isinstance(v, list):
        if len(v) < s.get("minItems", 0) or len(v) > s.get("maxItems", 10**9):
            errs.append(f"{path}: items count")
        if s.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in v}) != len(v):
            errs.append(f"{path}: unique")
        if "items" in s:
            for i, x in enumerate(v):
                errs += _validate(x, s["items"], root, f"{path}/{i}")
    if isinstance(v, dict):
        for r in s.get("required", []):
            if r not in v:
                errs.append(f"{path}: required {r}")
        if len(v) < s.get("minProperties", 0) or len(v) > s.get("maxProperties", 10**9):
            errs.append(f"{path}: properties count")
        props = s.get("properties", {})
        for k, x in v.items():
            if "propertyNames" in s:
                errs += _validate(k, s["propertyNames"], root, f"{path}/{k}(name)")
            if k in props:
                errs += _validate(x, props[k], root, f"{path}/{k}")
            elif "additionalProperties" in s:
                ap = s["additionalProperties"]
                if ap is False:
                    errs.append(f"{path}/{k}: additional")
                elif isinstance(ap, dict):
                    errs += _validate(x, ap, root, f"{path}/{k}")
    for sub in s.get("allOf", []):
        errs += _validate(v, sub, root, path)
    if "oneOf" in s:
        ok = [sub for sub in s["oneOf"] if not _validate(v, sub, root, path)]
        if len(ok) != 1:
            errs.append(f"{path}: oneOf matched {len(ok)}")
    if "not" in s and not _validate(v, s["not"], root, path):
        errs.append(f"{path}: not")
    return errs


def schema_errors(data: object) -> list[str]:
    s = json_schema()
    return _validate(data, s, s)


def _keywords(s: object, out: set[str], in_props: bool = False) -> None:
    if isinstance(s, dict):
        for k, v in s.items():
            if not in_props:
                out.add(k)
            _keywords(v, out, in_props=(k in ("properties", "$defs") and not in_props))
    elif isinstance(s, list):
        for v in s:
            _keywords(v, out)


def test_test_validator_covers_every_schema_keyword() -> None:
    found: set[str] = set()
    _keywords(json_schema(), found)
    assert found <= SUPPORTED_KEYWORDS, found - SUPPORTED_KEYWORDS


def test_json_schema_is_a_fresh_copy() -> None:
    a = json_schema()
    a["title"] = "changed"
    assert json_schema()["title"] == "NestForge Part DSL v1"
    assert json_schema()["$schema"] == "https://json-schema.org/draft/2020-12/schema"


# ── 좋은 파일 ──

@pytest.mark.parametrize("name", FIXTURES)
def test_design_drafts_are_valid(name: str) -> None:
    d = load(name)
    part = parse_part(d)
    assert isinstance(part, PartFile)
    assert part.key is None and part.version is None and not part.is_published
    assert list(part.params) == list(d["params"])  # 파라미터 순서를 지킨다
    assert schema_errors(d) == []


@pytest.mark.parametrize("name", FIXTURES)
def test_published_files_are_valid(name: str) -> None:
    d = published(name)
    part = parse_part(d, published=True, stem=f"{name}@v1")
    assert part.key == f"{name}@v1" and part.version == 1 and part.is_published
    assert schema_errors(d) == []


def test_parsed_values() -> None:
    p = parse_part(load("tunnel_junction"))
    assert p.params["layout"].type == "choice" and p.params["layout"].choices == ["I", "L", "T", "X"]
    assert p.params["wall_thickness_mm"].default == 3.0 and p.params["wall_thickness_mm"].rule_default
    assert p.anchors["front"].door is not None and p.anchors["front"].door.profile == "door_shape"
    assert p.anchors["top"].part == "body" and p.anchors["top"].openable is False
    assert p.body[0].op == "box" and p.body[0].mode == "add" and p.body[1].mode == "cut"
    assert p.print[0].rotation == "inverted"
    assert p.door_fields == ["layout", "door_shape"]
    deck = parse_part(load("deck_platform"))
    assert deck.body[1].repeat == {"i": 2}
    assert deck.features.openings[0].kind == "passage" and deck.features.openings[0].probe.shape == "box"


def test_load_part_json() -> None:
    text = (DATA / "deck_platform.json").read_text(encoding="utf-8")
    assert load_part_json(text).family == "deck_platform"
    with pytest.raises(DslError) as e:
        load_part_json("{not json")
    assert e.value.code == "DSL010"


# ── 나쁜 파일: (바꾸는 함수, 코드, 포인터). 구조 규칙이라 JSON Schema 도 거부해야 한다 ──

def _set(path: str, value: object) -> Callable[[dict], None]:
    def f(d: dict) -> None:
        *head, last = [int(p) if p.isdigit() else p for p in path.strip("/").split("/")]
        node = d
        for p in head:
            node = node[p]
        node[last] = value
    return f


def _del(path: str) -> Callable[[dict], None]:
    def f(d: dict) -> None:
        *head, last = [int(p) if p.isdigit() else p for p in path.strip("/").split("/")]
        node = d
        for p in head:
            node = node[p]
        del node[last]
    return f


STRUCTURAL = [
    (_del("/features"), "DSL011", "/features"),
    (_del("/params/size_mm/desc"), "DSL011", "/params/size_mm/desc"),
    (_del("/body/0/size"), "DSL011", "/body/0/size"),
    (_del("/anchors/front/up"), "DSL011", "/anchors/front/up"),
    (_set("/bogus", 1), "DSL012", "/bogus"),
    (_set("/body/0/sizes", [1, 2, 3]), "DSL012", "/body/0/sizes"),
    (_set("/params/size_mm/step", 1), "DSL012", "/params/size_mm/step"),
    (_set("/anchors/front/door/shape", "box"), "DSL012", "/anchors/front/door/shape"),
    (_set("/features/openings", [{"kind": "vent", "step": "x", "label": {"ko": "가", "en": "a"}, "size": 1}]),
     "DSL012", "/features/openings/0/size"),
    (_set("/name", "터널"), "DSL013", "/name"),
    (_set("/params/size_mm/min", True), "DSL013", "/params/size_mm/min"),
    (_set("/params/size_mm/min", "60"), "DSL013", "/params/size_mm/min"),
    (_set("/params/layout/default", 1), "DSL013", "/params/layout/default"),
    (_set("/body/0/size/0", True), "DSL013", "/body/0/size/0"),
    (_set("/body/0/size/0", ["S"]), "DSL013", "/body/0/size/0"),
    (_set("/anchors/front/openable", "yes"), "DSL013", "/anchors/front/openable"),
    (_set("/body/0/when", None), "DSL013", "/body/0/when"),
    (_set("/part_id", None), "DSL013", "/part_id"),
    (_set("/body/0/size", ["S", "S"]), "DSL010", "/body/0/size"),
    (_set("/body/0/size/0", ""), "DSL010", "/body/0/size/0"),
    (_set("/body/0/size/0", "S + " * 100 + "1"), "DSL010", "/body/0/size/0"),
    (_set("/body/1/op", "boxx"), "DSL010", "/body/1"),
    (_set("/body/0/mode", "subtract"), "DSL010", "/body/0/mode"),
    (_set("/body/0/repeat", {"k": 2}), "DSL010", "/body/0/repeat/k"),
    (_set("/body/0/repeat", {}), "DSL010", "/body/0/repeat"),
    (_set("/params/layout/type", "enum"), "DSL010", "/params/layout"),
    (_set("/params/layout/choices", ["I"]), "DSL010", "/params/layout/choices"),
    (_set("/params/layout/choices", ["I", "L", "T", "X", "I"]), "DSL010", "/params/layout/choices"),
    (_set("/params/layout/choices", ["I", "L", "T", "x-y"]), "DSL010", "/params/layout/choices/3"),
    (_set("/params/Size", {"type": "bool", "default": True, "desc": {"ko": "가", "en": "a"}}), "DSL010",
     "/params/Size"),
    (_set("/params/model_x", {"type": "bool", "default": True, "desc": {"ko": "가", "en": "a"}}), "DSL010",
     "/params/model_x"),
    (_set("/family", "Tunnel"), "DSL010", "/family"),
    (_set("/family", "tj"), "DSL010", "/family"),
    (_set("/part_id", "body"), "DSL010", "/part_id"),
    (_set("/part_id", "model_hub"), "DSL010", "/part_id"),
    (_set("/color", "#C9A46E"), "DSL010", "/color"),
    (_set("/habitats", ["aquarium"]), "DSL010", "/habitats/0"),
    (_set("/habitats", []), "DSL010", "/habitats"),
    (_set("/role", "connector"), "DSL010", "/role"),
    (_set("/anchors/front/normal", "-y"), "DSL010", "/anchors/front/normal"),
    (_set("/anchors/front/side", "top"), "DSL010", "/anchors/front/side"),
    (_set("/anchors/Front", {"origin": [0, 0, 0], "normal": "-Y", "up": "+Z"}), "DSL010", "/anchors/Front"),
    (_set("/print/0/rotation", "sideways"), "DSL010", "/print/0/rotation"),
    (_set("/print", []), "DSL010", "/print"),
    (_set("/body", []), "DSL010", "/body"),
    (_set("/keywords/ko", ["가" * 21]), "DSL010", "/keywords/ko/0"),
    (_set("/name/ko", "가" * 21), "DSL010", "/name/ko"),
    (_set("/description/ko", "가" * 201), "DSL010", "/description/ko"),
    (_set("/name/en", ""), "DSL010", "/name/en"),
    (_set("/size_fields", ["size_mm", "size_mm"]), "DSL010", "/size_fields"),
    (_set("/attach_order/slide", ["back", "back"]), "DSL010", "/attach_order/slide"),
    (_set("/attach_order/drag", ["back"]), "DSL012", "/attach_order/drag"),
    (_set("/constraints/0/max", "1"), "DSL010", "/constraints/0"),
    (_del("/constraints/0/min"), "DSL010", "/constraints/0"),
    (_set("/constraints/0/source", "rule"), "DSL010", "/constraints/0/source"),
    (_set("/opens", [{"anchor": "back", "set": {}}]), "DSL010", "/opens/0/set"),
    (_set("/body/1", {"op": "passage", "shape": "door_shape", "width": 10, "axis": "x", "length": 5}), "DSL011",
     "/body/1/mode"),
    (_set("/body/1", {"op": "passage", "shape": "door_shape", "width": 10, "axis": "z", "length": 5,
                      "mode": "cut"}), "DSL010", "/body/1/axis"),
    (_set("/body/1", {"op": "passage", "shape": "door_shape", "width": 10, "axis": "x", "length": 5,
                      "mode": "add"}), "DSL010", "/body/1/mode"),
    (_set("/body/1", {"op": "prism", "plane": "xz", "points": [[0, 0], [1, 0]], "depth": 2}), "DSL010",
     "/body/1/points"),
    (_set("/body/1", {"op": "cylinder", "r": 1, "h": 2, "axis": "w"}), "DSL010", "/body/1/axis"),
    (_set("/features/openings", [{"kind": "passage", "size": 1, "label": {"ko": "가", "en": "a"},
                                  "probe": {"shape": "tube", "axis": "y", "at": [0, 0, 0], "length": 1}}]),
     "DSL010", "/features/openings/0/probe/shape"),
    (_set("/features/openings", [{"kind": "hole", "label": {"ko": "가", "en": "a"}}]), "DSL010",
     "/features/openings/0"),
]


@pytest.mark.parametrize("mutate,code,ptr", STRUCTURAL)
def test_structural_errors(mutate: Callable[[dict], None], code: str, ptr: str) -> None:
    d = load("tunnel_junction")
    mutate(d)
    with pytest.raises(DslErrors) as e:
        parse_part(d)
    got = [(x.code, x.path) for x in e.value.errors]
    assert (code, ptr) in got, got
    assert schema_errors(d), "the JSON Schema must reject it too"


# pydantic 에만 있는 규칙 (JSON Schema 로는 적을 수 없다): JSON Schema 는 통과시키고 pydantic 은 거부한다
SEMANTIC = [
    (_set("/params/size_mm/default", 300), "DSL010", "/params/size_mm"),
    (_set("/params/size_mm/min", 300), "DSL010", "/params/size_mm"),
    (_set("/params/layout/default", "Q"), "DSL010", "/params/layout"),
    (_set("/params/layout/choice_labels", {"Q": {"ko": "가", "en": "a"}}), "DSL010", "/params/layout"),
    (_set("/key", "tunnel_junction@v1"), "DSL014", "/key"),
    (_set("/version", 1), "DSL014", "/key"),
]


@pytest.mark.parametrize("mutate,code,ptr", SEMANTIC)
def test_semantic_errors(mutate: Callable[[dict], None], code: str, ptr: str) -> None:
    d = load("tunnel_junction")
    mutate(d)
    with pytest.raises(DslErrors) as e:
        parse_part(d)
    assert (code, ptr) in [(x.code, x.path) for x in e.value.errors]
    assert schema_errors(d) == []


def test_unsupported_dsl_version() -> None:
    d = load("deck_platform")
    d["dsl"] = 2
    with pytest.raises(DslErrors) as e:
        parse_part(d)
    err = e.value.errors[0]
    assert (err.code, err.path) == ("DSL014", "/dsl") and "unsupported dsl version 2" in err.message
    assert schema_errors(d)


def test_published_identity() -> None:
    d = published("deck_platform")
    parse_part(d, published=True, stem="deck_platform@v1")
    with pytest.raises(DslError) as e:
        parse_part(d, published=True, stem="deck_platform@v2")
    assert (e.value.code, e.value.path) == ("DSL014", "/key")
    with pytest.raises(DslError) as e:
        parse_part(load("deck_platform"), published=True)
    assert e.value.code == "DSL014" and "needs key and version" in e.value.message
    bad = published("deck_platform")
    bad["key"] = "deck_platform@v2"
    with pytest.raises(DslError) as e:
        parse_part(bad)
    assert (e.value.code, e.value.path) == ("DSL014", "/key")


def test_errors_are_collected_and_hinted() -> None:
    d = load("tunnel_junction")
    d["bogus"] = 1
    d["body"][0]["sizes"] = 1
    del d["features"]
    d["part_id"] = "Hub"
    with pytest.raises(DslErrors) as e:
        parse_part(d)
    errs = {x.path: x for x in e.value.errors}
    assert set(errs) >= {"/bogus", "/body/0/sizes", "/features", "/part_id"}
    assert errs["/body/0/sizes"].hint == "did you mean 'size'?"
    assert errs["/features"].message == "missing required field 'features'"
    assert "4 errors" in str(e.value)
    assert e.value.to_dict()["errors"][0].keys() == {"code", "path", "message", "hint"}


def test_non_object_and_numbers() -> None:
    with pytest.raises(DslError) as e:
        parse_part([1, 2])
    assert e.value.code == "DSL013"
    d = load("deck_platform")
    d["body"][0]["size"] = [160, 120.5, "dt"]  # JSON 숫자와 식을 섞어 쓸 수 있다
    part = parse_part(d)
    assert part.body[0].size == [160, 120.5, "dt"]
    d["params"]["width_mm"]["default"] = 160  # number 형은 정수 JSON 도 받는다
    parse_part(d)
    d["params"]["wall_thickness_mm"] = {"type": "integer", "default": 3.0, "min": 1, "max": 8,
                                        "desc": {"ko": "가", "en": "a"}}
    with pytest.raises(DslError):
        parse_part(d)


def test_draft_and_published_round_trip_through_json() -> None:
    d = published("tunnel_junction")
    text = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    part = load_part_json(text, published=True, stem="tunnel_junction@v1")
    assert part.model_dump(mode="json", exclude_unset=True) == d
    # 깊은 사본이 원본을 바꾸지 않는다
    assert copy.deepcopy(d) == d
