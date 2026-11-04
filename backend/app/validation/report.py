"""검증 보고서 모델."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    error = "error"      # 안전·출력 불가 문제 → 해결 전 내려받기 불가
    warning = "warning"  # 주의 (서포트 필요, 출력 공간 초과, 마릿수 등)
    info = "info"        # 참고 (자동 보정 내역 등)


class Issue(BaseModel):
    code: str
    severity: Severity
    message_ko: str
    item_index: int | None = None
    related_index: int | None = None
    auto_fixed: bool = False
    details: dict = Field(default_factory=dict)


class ValidationReport(BaseModel):
    issues: list[Issue] = Field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.error and not i.auto_fixed]

    @property
    def passed(self) -> bool:
        return not self.errors

    def extend(self, issues: list[Issue]) -> None:
        self.issues.extend(issues)
