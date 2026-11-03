"""설계 생성·수정·내보내기 서비스.

파이프라인: 사육 환경 + 프롬프트 → LLM 해석(DesignSpec) → 엔진(보정·형상·배치·검증) → 버전 저장.
수정 시 직전 버전의 '보정 반영 명세'를 LLM 에 맥락으로 주고 새 버전을 만든다 (이전 버전 유지).
"""

from __future__ import annotations

import copy
import logging
import os
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import trimesh
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain import BuiltItem, Cage, Placement, PlacementHint
from app.geometry.export import ExportFile, ExportPart, export_parts
from app.geometry.fingerprint import file_digest, geometry_fingerprint
from app.llm.base import HabitatInfo, Interpreter, InterpretRequest
from app.llm.spec import parse_spec, to_item_specs
from app.models import Design, DesignVersion, Habitat, Pet, Post, User
from app.rules.loader import RuleBook
from app.schemas import (
    CageIn,
    DesignListItem,
    DesignListOut,
    DesignOut,
    HabitatIn,
    HabitatOut,
    ItemOut,
    PlacementOut,
    VersionOut,
    VersionSummary,
)
from app.services import usage
from app.services.engine import EngineContext, build_item, revalidate, run_engine
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


_ID_RE = re.compile(r"[0-9a-f]{32}")


class MeshRegenerationError(RuntimeError):
    """저장된 파라미터로 메시를 다시 만들 수 없을 때 (템플릿 변경 등)."""

    def __init__(self, message_ko: str):
        super().__init__(message_ko)
        self.message_ko = message_ko


class GeometryChangedError(MeshRegenerationError):
    """다시 만든 형상이 저장할 때 검증한 형상과 같다고 확인되지 않았고, 다시 검증해도 통과하지 못할 때."""

    MESSAGE_KO = (
        "이 설계 버전을 만든 뒤 서비스가 업데이트되어, 지금 다시 만든 형상이 처음 검증한 형상과 같다고 확인할 수 "
        "없었어요. 다시 검증해 보니 안전 기준을 통과하지 못해 내려받을 수 없어요. 같은 요청으로 새 버전을 만들어 주세요."
    )

    def __init__(self, errors: list[dict]):
        super().__init__(self.MESSAGE_KO)
        self.errors = errors


def _atomic_write(path: Path, data: bytes) -> None:
    """임시 파일에 쓴 뒤 os.replace 로 바꿔 끼운다. 동시에 읽는 요청이 반쯤 쓰인 파일을 받지 않게 한다."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _mesh_files(item: BuiltItem) -> dict[str, bytes]:
    """구조물 하나의 메시 캐시 파일: 출력 자세(print_i), 배치된 경우 케이지 좌표계 뷰어 메시(world_i)."""
    files = {f"print_{item.index}.stl": item.print_mesh.export(file_type="stl")}
    if item.placement is not None:
        files[f"world_{item.index}.stl"] = item.world_mesh().export(file_type="stl")
    return files


@dataclass(frozen=True)
class DesignLimits:
    """최근 24시간 설계 요청(LLM 호출) 횟수 상한. 관리자는 적용하지 않는다.
    per_user·global_ 은 0 이면 막음, per_ip 는 0 이면 IP 별 제한 없음."""

    per_user: int = 20
    global_: int = 300
    per_ip: int = 40


TITLE_LEN = 40


def make_title(prompt: str) -> str:
    """설계 제목: 사용자가 쓴 첫 요청의 첫 줄 (길면 줄임표). LLM 설명문보다 짧고 본인이 알아보기 쉽다."""
    first = next((line.strip() for line in prompt.splitlines() if line.strip()), "") or "맞춤 설계"
    return first if len(first) <= TITLE_LEN else first[: TITLE_LEN - 1].rstrip() + "…"


def _can_edit(design: Design, user: User) -> bool:
    """수정·공유 권한: 소유자만. 소유자가 없는 옛 설계(회원 기능 이전)는 관리자가 소유자다.
    관리자도 회원의 설계를 대신 공유·수정하지는 못한다 (볼 수만 있다: _can_view_all)."""
    if design.owner_id is None:
        return user.is_admin
    return design.owner_id == user.id


def _can_view_all(design: Design, user: User | None) -> bool:
    """모든 버전을 볼 수 있는지: 소유자, 또는 관리자(운영·신고 처리)."""
    return user is not None and (user.is_admin or _can_edit(design, user))


class DesignService:
    def __init__(self, rules: RuleBook, interpreter: Callable[[], Interpreter], mesh_dir: Path,
                 limits: DesignLimits | None = None):
        self.rules = rules
        self._interpreter = interpreter
        self.mesh_dir = Path(mesh_dir)
        self.limits = limits or DesignLimits()
        self._locks_guard = threading.Lock()
        self._version_locks: dict[str, threading.Lock] = {}
        # 다시 검증에 실패한 버전 → 오류 목록. 같은 코드로 실행되는 동안 결과는 바뀌지 않으므로, 요청마다
        # 형상 생성·검증을 되풀이하지 않고 바로 막는다 (공유된 설계의 뷰어가 메시를 여러 번 요청해도 가볍게).
        self._geometry_blocked: dict[tuple[str, int], list[dict]] = {}

    def _version_lock(self, design_id: str, version: int) -> threading.Lock:
        """버전별 메시 재생성 잠금 (같은 버전을 동시에 여러 번 만들지 않도록)."""
        key = f"{design_id}/{version}"
        with self._locks_guard:
            return self._version_locks.setdefault(key, threading.Lock())

    # ── 사육 환경 ───────────────────────────────────────────

    def check_species(self, species: str, size: str) -> None:
        try:
            self.rules.size_rules(species, size)
        except KeyError:
            raise InvalidInputError(f"지원하지 않는 종/크기입니다: {species}/{size}") from None

    def create_habitat(self, db: Session, data: HabitatIn, user: User) -> Habitat:
        self.check_species(data.species, data.size)
        if data.pet_id is not None:
            pet = db.get(Pet, data.pet_id)
            if pet is None or pet.owner_id != user.id:
                raise NotFoundError("반려동물 정보를 찾을 수 없습니다.")
        h = Habitat(
            owner_id=user.id, pet_id=data.pet_id,
            species=data.species, size=data.size, count=data.count,
            cage_width_mm=data.cage.width_mm, cage_depth_mm=data.cage.depth_mm, cage_height_mm=data.cage.height_mm,
        )
        db.add(h)
        db.commit()
        return h

    def get_habitat(self, db: Session, habitat_id: str, user: User) -> Habitat:
        h = db.get(Habitat, habitat_id) if _ID_RE.fullmatch(habitat_id) else None
        # 남의 사육 환경은 없는 것과 같이 다룬다 (존재 여부도 알리지 않음)
        if h is None or not (user.is_admin or (h.owner_id is not None and h.owner_id == user.id)):
            raise NotFoundError("사육 환경을 찾을 수 없습니다.")
        return h

    def habitat_out(self, h: Habitat) -> HabitatOut:
        sp = self.rules.species_file.species.get(h.species)
        size = sp.sizes.get(h.size) if sp else None
        return HabitatOut(
            id=h.id, pet_id=h.pet_id, species=h.species, species_name_ko=sp.display_name if sp else h.species,
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

    def quota(self, db: Session, user: User) -> dict[str, int | None]:
        """최근 24시간 설계 요청 횟수와 상한 (관리자는 상한 없음 → None). 실패한 요청도 센다."""
        used = usage.count(db, "design", user_id=user.id)
        limit = None if user.is_admin else self.limits.per_user
        return {"used": used, "limit": limit, "remaining": None if limit is None else max(0, limit - used)}

    def reserve_quota(self, db: Session, user: User, ip_key: str | None) -> None:
        """LLM 을 부르기 전에 사용량 1회를 기록한다 (상한에 닿았으면 429). 동시 요청도 상한을 넘지 못한다."""
        if user.is_admin:
            db.commit()  # 상한은 없지만 LLM 호출 동안 읽기 트랜잭션을 열어 두지 않는다
            return
        lim = self.limits
        usage.reserve(
            db, "design", user, ip_key=ip_key,
            per_user=usage.Cap(lim.per_user, f"최근 24시간 동안 쓸 수 있는 설계 횟수({lim.per_user}회)를 모두 썼어요. "
                                             "잠시 뒤 다시 시도해 주세요.", "design_quota_exceeded"),
            per_ip=usage.Cap(lim.per_ip, "이 네트워크에서 최근 24시간 동안 설계 요청이 너무 많았어요. 잠시 뒤 다시 시도해 주세요.",
                             "design_quota_exceeded") if lim.per_ip > 0 else None,
            global_=usage.Cap(lim.global_, "오늘은 서비스 전체 설계 요청이 많아 잠시 쉬어 가요. 나중에 다시 시도해 주세요.",
                              "design_capacity_exceeded"),
        )

    def create_design(self, db: Session, habitat_id: str, prompt: str, user: User,
                      ip_key: str | None = None) -> tuple[Design, DesignVersion]:
        h = self.get_habitat(db, habitat_id, user)
        # 사용량을 먼저 기록하고 커밋한다 (LLM 호출 수십 초 동안 DB 연결을 '트랜잭션 중' 상태로 잡아 두지 않는다)
        self.reserve_quota(db, user, ip_key)
        version = self._generate(h, prompt, previous=None)  # LLM 실패 시 예외 → 아무것도 저장하지 않음
        design = Design(habitat_id=h.id, owner_id=user.id, title=make_title(prompt))
        db.add(design)
        db.flush()
        self._save_version(db, design, version, 1, user)
        db.commit()
        return design, version["row"]

    def revise_design(
        self, db: Session, design_id: str, prompt: str, user: User, base_version: int | None = None,
        ip_key: str | None = None,
    ) -> tuple[Design, DesignVersion]:
        design = self.get_editable_design(db, design_id, user)
        base = self.get_version(db, design, base_version)
        previous = self._previous_spec(base)
        habitat = design.habitat
        self.reserve_quota(db, user, ip_key)  # 기록 후 커밋 (create_design 과 같은 이유)
        generated = self._generate(habitat, prompt, previous=previous)
        next_no = (db.scalar(select(func.max(DesignVersion.version)).where(DesignVersion.design_id == design.id)) or 0) + 1
        self._save_version(db, design, generated, next_no, user)
        db.commit()
        db.refresh(design)
        return design, generated["row"]

    @staticmethod
    def _with_legacy_defaults(spec: dict) -> dict:
        """저장 당시 없던 파라미터를 legacy_defaults 로 채운다 (메시 재생성과 같은 형상을 LLM 에게 보여 주도록)."""
        items = []
        for it in spec.get("items") or []:
            if not isinstance(it, dict):  # 형식 오류는 parse_spec 이 걸러낸다
                items.append(it)
                continue
            try:
                legacy = get_template(it.get("template")).legacy_defaults
            except Exception:  # 알 수 없는 템플릿도 parse_spec 이 걸러낸다
                legacy = {}
            if legacy and isinstance(it.get("params"), dict):
                it = {**it, "params": {**legacy, **it["params"]}}
            items.append(it)
        return {**spec, "items": items}

    @classmethod
    def _previous_spec(cls, base: DesignVersion):
        for candidate in (base.effective_spec, base.llm_spec):
            try:
                import json

                return parse_spec(json.dumps(cls._with_legacy_defaults(candidate), ensure_ascii=False))
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

    def _save_version(self, db: Session, design: Design, g: dict, version_no: int, user: User) -> None:
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

        # 검증한 형상 그대로의 메시 파일. 해시를 함께 저장해 두고, 캐시를 다시 만들 때 같은 형상인지 확인한다
        files: dict[str, bytes] = {}
        for it in engine.items:
            files.update(_mesh_files(it))
        geometry = {
            "fingerprint": geometry_fingerprint((it.key for it in engine.items), self.rules.printing),
            "files": {name: file_digest(data) for name, data in files.items()},
        }
        row = DesignVersion(
            design_id=design.id, version=version_no, prompt=g["prompt"],
            provider=g["interpret"].provider, llm_attempts=g["interpret"].attempts,
            llm_spec=llm_spec, effective_spec=effective, items=built_items,
            report=engine.report.model_dump(mode="json"), passed=engine.report.passed, geometry=geometry,
            created_by=user.id,
        )
        db.add(row)
        db.flush()
        g["row"] = row
        # 메시 캐시 저장 (뷰어용 배치 메시 + 출력 자세 메시)
        d = self._version_dir(design.id, version_no)
        d.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            _atomic_write(d / name, data)

    # ── 조회 ────────────────────────────────────────────────

    def get_design(self, db: Session, design_id: str) -> Design:
        """권한 확인 없이 찾는다. API 에서는 get_visible / get_editable_design 을 쓴다."""
        d = db.get(Design, design_id) if _ID_RE.fullmatch(design_id) else None
        if d is None:
            raise NotFoundError("설계를 찾을 수 없습니다.")
        return d

    @staticmethod
    def shared_versions(db: Session, design_id: str) -> list[int]:
        """커뮤니티 글에 첨부된 버전 (누구나 볼 수 있다)."""
        rows = db.scalars(select(Post.design_version).where(Post.design_id == design_id,
                                                            Post.design_version.is_not(None)).distinct())
        return sorted(set(rows))

    def get_visible(self, db: Session, design_id: str, user: User | None) -> tuple[Design, set[int] | None]:
        """볼 수 있는 설계와 볼 수 있는 버전 (None = 모든 버전).

        소유자·관리자는 모든 버전, 그 밖의 사람은 커뮤니티 글에 첨부된 버전만 본다
        (공유한 뒤에 만든 버전이나 공유하지 않은 이전 버전은 보이지 않는다). 볼 수 있는 버전이 없으면 404."""
        d = self.get_design(db, design_id)
        if _can_view_all(d, user):
            return d, None
        allowed = set(self.shared_versions(db, d.id))
        if not allowed:
            raise NotFoundError("설계를 찾을 수 없습니다.")
        return d, allowed

    def get_editable_design(self, db: Session, design_id: str, user: User) -> Design:
        d = self.get_design(db, design_id)
        if not _can_edit(d, user):
            raise NotFoundError("설계를 찾을 수 없습니다.")
        return d

    def list_designs(self, db: Session, user: User, page: int, page_size: int) -> DesignListOut:
        """내 설계 목록 (최근 수정순). 관리자는 소유자가 없는 옛 설계도 함께 본다."""
        cond = Design.owner_id == user.id
        if user.is_admin:
            cond = cond | Design.owner_id.is_(None)
        latest = (select(DesignVersion.design_id, func.max(DesignVersion.created_at).label("updated"),
                         func.count(DesignVersion.id).label("n"), func.max(DesignVersion.version).label("last"))
                  .group_by(DesignVersion.design_id).subquery())
        total = db.scalar(select(func.count(Design.id)).where(cond)) or 0
        rows = db.execute(
            select(Design, latest.c.updated, latest.c.n, latest.c.last)
            .options(selectinload(Design.habitat))
            .join(latest, latest.c.design_id == Design.id)
            .where(cond)
            .order_by(latest.c.updated.desc(), Design.id)
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        ids = [r[0].id for r in rows]
        shared_ids, passed, pets = set(), {}, {}
        if rows:
            shared_ids = set(db.scalars(select(Post.design_id).where(Post.design_id.in_(ids))))
            # 각 설계의 최신 버전 검증 결과만 읽는다 (버전 JSON 전체를 불러오지 않게)
            passed = dict(db.execute(
                select(DesignVersion.design_id, DesignVersion.passed)
                .join(latest, (latest.c.design_id == DesignVersion.design_id) & (latest.c.last == DesignVersion.version))
                .where(DesignVersion.design_id.in_(ids))
            ).all())
            pet_ids = {d.habitat.pet_id for d, *_ in rows if d.habitat.pet_id}
            if pet_ids:
                pets = {p.id: p.name for p in db.scalars(select(Pet).where(Pet.id.in_(pet_ids)))}
        items = []
        for d, updated, n, last in rows:
            items.append(DesignListItem(
                id=d.id, title=d.title or self.title_of(d), created_at=d.created_at, updated_at=updated,
                version_count=n, latest_version=last, latest_passed=bool(passed.get(d.id)),
                habitat=self.habitat_out(d.habitat), pet_name=pets.get(d.habitat.pet_id),
                shared=d.id in shared_ids,
            ))
        return DesignListOut(items=items, total=total, page=page, page_size=page_size)

    @staticmethod
    def title_of(design: Design) -> str:
        if design.title:
            return design.title
        first = design.versions[0] if design.versions else None
        return make_title(first.prompt) if first is not None else "맞춤 설계"

    def get_version(self, db: Session, design: Design, version: int | None,
                    allowed: set[int] | None = None) -> DesignVersion:
        """버전을 찾는다. allowed 가 있으면 그 버전만 (지정하지 않으면 그중 최신)."""
        versions = [v for v in design.versions if allowed is None or v.version in allowed]
        if not versions:
            raise NotFoundError("설계 버전이 없습니다.")
        if version is None:
            return versions[-1]
        for v in versions:
            if v.version == version:
                return v
        raise NotFoundError(f"버전 {version} 을(를) 찾을 수 없습니다.")

    def design_out(self, db: Session, design: Design, v: DesignVersion, user: User | None) -> DesignOut:
        # 뷰어 메시 URL 에 지금 형상 코드의 지문을 붙인다: 배포로 형상이 바뀌면 URL 도 바뀌어 브라우저 캐시
        # (max-age 하루)가 옛 형상을 보여주지 않는다
        g = geometry_fingerprint((it["template"] for it in v.items), self.rules.printing)[:16]
        items = [
            ItemOut(
                index=it["index"], template=it["template"], label_ko=it["label_ko"], params=it["params"],
                reason_ko=it["reason_ko"],
                placement=PlacementOut(**it["placement"]) if it["placement"] else None,
                size_mm=it["size_mm"], print_size_mm=it["print_size_mm"],
                mesh_url=(f"/designs/{design.id}/versions/{v.version}/parts/{it['index']}.stl?g={g}"
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
        shared = self.shared_versions(db, design.id)
        see_all = _can_view_all(design, user)
        return DesignOut(
            id=design.id,
            title=self.title_of(design),
            is_owner=user is not None and _can_edit(design, user),
            shared=bool(shared),
            shared_versions=shared,
            owner_nickname=design.owner.nickname if design.owner else None,
            habitat=self.habitat_out(design.habitat),
            versions=[
                VersionSummary(version=x.version, prompt=x.prompt, passed=x.passed, provider=x.provider,
                               created_at=x.created_at)
                for x in design.versions if see_all or x.version in shared
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

    def _rebuild(self, design: Design, v: DesignVersion, it: dict) -> BuiltItem:
        """저장된 최종 파라미터·배치로 구조물 하나를 다시 만든다."""
        try:
            t = get_template(it["template"])
            built = build_item(it["index"], t, t.load_stored_params(it["params"]), PlacementHint(),
                               self.rules.printing)
        except Exception as e:  # 템플릿 삭제·파라미터 스키마 변경·형상 커널 오류
            log.exception("mesh regeneration failed: design=%s v=%s item=%s", design.id, v.version, it)
            raise MeshRegenerationError(
                "이 설계 버전의 형상을 다시 만들 수 없어요. 같은 요청으로 새 버전을 만들어 주세요."
            ) from e
        if it["placement"]:
            built.placement = Placement(**it["placement"])
        return built

    def _revalidate(self, design: Design, v: DesignVersion, rebuilt: dict[int, BuiltItem], changed: list[str]) -> None:
        """다시 만든 형상이 저장할 때 검증한 형상과 다를 때(또는 확인할 해시가 없는 옛 버전일 때),
        구조물 전체를 저장된 배치 그대로 지금 기준으로 다시 검증한다. 통과하지 못하면 GeometryChangedError.
        rebuilt 에 아직 다시 만들지 않은 구조물을 채운다 (겹침·틈새는 구조물끼리 함께 봐야 한다)."""
        stored = v.geometry or {}
        current = geometry_fingerprint((it["template"] for it in v.items), self.rules.printing)
        if stored.get("files"):
            log.warning(
                "rebuilt geometry differs from the validated geometry: design=%s v=%s files=%s "
                "fingerprint %s -> %s; re-validating",
                design.id, v.version, ",".join(changed), stored.get("fingerprint"), current,
            )
        else:
            log.warning("no stored geometry digests (version predates them): design=%s v=%s; re-validating",
                        design.id, v.version)
        for it in v.items:
            if it["index"] not in rebuilt:
                rebuilt[it["index"]] = self._rebuild(design, v, it)
        try:
            report = revalidate([rebuilt[i] for i in sorted(rebuilt)], self._engine_ctx(design.habitat))
        except Exception as e:  # 규칙 파일에서 종/크기가 빠짐, 검증 중 형상 오류 등 → 확인할 수 없으면 막는다
            log.exception("re-validation failed to run: design=%s v=%s", design.id, v.version)
            raise MeshRegenerationError(
                "이 설계 버전의 형상을 다시 검증할 수 없어요. 같은 요청으로 새 버전을 만들어 주세요."
            ) from e
        if not report.passed:
            errors = [i.model_dump(mode="json") for i in report.errors]
            log.warning("re-validation failed: design=%s v=%s codes=%s", design.id, v.version,
                        ",".join(sorted({e["code"] for e in errors})))
            self._geometry_blocked[(design.id, v.version)] = errors
            raise GeometryChangedError(errors)
        log.info("re-validation passed: design=%s v=%s", design.id, v.version)

    def _ensure_meshes(self, design: Design, v: DesignVersion) -> Path:
        """메시 캐시가 없으면(새 인스턴스·삭제 등) 저장된 최종 파라미터로 다시 만든다.

        캐시에는 검증을 거친 형상만 둔다 (파일이 있으면 그대로 응답하므로):
          - 다시 만든 파일이 저장할 때 기록한 해시와 바이트 단위로 같으면 그대로 쓴다 (형상 생성은 결정적).
          - 다르거나 (배포 사이 템플릿 build()·테셀레이션 설정·형상 라이브러리 변경) 해시가 없는 옛 버전이면,
            구조물 전체를 다시 검증한다. 통과하면 다시 만든 형상으로 캐시 전체를 맞추고(남아 있던 파일과
            섞이지 않게), 통과하지 못하면 아무 파일도 쓰지 않고 뷰어·내려받기 모두 409 로 막는다.
          - 처음부터 검증을 통과하지 못한 버전은 다시 검증하지 않는다. 내려받기는 이미 막혀 있고(export 의
            v.passed 확인), 메시는 어디가 문제인지 보여 주는 뷰어에만 쓰인다."""
        d = self._version_dir(design.id, v.version)

        def missing() -> list[dict]:
            return [it for it in v.items if not (d / f"print_{it['index']}.stl").is_file()
                    or (it["placement"] and not (d / f"world_{it['index']}.stl").is_file())]

        if not missing():
            return d
        # 컨테이너가 새로 뜨면 캐시가 비어 있어 여러 요청이 동시에 재생성을 시도할 수 있다.
        # 버전별 잠금으로 한 번만 만들고, 파일은 원자적으로 교체해 반쯤 쓰인 파일이 응답되지 않게 한다.
        with self._version_lock(design.id, v.version):
            blocked = self._geometry_blocked.get((design.id, v.version))
            if blocked is not None:
                raise GeometryChangedError(blocked)
            todo = missing()
            if not todo:
                return d
            rebuilt = {it["index"]: self._rebuild(design, v, it) for it in todo}
            files = {name: data for b in rebuilt.values() for name, data in _mesh_files(b).items()}
            expected = (v.geometry or {}).get("files") or {}
            changed = sorted(name for name, data in files.items() if expected.get(name) != file_digest(data))
            if changed and v.passed:
                done = set(rebuilt)
                self._revalidate(design, v, rebuilt, changed)
                for i, b in rebuilt.items():
                    if i not in done:
                        files.update(_mesh_files(b))
            d.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                _atomic_write(d / name, data)
        return d

    def part_mesh_path(self, db: Session, design_id: str, version: int, index: int, user: User | None) -> Path:
        design, allowed = self.get_visible(db, design_id, user)
        v = self.get_version(db, design, version, allowed)
        if not any(it["index"] == index and it["placement"] for it in v.items):
            raise NotFoundError("해당 구조물 메시가 없습니다.")
        return self._ensure_meshes(design, v) / f"world_{index}.stl"

    def export(self, db: Session, design_id: str, version: int | None, fmt: str, user: User | None) -> ExportFile:
        design, allowed = self.get_visible(db, design_id, user)
        v = self.get_version(db, design, version, allowed)
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
        return export_parts(parts, fmt, f"nestforge_{design.id[:8]}_v{v.version}", self.rules.printing.plate_spacing_mm)
