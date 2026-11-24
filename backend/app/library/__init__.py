"""부품 라이브러리 (Part DSL v1).

개발자 에이전트가 오프라인으로 쓴 부품 JSON(app/library/parts/<family>@v<N>.json)을 읽어 템플릿으로 등록한다.
서버는 부품을 만들려고 AI 를 부르지 않는다. 가벼운 모듈(errors, schema, expr, index)은 형상 커널을 불러오지 않는다.
이 패키지 자체도 아무것도 import 하지 않는다 (가벼운 경로가 무거운 모듈을 끌어오지 않게).
"""
