"""부품 검증기 (설계 §7). "이 부품이 안전하고 다른 부품과 이어 쓸 수 있는가"의 단 하나의 구현이다 (원칙 4).

DSL 부품(초안·게시)과 코드 부품 모두 Template API 로만 본다. 코드 부품에는 이것이 계약 시험이다
(tests/test_part_contract.py, 면제마다 적힌 사유). DSL 부품은 면제가 없다 (R6).

모듈:
- report     CheckResult, 보고서 dict, CLI 요약 (가벼움)
- variants   종·크기 구분마다의 규칙 문맥과 파라미터 변형, P1–P4
- geometry   G01–G07, G10, G12 (engine.build_item 으로 만든 형상)
- honesty    G08 틈 끼임 자가 검사, G09 특징 정직성, G11 넘어짐 각도
- anchors    C01–C08 (시험 파일이 함께 쓰는 check_anchors·bumped·profile_iou 도 여기)
- trials     시험 조립 T01–T02
- engine_ctx VerifyEngineContext (초안 key 를 허용 템플릿에 더한다)
- rebuild    새 프로세스 다시 만들기 (G12)
- run        verify(): 모든 검사를 묶어 RunSummary 를 낸다

이 패키지 자체는 아무것도 import 하지 않는다 (report 만 가볍다; 나머지는 형상 커널을 불러온다).
"""
