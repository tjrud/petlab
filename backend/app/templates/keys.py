"""템플릿 키 → 모듈 이름 (형상 커널을 불러오지 않고 형상 지문을 계산할 때 쓴다). registry 와 같아야 한다(테스트로 확인)."""

TEMPLATE_MODULES: dict[str, str] = {
    "hideout": "app.templates.hideout",
    "tunnel": "app.templates.tunnel",
    "ramp": "app.templates.ramp",
    "sand_bath": "app.templates.sand_bath",
}
