"""검증용 엔진 문맥 (설계 §16 T7, Appendix A).

게시 전 초안은 species.yaml 의 templates 에 없으므로 엔진(run_engine)이 template_not_allowed 로 막는다. engine.py 를
고치지 않고(R1) 이 하위 클래스가 allowed_templates 에 초안 key 를 더한다. 초안 템플릿 자체는 registry.overlay 로
잠시 등록한다 (get_template·primitives 가 찾게). 서버는 이 클래스를 쓰지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.engine import EngineContext


@dataclass(frozen=True)
class VerifyEngineContext(EngineContext):
    """EngineContext 와 같고, allowed_templates 에 extra_templates(검증하는 초안 key)를 더한다."""

    extra_templates: tuple[str, ...] = ()

    @property
    def allowed_templates(self) -> tuple[str, ...]:
        base = self.rules.allowed_templates(self.species)
        return base + tuple(k for k in self.extra_templates if k not in base)
