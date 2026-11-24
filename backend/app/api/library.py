"""부품 라이브러리 표시 정보 (누구나): 라이브러리 부품의 이름·색·파라미터 이름·선택지 이름 (설계 문서 §13).

프론트엔드는 코드 부품의 표시 정보를 정적 표로 갖고 있고, 라이브러리 부품(family@vN)은 이 응답으로 채운다.
…_ko 열쇠의 값은 응답 미들웨어가 요청 언어로 바꾼다 (영어 문구는 app/i18n/en/library.json).

가벼운 요청이다: 색인(app.library.index)과 부품 JSON 파일만 읽고 형상 커널·LLM SDK 를 불러오지 않는다 (R9).
저장된 설계를 보여 줘야 하므로 폐기·차단한 부품도 넣는다 (status 로 구분).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.library import index

router = APIRouter(prefix="/library", tags=["부품 라이브러리"])

# 색인이 바뀌는 것은 배포 때뿐이다. 5분 동안 브라우저가 다시 묻지 않게 한다 (언어별로 따로: Vary X-Lang)
CACHE_CONTROL = "max-age=300"


class ParamDisplayOut(BaseModel):
    label_ko: str
    unit: Literal["mm", "deg"] | None = None


class ChoiceDisplayOut(BaseModel):
    label_ko: str


class PartDisplayOut(BaseModel):
    name_ko: str
    color: str
    status: Literal["active", "retired", "blocked"]
    params: dict[str, ParamDisplayOut]
    choices: dict[str, dict[str, ChoiceDisplayOut]]


class LibraryDisplayOut(BaseModel):
    parts: dict[str, PartDisplayOut]


@router.get("/display", response_model=LibraryDisplayOut, summary="라이브러리 부품 표시 정보 (누구나)")
def library_display(response: Response) -> dict:
    response.headers["Cache-Control"] = CACHE_CONTROL
    return {"parts": index.display_meta()}
