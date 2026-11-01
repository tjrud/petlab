"""설계 생성·수정·내보내기 서비스.

파이프라인: 사육 환경 + 프롬프트 → LLM 해석(DesignSpec) → 엔진(보정·형상·배치·검증) → 버전 저장.
수정 시 직전 버전의 '보정 반영 명세'를 LLM 에 맥락으로 주고 새 버전을 만든다 (이전 버전 유지).
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path

import trimesh
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import Cage, Placement, PlacementHint
from app.geometry.export import ExportFile, ExportPart, export_parts
from app.llm.base import HabitatInfo, InterpretRequest, Interpreter
from app.llm.spec import parse_spec, to_item_specs
from app.models import Design, DesignVersion, Habitat
from app.rules.loader import RuleBook
from app.schemas import (
    CageIn,
    DesignOut,
    HabitatIn,
    HabitatOut,
    ItemOut,
    PlacementOut,
    VersionOut,
    VersionSummary,
)
from app.services.engine import EngineContext, build_item, run_engine
from app.templates.registry import get_template

log = logging.getLogger(__name__)


class NotFoundError(LookupError):
    def __init__(self, message_ko: str):
        super().__init__(message_ko)
        self.message_ko = message_ko


class InvalidInputError(ValueError):
    def __init__(self, message_ko: str):
        super().__init__(message_ko)
        self.message_ko = message_ko


class ExportBlockedError(RuntimeError):
    def __init__(self, message_ko: str, errors: list[dict]):
        super().__init__(message_ko)
        self.message_ko = message_ko
        self.errors = errors


class DesignService:
    def __init__(self, rules: RuleBook, interpreter: Callable[[], Interpreter], mesh_dir: Path):
        self.rules = rules
        self._interpreter = interpreter
        self.mesh_dir = Path(mesh_dir)

    # ── 사육 환경 ───────────────────────────────────────────

    def create_habitat(self, db: Session, data: HabitatIn) -> Habitat:
        try:
            self.rules.size_rules(data.species, data.size)
        except KeyError:
            raise InvalidInputError(f"지원하지 않는 종/크기입니다: {data.species}/{data.size}") from None
        h = Habitat(
            species=data.species, size=data.size, count=data.count,
            cage_width_mm=data.cage.width_mm, cage_depth_mm=data.cage.depth_mm, cage_height_mm=data.cage.height_mm,
        )
        db.add(h)
        db.commit()
        return h

    def get_habitat(self, db: Session, habitat_id: str) -> Habitat:
        h = db.get(Habitat, habitat_id)
        if h is None:
            raise NotFoundError("사육 환경을 찾을 수 없습니다.")
        return h

    def habitat_out(self, h: Habitat) -> HabitatOut:
        sp = self.rules.species_file.species.get(h.species)
        size = sp.sizes.get(h.size) if sp else None
        return HabitatOut(
            id=h.id, species=h.species, species_name_ko=sp.display_name if sp else h.species,
            size=h.size, size_name_ko=size.display_name if size else h.size, count=h.count,
            cage=CageIn(width_mm=h.cage_width_mm, depth_mm=h.cage_depth_mm, height_mm=h.cage_height_mm),
            created_at=h.created_at,
        )

    @staticmethod
    def _cage(h: Habitat) -> Cage:
        return Cage(h.cage_width_mm, h.cage_depth_mm, h.cage_height_mm)

    def _engine_ctx(self, h: Habitat) -> EngineContext:
        return EngineContext(cage=self._cage(h), species=h.species, size=h.size, count=h.count, rules=self.rules)

    # ── 설계 생성 / 수정 ─────────────────────────────────────

    def create_design(self, db: Session, habitat_id: str, prompt: str) -> tuple[Design, DesignVersion]:
        h = self.get_habitat(db, habitat_id)
        version = self._generate(h, prompt, previous=None)  # LLM 실패 시 예외 → 아무것도 저장하지 않음
        design = Design(habitat_id=h.id)
        db.add(design)
        db.flush()
        self._save_version(db, design, version, 1)
        db.commit()
        return design, version["row"]

    def revise_design(
        self, db: Session, design_id: str, prompt: str, base_version: int | None = None
    ) -> tuple[Design, DesignVersion]:
        design = self.get_design(db, design_id)
        base = self.get_version(db, design, base_version)
        previous = self._previous_spec(base)
        generated = self._generate(design.habitat, prompt, previous=previous)
        next_no = (db.scalar(select(func.max(DesignVersion.version)).where(DesignVersion.design_id == design.id)) or 0) + 1
        self._save_version(db, design, generated, next_no)
        db.commit()
        db.refresh(design)
        return design, generated["row"]

    @staticmethod
    def _previous_spec(base: DesignVersion):
        for candidate in (base.effective_spec, base.llm_spec):
            try:
                import json

                return parse_spec(json.dumps(candidate, ensure_ascii=False))
            except Exception:  # 검증 실패 시 다음 후보
                continue
        return None

    def _generate(self, h: Habitat, prompt: str, previous) -> dict:
        size_rules = self.rules.size_rules(h.species, h.size)
        species_name = self.rules.species_file.species[h.species].display_name
        req = InterpretRequest(
            prompt=prompt,
            habitat=HabitatInfo(h.species, species_name, h.size, h.count, self._cage(h)),
            size_rules=size_rules,
            min_wall_mm=self.rules.min_wall_for(h.species, h.size),
            previous=previous,
        )
        result = self._interpreter().interpret(req)
        engine_result = run_engine(to_item_specs(result.spec), self._engine_ctx(h))
        return {"prompt": prompt, "interpret": result, "engine": engine_result}

    def _save_version(self, db: Session, design: Design, g: dict, version_no: int) -> None:
        spec = g["interpret"].spec
        llm_spec = spec.model_dump(mode="json")
        engine = g["engine"]
        effective = copy.deepcopy(llm_spec)
        built_items = []
        effective_items = []
        for it in engine.items:
            src = llm_spec["items"][it.index]
            params = it.params.model_dump(mode="json") if it.params is not None else src["params"]
            effective_items.append({**copy.deepcopy(src), "params": params})
            lo, hi = it.mesh.bounds
            built_items.append({
                "index": it.index,
                "template": it.key,
                "label_ko": it.label_ko,
                "params": params,
                "reason_ko": src.get("reason_ko", ""),
                "hint": src["placement"],
                "placement": (
                    {"x_mm": it.placement.x_mm, "y_mm": it.placement.y_mm, "rotation_deg": it.placement.rotation_deg}
                    if it.placement else None
                ),
                "size_mm": [float(v) for v in (hi - lo)],
                "print_size_mm": [float(v) for v in it.print_mesh.extents],
            })
        if effective_items:
            effective["items"] = effective_items

        row = DesignVersion(
            design_id=design.id, version=version_no, prompt=g["prompt"],
            provider=g["interpret"].provider, llm_attempts=g["interpret"].attempts,
            llm_spec=llm_spec, effective_spec=effective, items=built_items,
            report=engine.report.model_dump(mode="json"), passed=engine.report.passed,
        )
        db.add(row)
        db.flush()
        g["row"] = row
        # 메시 캐시 저장 (뷰어용 배치 메시 + 출력 자세 메시)
        d = self._version_dir(design.id, version_no)
        d.mkdir(parents=True, exist_ok=True)
        for it in engine.items:
            it.print_mesh.export(d / f"print_{it.index}.stl")
            if it.placement is not None:
                it.world_mesh().export(d / f"world_{it.index}.stl")

    # ── 조회 ────────────────────────────────────────────────

    def get_design(self, db: Session, design_id: str) -> Design:
        d = db.get(Design, design_id)
        if d is None:
            raise NotFoundError("설계를 찾을 수 없습니다.")
        return d

    def get_version(self, db: Session, design: Design, version: int | None) -> DesignVersion:
        if not design.versions:
            raise NotFoundError("설계 버전이 없습니다.")
        if version is None:
            return design.versions[-1]
        for v in design.versions:
            if v.version == version:
                return v
        raise NotFoundError(f"버전 {version} 을(를) 찾을 수 없습니다.")

    def design_out(self, design: Design, v: DesignVersion) -> DesignOut:
        items = [
            ItemOut(
                index=it["index"], template=it["template"], label_ko=it["label_ko"], params=it["params"],
                reason_ko=it["reason_ko"],
                placement=PlacementOut(**it["placement"]) if it["placement"] else None,
                size_mm=it["size_mm"], print_size_mm=it["print_size_mm"],
                mesh_url=(f"/designs/{design.id}/versions/{v.version}/parts/{it['index']}.stl"
                          if it["placement"] else None),
            )
            for it in v.items
        ]
        report = dict(v.report)
        issues = report.get("issues", [])
        errors = [i for i in issues if i["severity"] == "error" and not i.get("auto_fixed")]
        validation = {
            "passed": v.passed,
            "summary": {
                "errors": len(errors),
                "warnings": sum(1 for i in issues if i["severity"] == "warning"),
                "auto_fixed": sum(1 for i in issues if i.get("auto_fixed")),
            },
            "issues": issues,
        }
        return DesignOut(
            id=design.id,
            habitat=self.habitat_out(design.habitat),
            versions=[
                VersionSummary(version=x.version, prompt=x.prompt, passed=x.passed, provider=x.provider,
                               created_at=x.created_at)
                for x in design.versions
            ],
            current=VersionOut(
                version=v.version, prompt=v.prompt, provider=v.provider,
                summary_ko=v.llm_spec.get("summary_ko", ""), notes_ko=v.llm_spec.get("notes_ko", []),
                items=items, validation=validation, export_allowed=v.passed and bool(items),
                created_at=v.created_at,
            ),
        )

    # ── 메시 / 내보내기 ──────────────────────────────────────

    def _version_dir(self, design_id: str, version: int) -> Path:
        return self.mesh_dir / design_id / f"v{version}"

    def _ensure_meshes(self, design: Design, v: DesignVersion) -> Path:
        """메시 캐시가 없으면(삭제 등) 저장된 최종 파라미터로 다시 생성한다 (형상 생성은 결정적)."""
        d = self._version_dir(design.id, v.version)
        missing = [it for it in v.items if not (d / f"print_{it['index']}.stl").is_file()
                   or (it["placement"] and not (d / f"world_{it['index']}.stl").is_file())]
        if missing:
            d.mkdir(parents=True, exist_ok=True)
            for it in missing:
                t = get_template(it["template"])
                built = build_item(it["index"], t, t.Params.model_validate(it["params"]), PlacementHint(),
                                   self.rules.printing)
                built.print_mesh.export(d / f"print_{it['index']}.stl")
                if it["placement"]:
                    built.placement = Placement(**it["placement"])
                    built.world_mesh().export(d / f"world_{it['index']}.stl")
        return d

    def part_mesh_path(self, db: Session, design_id: str, version: int, index: int) -> Path:
        design = self.get_design(db, design_id)
        v = self.get_version(db, design, version)
        if not any(it["index"] == index and it["placement"] for it in v.items):
            raise NotFoundError("해당 구조물 메시가 없습니다.")
        return self._ensure_meshes(design, v) / f"world_{index}.stl"

    def export(self, db: Session, design_id: str, version: int | None, fmt: str) -> ExportFile:
        design = self.get_design(db, design_id)
        v = self.get_version(db, design, version)
        if not v.passed or not v.items:
            errors = [i for i in v.report.get("issues", []) if i["severity"] == "error" and not i.get("auto_fixed")]
            raise ExportBlockedError(
                "검증을 통과하지 못한 설계는 내려받을 수 없습니다. 아래 문제를 해결하도록 설계를 수정해 주세요.",
                errors,
            )
        d = self._ensure_meshes(design, v)
        parts = [
            ExportPart(f"part{it['index'] + 1}_{it['template']}",
                       trimesh.load(d / f"print_{it['index']}.stl", file_type="stl"))
            for it in v.items
        ]
        return export_parts(parts, fmt, f"kkomul_{design.id[:8]}_v{v.version}", self.rules.printing.plate_spacing_mm)
