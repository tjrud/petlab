"""템플릿 키 → 모듈 이름 (형상 커널을 불러오지 않고 형상 지문을 계산할 때 쓴다). registry 와 같아야 한다(테스트로 확인).

TEMPLATE_MODULES 는 코드로 만든 부품만 담는다. 부품 라이브러리(app/library)에 게시된 부품의 키(`family@vN`)는
known_template_keys() 가 색인(index.json)에서 읽어 더한다. 이 모듈은 다른 모듈을 맨 위에서 import 하지 않는다
(규칙 로더가 불러 쓰므로 순환이 생기지 않게).
"""

TEMPLATE_MODULES: dict[str, str] = {
    "hideout": "app.templates.hideout",
    "tunnel": "app.templates.tunnel",
    "ramp": "app.templates.ramp",
    "sand_bath": "app.templates.sand_bath",
    "house": "app.templates.house",
    "cave": "app.templates.cave",
    "bowl_holder": "app.templates.bowl_holder",
    "bottle_stand": "app.templates.bottle_stand",
}


def library_template_keys() -> tuple[str, ...]:
    """부품 라이브러리에 게시된 부품의 키 (key 순, 상태와 상관없이: 폐기·차단 부품도 저장된 설계를 다시 만든다)."""
    from app.library import index  # 가벼운 모듈 (json·pydantic 만 쓴다)

    return index.keys()


def is_library_key(key: str) -> bool:
    """코드 부품이 아닌, 라이브러리에 게시된 부품 키인지."""
    if key in TEMPLATE_MODULES:
        return False
    from app.library import index

    return index.is_library_key(key)


def known_template_keys() -> tuple[str, ...]:
    """만들 수 있는 모든 템플릿 키: 코드 부품(TEMPLATE_MODULES 순서) 뒤에 라이브러리 부품(key 순). 레지스트리 순서와 같다."""
    return tuple(TEMPLATE_MODULES) + tuple(k for k in library_template_keys() if k not in TEMPLATE_MODULES)
