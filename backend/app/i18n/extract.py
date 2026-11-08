"""백엔드 코드·규칙 파일에서 사용자에게 보이는 한국어 문구를 모은다 (영어 카탈로그가 빠짐없는지 확인용).

- 코드: 문자열·f-문자열 중 한글이 있는 것. f-문자열의 {값} 은 {0}, {1} … 자리표시로 바꾼다.
  문서 문자열, 로그(log.*), 예외 detail(내부 기록), LLM 프롬프트(app/llm/prompts.py)는 뺀다.
- 규칙 파일(rules/*.yaml): 한글이 있는 값.

python -m app.i18n.extract  → 카탈로그에 없는 문구를 출력한다
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]  # backend/
APP = ROOT / "app"
RULES = ROOT / "rules"
HANGUL = re.compile(r"[가-힣]")

# 사용자에게 보이지 않는 문구가 있는 파일
SKIP_FILES = {"app/llm/prompts.py", "app/i18n/extract.py", "app/i18n/__init__.py"}
LOG_FUNCS = {"debug", "info", "warning", "error", "exception", "critical"}
# 홀로는 번역할 수 없는 조각 (조사 등). 문장 틀 쪽에서 번역한다
IGNORE = {"이", "가"}


def _template(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out, n = "", 0
        for v in node.values:
            if isinstance(v, ast.Constant):
                out += str(v.value).replace("{", "{{").replace("}", "}}") if False else str(v.value)
            else:
                out += "{" + str(n) + "}"
                n += 1
        return out
    return None


def _skip_parents(tree: ast.AST) -> set[int]:
    """문서 문자열·로그 호출·detail= 인자 안의 노드 id."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, (ast.Constant, ast.JoinedStr)):
                skip.add(id(body[0].value))
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in LOG_FUNCS:
                for sub in ast.walk(node):
                    skip.add(id(sub))
            for kw in node.keywords:
                if kw.arg == "detail":
                    for sub in ast.walk(kw.value):
                        skip.add(id(sub))
    return skip


def code_strings() -> dict[str, list[str]]:
    """{문구: [파일:줄, …]}"""
    found: dict[str, list[str]] = {}
    for f in sorted(APP.rglob("*.py")):
        rel = f.relative_to(ROOT).as_posix()
        if rel in SKIP_FILES:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        skip = _skip_parents(tree)
        inner: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    inner.add(id(v))
        for node in ast.walk(tree):
            if id(node) in skip or id(node) in inner:
                continue
            t = _template(node)
            if t and HANGUL.search(t):
                found.setdefault(t, []).append(f"{rel}:{getattr(node, 'lineno', 0)}")
    return found


def rule_strings() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}

    def walk(v: object, where: str) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{where}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{where}[{i}]")
        elif isinstance(v, str) and HANGUL.search(v):
            found.setdefault(v.strip(), []).append(where)

    for f in sorted(RULES.glob("*.yaml")):
        walk(yaml.safe_load(f.read_text(encoding="utf-8")), f"rules/{f.name}")
    return found


def all_strings() -> dict[str, list[str]]:
    out = code_strings()
    for k, v in rule_strings().items():
        out.setdefault(k, []).extend(v)
    return out


def missing() -> dict[str, list[str]]:
    from app.i18n import _CATALOG_DIR

    have: set[str] = set()
    for f in _CATALOG_DIR.glob("*.json"):
        have.update(json.loads(f.read_text(encoding="utf-8")))
    return {k: v for k, v in all_strings().items() if k not in have and k not in IGNORE}


if __name__ == "__main__":
    data = all_strings() if "--all" in sys.argv else missing()
    json.dump(data, sys.stdout, ensure_ascii=False, indent=1)
    print(f"\n{len(data)} strings", file=sys.stderr)
