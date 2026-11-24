"""Part DSL 오류.

오류마다 코드, JSON 포인터 경로, 열(1부터), 영어 메시지와 고치는 방법(hint)을 담는다. 개발자 에이전트(나중에는 LLM)가
그대로 읽고 고칠 수 있게 메시지는 짧고 구체적으로 쓴다.

코드:
- DSL001 문법 (허용하지 않는 식 요소 포함)
- DSL002 모르는 이름
- DSL003 형(type)이 맞지 않음
- DSL004 이 자리에서 쓸 수 없는 이름 (geometry 에서 rule./ctx., 뒤에 선언한 파라미터 등)
- DSL005 한도 초과 (식 길이·노드 수·중첩·식 개수)
- DSL006 값 계산 오류 (0 으로 나누기, 음수의 sqrt, 무한대·NaN, 값이 없는 규칙)
- DSL007 이름 정의 오류 (중복, 예약어)
- DSL010 스키마: 값이 허용 범위·형식을 벗어남
- DSL011 스키마: 필수 항목 없음
- DSL012 스키마: 모르는 항목
- DSL013 스키마: JSON 형이 다름
- DSL014 게시 파일의 key·version·파일 이름이 서로 맞지 않음, 지원하지 않는 dsl 버전
"""

from __future__ import annotations

from dataclasses import dataclass, field

CODES: dict[str, str] = {
    "DSL001": "syntax",
    "DSL002": "unknown name",
    "DSL003": "type",
    "DSL004": "name not allowed here",
    "DSL005": "limit",
    "DSL006": "evaluation",
    "DSL007": "name definition",
    "DSL010": "schema value",
    "DSL011": "schema missing field",
    "DSL012": "schema unknown field",
    "DSL013": "schema JSON type",
    "DSL014": "file identity",
}


def pointer(*parts: object) -> str:
    """JSON 포인터 (RFC 6901). pointer("params", "size_mm", "min") == "/params/size_mm/min"."""
    out = []
    for p in parts:
        s = str(p).replace("~", "~0").replace("/", "~1")
        out.append("/" + s)
    return "".join(out)


@dataclass(eq=False)
class DslError(Exception):
    """DSL 파일·식의 오류 하나."""

    code: str
    path: str = ""
    message: str = ""
    hint: str = ""
    col: int | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.__str__())

    def __str__(self) -> str:
        where = self.path or "/"
        if self.col is not None:
            where += f" (col {self.col})"
        s = f"{self.code} {where}: {self.message}"
        if self.hint:
            s += f" (hint: {self.hint})"
        return s

    def __reduce__(self):  # 검증 작업 프로세스 사이로 오류를 넘길 때 (pickle)
        return (DslError, (self.code, self.path, self.message, self.hint, self.col))

    def at(self, path: str) -> DslError:
        """경로가 비어 있으면 path 로 채운 사본."""
        if self.path:
            return self
        return DslError(self.code, path, self.message, self.hint, self.col)

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "path": self.path}
        if self.col is not None:
            d["col"] = self.col
        d["message"] = self.message
        d["hint"] = self.hint
        return d


@dataclass(eq=False)
class DslErrors(DslError):
    """오류 여러 개 (파일 검사). 코드·경로·메시지는 첫 오류의 것이라 DslError 로 잡아도 된다."""

    errors: list[DslError] = field(default_factory=list)

    @classmethod
    def of(cls, errors: list[DslError]) -> DslErrors:
        if not errors:
            raise ValueError("DslErrors needs at least one error")
        first = errors[0]
        return cls(first.code, first.path, first.message, first.hint, first.col, list(errors))

    def __reduce__(self):
        return (DslErrors, (self.code, self.path, self.message, self.hint, self.col, list(self.errors)))

    def __str__(self) -> str:
        if len(self.errors) <= 1:
            return DslError.__str__(self)
        lines = [f"{len(self.errors)} errors:"] + [f"  {DslError.__str__(e)}" for e in self.errors]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"errors": [e.to_dict() for e in self.errors]}
