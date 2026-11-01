"""설계 생성·수정·내보내기 서비스.

파이프라인: 사육 환경 + 프롬프트 → LLM 해석(DesignSpec) → 엔진(보정·형상·배치·검증) → 버전 저장.
수정 시 직전 버전의 '보정 반영 명세'를 LLM 에 맥락으로 주고 새 버전을 만든다 (이전 버전 유지).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import trimesh
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import BuiltItem, Cage, Placement, PlacementHint
from app.geometry.export import ExportFile, ExportPart, export_parts
from app.geometry.fingerprint import GeometryFingerprinter, geometry_key, mesh_digest
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
from app.services.engine import EngineContext, build_item, revalidate, run_engine
from app.templates.registry import get_template
from app.validation.report import Issue, Severity

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
    code = "validation_failed"

    def __init__(self, message_ko: str, errors: list[dict]):
        super().__init__(message_ko)
        self.message_ko = message_ko
        self.errors = errors


class GeometryChangedError(ExportBlockedError):
    """현재 코드가 다시 만든 형상이 저장 당시 검증한 형상과 다르고, 다시 검증한 결과 통과하지 못했을 때."""

    code = "geometry_changed"


_ID_RE = re.compile(r"[0-9a-f]{32}")


class MeshRegenerationError(RuntimeError):
    """저장된 파라미터로 메시를 다시 만들 수 없을 때 (템플릿 변경 등)."""

    def __init__(self, message_ko: str):
        super().__init__(message_ko)
        self.message_ko = message_ko


MESH_UNAVAILABLE_KO = "이 설계 버전의 형상을 다시 만들 수 없어요. 같은 요청으로 새 버전을 만들어 주세요."
GEOMETRY_CHANGED_KO = (
    "서비스 업데이트로 이 버전의 형상이 처음 검증할 때와 달라졌고, 다시 검증한 결과 문제가 있어 내려받을 수 없어요. "
    "같은 요청으로 새 버전을 만들어 주세요."
)
GEOMETRY_REVALIDATED_KO = "서비스 업데이트로 형상 생성 방식이 바뀌어, 이 버전의 형상을 현재 기준으로 다시 검증했어요."

# 메시 캐시 디렉터리의 판정 파일. 메시 파일을 모두 쓴 뒤 마지막에 써서 '완성된 캐시' 표시를 겸한다.
_MANIFEST = "geometry.json"


@dataclass(frozen=True)
class GeometryCheck:
    """현재 코드가 만든 이 버전의 형상이 저장 당시 검증한 형상과 같은지에 대한 판정."""

    fingerprint: str              # 현재 파이프라인 지문
    digests: dict[str, str]       # 항목별 현재 메시 요약값 (키: 항목 index 문자열)
    identical: bool | None        # 저장 당시 요약값과 모두 같은지 (None: 요약값이 없는, 이 기능 이전 버전)
    report: dict | None = None    # 같다고 확인하지 못해 현재 규칙으로 다시 검증한 결과 {"passed", "issues"}

    @property
    def key(self) -> str:
        """뷰어 메시 URL 의 형상 키 (?g=)."""
        return _digests_key(self.digests)

    @property
    def blocked(self) -> bool:
        return self.report is not None and not self.report["passed"]


def _digests_key(digests: dict[str, str]) -> str:
    return geometry_key(digests[k] for k in sorted(digests, key=int))


def _atomic_write(path: Path, write: Callable[[Path], object]) -> None:
    """임시 파일에 쓴 뒤 os.replace 로 바꿔 끼운다. 동시에 읽는 요청이 반쯤 쓰인 파일을 받지 않게 한다."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_export(mesh: trimesh.Trimesh, path: Path) -> None:
    _atomic_write(path, lambda p: mesh.export(p, file_type="stl"))


def _write_manifest(d: Path, check: GeometryCheck) -> None:
    text = json.dumps(asdict(check), ensure_ascii=False)
    _atomic_write(d / _MANIFEST, lambda p: p.write_text(text, encoding="utf-8"))


class DesignService:
    def __init__(self, rules: RuleBook, interpreter: Callable[[], Interpreter], mesh_dir: Path):
        self.rules = rules
        self._interpreter = interpreter
        self.mesh_dir = Path(mesh_dir)
        self.fingerprints = GeometryFingerprinter(rules.printing)
        self._locks_guard = threading.Lock()
        self._version_locks: dict[str, threading.Lock] = {}

    def _version_lock(self, design_id: str, version: int) -> threading.Lock:
        """버전별 메시 재생성 잠금 (같은 버전을 동시에 여러 번 만들지 않도록)."""
        key = f"{design_id}/{version}"
        with self._locks_guard:
            return self._version_locks.setdefault(key, threading.Lock())

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
        h = db.get(Habitat, habitat_id) if _ID_RE.fullmatch(habitat_id) else None
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
        # LLM 호출(수십 초) 동안 DB 연결을 '트랜잭션 중' 상태로 잡아 두지 않도록 읽기 트랜잭션을 끝낸다
        db.commit()
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
        habitat = design.habitat
        db.commit()  # LLM 호출 전에 읽기 트랜잭션 종료 (create_design 과 같은 이유)
        generated = self._generate(habitat, prompt, previous=previous)
        next_no = (db.scalar(select(func.max(DesignVersion.version)).where(DesignVersion.design_id == design.id)) or 0) + 1
        self._save_version(db, design, generated, next_no)
        db.commit()
        db.refresh(design)
        return design, generated["row"]

    @staticmethod
    def _previous_spec(base: DesignVersion):
        for candidate in (base.effective_spec, base.llm_spec):
            try:
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
        fingerprint = self.fingerprints.for_templates(it.key for it in engine.items)
        worlds = {it.index: it.world_mesh() if it.placement is not None else None for it in engine.items}
        digests = {str(it.index): mesh_digest(it.print_mesh, worlds[it.index]) for it in engine.items}
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
                # 검증한 메시(출력 자세 + 배치)의 요약값. 메시를 다시 만들 때 같은 형상인지 이 값으로 확인한다.
                "mesh_sha256": digests[str(it.index)],
            })
        if effective_items:
            effective["items"] = effective_items

        row = DesignVersion(
            design_id=design.id, version=version_no, prompt=g["prompt"],
            provider=g["interpret"].provider, llm_attempts=g["interpret"].attempts,
            llm_spec=llm_spec, effective_spec=effective, items=built_items,
            report=engine.report.model_dump(mode="json"), passed=engine.report.passed,
            geometry_fingerprint=fingerprint,
        )
        db.add(row)
        db.flush()
        g["row"] = row
        # 메시 캐시 저장 (뷰어용 배치 메시 + 출력 자세 메시). 방금 검증한 메시이므로 판정은 '같음'.
        d = self._version_dir(design.id, version_no, fingerprint)
        d.mkdir(parents=True, exist_ok=True)
        for it in engine.items:
            _atomic_export(it.print_mesh, d / f"print_{it.index}.stl")
            if worlds[it.index] is not None:
                _atomic_export(worlds[it.index], d / f"world_{it.index}.stl")
        _write_manifest(d, GeometryCheck(fingerprint=fingerprint, digests=digests, identical=True))

    # ── 조회 ────────────────────────────────────────────────

    def get_design(self, db: Session, design_id: str) -> Design:
        d = db.get(Design, design_id) if _ID_RE.fullmatch(design_id) else None
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

    def design_out(self, design: Design, v: DesignVersion, verify: bool = False) -> DesignOut:
        """응답 변환. verify=True 면 메시를 준비하면서(캐시가 없으면 다시 만들어) 현재 형상이 검증한 형상과 같은지
        확인하고, 다르면 다시 검증한 결과를 검증 보고서·내려받기 가능 여부·메시 URL 에 반영한다."""
        geometry: GeometryCheck | None = None
        unavailable = False
        if verify:
            try:
                _, geometry = self._ensure_meshes(design, v)
            except MeshRegenerationError:
                unavailable = True
        key = geometry.key if geometry else self._stored_geometry_key(v)

        items = [
            ItemOut(
                index=it["index"], template=it["template"], label_ko=it["label_ko"], params=it["params"],
                reason_ko=it["reason_ko"],
                placement=PlacementOut(**it["placement"]) if it["placement"] else None,
                size_mm=it["size_mm"], print_size_mm=it["print_size_mm"],
                mesh_url=(f"/designs/{design.id}/versions/{v.version}/parts/{it['index']}.stl?g={key}"
                          if it["placement"] and not unavailable else None),
            )
            for it in v.items
        ]
        stored_issues = list(v.report.get("issues", []))
        passed = v.passed
        if geometry is not None and geometry.report is not None:
            # 다시 검증한 보고서가 현재 형상에 대한 것이다. 파라미터 자동 보정 내역은 설계 이력이라 그대로 둔다.
            notice = (Issue(code="geometry_changed", severity=Severity.error, message_ko=GEOMETRY_CHANGED_KO)
                      if geometry.blocked else
                      Issue(code="geometry_revalidated", severity=Severity.info, message_ko=GEOMETRY_REVALIDATED_KO))
            issues = ([notice.model_dump(mode="json")] + [i for i in stored_issues if i.get("auto_fixed")]
                      + geometry.report["issues"])
            passed = geometry.report["passed"]
        elif unavailable:
            issues = stored_issues + [Issue(code="mesh_unavailable", severity=Severity.error,
                                            message_ko=MESH_UNAVAILABLE_KO).model_dump(mode="json")]
            passed = False
        else:
            issues = stored_issues
        errors = [i for i in issues if i["severity"] == "error" and not i.get("auto_fixed")]
        validation = {
            "passed": passed,
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
                items=items, validation=validation, export_allowed=passed and bool(items),
                created_at=v.created_at,
            ),
        )

    # ── 메시 / 내보내기 ──────────────────────────────────────

    def geometry_fingerprint(self, items: list[dict]) -> str:
        return self.fingerprints.for_templates(it["template"] for it in items)

    def _stored_geometry_key(self, v: DesignVersion) -> str:
        digests = {str(it["index"]): it.get("mesh_sha256") for it in v.items}
        if all(digests.values()):
            return _digests_key(digests)
        return self.geometry_fingerprint(v.items)[:16]  # 요약값이 없는 예전 버전

    def _version_dir(self, design_id: str, version: int, fingerprint: str) -> Path:
        # 파이프라인 지문별로 나눠 둔다: 코드·설정이 바뀐 뒤에는 이전 코드가 만든 캐시를 확인 없이 쓰지 않는다
        return self.mesh_dir / design_id / f"v{version}" / fingerprint[:16]

    @staticmethod
    def _mesh_files(d: Path, items: list[dict]) -> list[Path]:
        files = []
        for it in items:
            files.append(d / f"print_{it['index']}.stl")
            if it["placement"]:
                files.append(d / f"world_{it['index']}.stl")
        return files

    def _read_manifest(self, d: Path, v: DesignVersion) -> GeometryCheck | None:
        """완성된 캐시(판정 파일 + 메시 파일 전부)가 있으면 그 판정을, 아니면 None."""
        try:
            check = GeometryCheck(**json.loads((d / _MANIFEST).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None
        if not all(f.is_file() for f in self._mesh_files(d, v.items)):
            return None
        return check

    def _ensure_meshes(self, design: Design, v: DesignVersion) -> tuple[Path, GeometryCheck]:
        """이 버전의 메시 캐시를 준비하고, 현재 형상이 저장 당시 검증한 형상과 같은지 판정을 돌려준다.

        캐시가 없으면(새 인스턴스·재배포 등) 저장된 최종 파라미터와 배치로 *현재 코드*가 다시 만든다.
        다시 만든 메시의 요약값이 저장 당시와 같으면 검증한 형상 그대로다. 다르거나 확인할 수 없으면
        (요약값이 없는 예전 버전) 현재 규칙으로 다시 검증한다. 판정은 메시와 함께 캐시에 남겨 인스턴스마다 한 번만 계산한다.
        """
        fingerprint = self.geometry_fingerprint(v.items)
        d = self._version_dir(design.id, v.version, fingerprint)
        check = self._read_manifest(d, v)
        if check is not None:
            return d, check
        # 컨테이너가 새로 뜨면 캐시가 비어 있어 여러 요청이 동시에 재생성을 시도할 수 있다.
        # 버전별 잠금으로 한 번만 만들고, 파일은 원자적으로 교체해 반쯤 쓰인 파일이 응답되지 않게 한다.
        with self._version_lock(design.id, v.version):
            check = self._read_manifest(d, v)
            if check is None:
                check = self._rebuild_meshes(design, v, d, fingerprint)
        return d, check

    def _rebuild_meshes(self, design: Design, v: DesignVersion, d: Path, fingerprint: str) -> GeometryCheck:
        built: list[tuple[dict, BuiltItem, trimesh.Trimesh | None]] = []
        for it in v.items:
            try:
                t = get_template(it["template"])
                b = build_item(it["index"], t, t.Params.model_validate(it["params"]), PlacementHint(),
                               self.rules.printing)
            except Exception as e:  # 템플릿 삭제·파라미터 스키마 변경·형상 커널 오류
                log.exception("mesh regeneration failed: design=%s v=%s item=%s", design.id, v.version, it)
                raise MeshRegenerationError(MESH_UNAVAILABLE_KO) from e
            if it["placement"]:
                b.placement = Placement(**it["placement"])
            built.append((it, b, b.world_mesh() if b.placement is not None else None))

        digests = {str(it["index"]): mesh_digest(b.print_mesh, world) for it, b, world in built}
        stored = {str(it["index"]): it.get("mesh_sha256") for it in v.items}
        identical = None if None in stored.values() else stored == digests
        report = None
        if not identical:
            log.warning(
                "geometry differs from validated version (identical=%s): design=%s v=%s stored_fp=%s current_fp=%s",
                identical, design.id, v.version, v.geometry_fingerprint, fingerprint,
            )
            # 검증을 통과했던(내려받을 수 있던) 버전만 다시 검증한다. 통과하지 못한 버전은 어차피 내려받을 수 없다.
            if v.passed:
                try:
                    r = revalidate([b for _, b, _ in built], self._engine_ctx(design.habitat))
                except Exception as e:  # 규칙에서 종/크기 삭제, 검사 중 형상 오류 등 → 형상을 확인할 수 없음
                    log.exception("revalidation failed: design=%s v=%s", design.id, v.version)
                    raise MeshRegenerationError(MESH_UNAVAILABLE_KO) from e
                report = {"passed": r.passed, "issues": [i.model_dump(mode="json") for i in r.issues]}
                log.warning("revalidated design=%s v=%s passed=%s errors=%s", design.id, v.version, r.passed,
                            [i.code for i in r.errors])

        d.mkdir(parents=True, exist_ok=True)
        for it, b, world in built:
            _atomic_export(b.print_mesh, d / f"print_{it['index']}.stl")
            if world is not None:
                _atomic_export(world, d / f"world_{it['index']}.stl")
        check = GeometryCheck(fingerprint=fingerprint, digests=digests, identical=identical, report=report)
        _write_manifest(d, check)
        return check

    def part_mesh(self, db: Session, design_id: str, version: int, index: int) -> tuple[Path, str]:
        """뷰어용 배치 메시 경로와 현재 형상 키."""
        design = self.get_design(db, design_id)
        v = self.get_version(db, design, version)
        if not any(it["index"] == index and it["placement"] for it in v.items):
            raise NotFoundError("해당 구조물 메시가 없습니다.")
        d, check = self._ensure_meshes(design, v)
        return d / f"world_{index}.stl", check.key

    def export(self, db: Session, design_id: str, version: int | None, fmt: str) -> ExportFile:
        design = self.get_design(db, design_id)
        v = self.get_version(db, design, version)
        if not v.passed or not v.items:
            errors = [i for i in v.report.get("issues", []) if i["severity"] == "error" and not i.get("auto_fixed")]
            raise ExportBlockedError(
                "검증을 통과하지 못한 설계는 내려받을 수 없습니다. 아래 문제를 해결하도록 설계를 수정해 주세요.",
                errors,
            )
        d, check = self._ensure_meshes(design, v)
        if check.blocked:
            assert check.report is not None
            errors = [i for i in check.report["issues"] if i["severity"] == "error" and not i.get("auto_fixed")]
            raise GeometryChangedError(GEOMETRY_CHANGED_KO, errors)
        parts = [
            ExportPart(f"part{it['index'] + 1}_{it['template']}",
                       trimesh.load(d / f"print_{it['index']}.stl", file_type="stl"))
            for it in v.items
        ]
        return export_parts(parts, fmt, f"kkomul_{design.id[:8]}_v{v.version}", self.rules.printing.plate_spacing_mm)
